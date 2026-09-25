from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import COMMENT_FIXTURES, DEMO_USERS, PHOTO_FIXTURES, RESTAURANTS
from app.db.schema import metadata
from app.main import app
from app.services import comments as comment_service
from app.services import feed as feed_service
from app.services import notifications as notification_service
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import users as user_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError

# The photograph the seed holds the conversation on, and its author.
TALKED_ABOUT = PHOTO_FIXTURES[0]
PHOTO_AUTHOR = DEMO_USERS[1]
# A private photograph of `demo`, which is the only account that sees it.
PRIVATE_PHOTO = PHOTO_FIXTURES[2]
OWNER = DEMO_USERS[0]
STRANGER = DEMO_USERS[2]

THREAD = COMMENT_FIXTURES[0]
REPLIES = COMMENT_FIXTURES[1:5]
WITHOUT_REPLIES = COMMENT_FIXTURES[5]
BY_THE_PHOTO_AUTHOR = COMMENT_FIXTURES[6]


class FixtureStorage:
    def store(self, *, media_id, stream, content_type, extension):
        del content_type, stream
        return f"test/photos/{media_id}.{extension}"

    def delete(self, storage_key):
        del storage_key


@pytest.fixture
def seeded_database(monkeypatch):
    database = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(database)
    for module in (
        seed_module,
        comment_service,
        photo_service,
        restaurant_service,
        feed_service,
        user_service,
        notification_service,
    ):
        monkeypatch.setattr(module, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def session(user=OWNER):
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def comments(photo_id=TALKED_ABOUT.id, viewer=OWNER, limit=20, cursor=None):
    return comment_service.list_comments(photo_id, viewer_id=viewer.id, limit=limit, cursor=cursor)


def replies(comment_id=THREAD.id, viewer=OWNER, limit=20, cursor=None):
    return comment_service.list_replies(comment_id, viewer_id=viewer.id, limit=limit, cursor=cursor)


def write(text="Se ven muy buenas.", *, author=OWNER, photo_id=TALKED_ABOUT.id, parent_id=None):
    return comment_service.create_comment(
        author_id=author.id, photo_id=photo_id, text=text, parent_id=parent_id
    )


def test_two_people_converse_over_a_public_photograph(seeded_database):
    del seeded_database

    comment = write("¿Queda lejos del metro?")
    reply = write("A dos cuadras.", author=STRANGER, parent_id=comment.id)

    assert comment.parent_id is None
    assert comment.photo_id == TALKED_ABOUT.id
    assert comment.author.handle == OWNER.handle
    assert comment.author.nationality.name == "Chile"
    assert reply.parent_id == comment.id
    assert reply.author.handle == STRANGER.handle


def test_answering_a_reply_stays_on_the_second_level(seeded_database):
    del seeded_database

    reply_to_a_reply = write("Yo también.", parent_id=REPLIES[0].id)

    # It hangs from the comment the reply belongs to, not from the reply.
    assert reply_to_a_reply.parent_id == THREAD.id
    assert reply_to_a_reply.id in {reply.id for reply in replies().items}


def test_the_author_of_a_photograph_comments_on_their_own(seeded_database):
    del seeded_database

    own = write("Volvería sólo por esto.", author=PHOTO_AUTHOR)

    assert own.author.handle == PHOTO_AUTHOR.handle
    assert own.id in {thread.comment.id for thread in comments(viewer=PHOTO_AUTHOR).items}


def test_a_private_photograph_admits_no_conversation(seeded_database):
    del seeded_database

    # Its own author: it exists, and there is nobody to converse with.
    with pytest.raises(comment_service.InvalidCommentError):
        write(photo_id=PRIVATE_PHOTO.id, author=OWNER)
    with pytest.raises(comment_service.InvalidCommentError):
        comments(photo_id=PRIVATE_PHOTO.id, viewer=OWNER)
    # Somebody else's: indistinguishable from one that does not exist.
    with pytest.raises(comment_service.CommentNotFoundError):
        write(photo_id=PRIVATE_PHOTO.id, author=STRANGER)
    with pytest.raises(comment_service.CommentNotFoundError):
        comments(photo_id=PRIVATE_PHOTO.id, viewer=STRANGER)
    with pytest.raises(comment_service.CommentNotFoundError):
        write(photo_id=uuid4())


def test_a_text_or_a_parent_that_cannot_be_accepted(seeded_database):
    del seeded_database
    other_photo = PHOTO_FIXTURES[1]

    with pytest.raises(comment_service.InvalidCommentError):
        write("   ")
    with pytest.raises(comment_service.InvalidCommentError):
        write("a" * (comment_service.MAXIMUM_COMMENT_LENGTH + 1))
    with pytest.raises(comment_service.InvalidCommentError):
        write(parent_id=uuid4())
    # The parent exists, but belongs to another photograph.
    foreign = write(photo_id=other_photo.id)
    with pytest.raises(comment_service.InvalidCommentError):
        write(parent_id=foreign.id)


def test_the_conversation_reads_backwards_and_each_thread_forwards(seeded_database):
    del seeded_database

    page = comments()

    # First level, newest first.
    assert [thread.comment.id for thread in page.items] == [
        BY_THE_PHOTO_AUTHOR.id,
        WITHOUT_REPLIES.id,
        THREAD.id,
    ]
    thread = page.items[-1]
    # Four replies in the seed, and the first three travel inside.
    assert thread.reply_count == len(REPLIES) == 4
    assert len(thread.replies) == comment_service.REPLY_PREVIEW
    assert [reply.id for reply in thread.replies] == [reply.id for reply in REPLIES[:3]]
    assert page.items[0].reply_count == 0
    assert page.items[0].replies == ()
    assert page.next_cursor is None


def test_the_replies_of_a_comment_read_forwards(seeded_database):
    del seeded_database

    page = replies()

    assert [reply.id for reply in page.items] == [reply.id for reply in REPLIES]
    assert all(reply.parent_id == THREAD.id for reply in page.items)
    assert page.next_cursor is None


def test_both_lists_page_without_repeating_or_skipping(seeded_database):
    del seeded_database
    every_comment = [thread.comment.id for thread in comments().items]
    every_reply = [reply.id for reply in replies().items]

    seen_comments = []
    cursor = None
    while True:
        page = comments(limit=1, cursor=cursor)
        seen_comments.extend(thread.comment.id for thread in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    seen_replies = []
    cursor = None
    while True:
        page = replies(limit=1, cursor=cursor)
        seen_replies.extend(reply.id for reply in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen_comments == every_comment
    assert seen_replies == every_reply
    assert len(seen_comments) == len(set(seen_comments))
    assert len(seen_replies) == len(set(seen_replies))


def test_a_cursor_this_api_did_not_issue_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(InvalidCursorError):
        comments(cursor="no-es-un-cursor")
    with pytest.raises(InvalidCursorError):
        replies(cursor="no-es-un-cursor")


def test_a_photograph_without_conversation_is_not_an_error(seeded_database):
    del seeded_database
    quiet = PHOTO_FIXTURES[6]

    page = comments(photo_id=quiet.id)

    assert page.items == ()
    assert page.next_cursor is None
    assert photo_service.get_photo(quiet.id, viewer_id=OWNER.id).comments_count == 0
    # A comment that does not exist is not an empty list of replies.
    with pytest.raises(comment_service.CommentNotFoundError):
        replies(uuid4())
    # One that exists and was never answered, is.
    assert replies(WITHOUT_REPLIES.id).items == ()


def test_the_photograph_reports_how_many_comments_it_carries(seeded_database):
    del seeded_database

    metadata_count = photo_service.get_photo(TALKED_ABOUT.id, viewer_id=OWNER.id).comments_count
    gallery = photo_service.list_restaurant_photos(RESTAURANTS[0].id, viewer_id=OWNER.id, limit=50)
    in_gallery = {photo.id: photo.comments_count for photo in gallery.items}
    page = comments()

    assert metadata_count == in_gallery[TALKED_ABOUT.id] == len(COMMENT_FIXTURES)
    # The number counts the whole conversation, which is what the list shows:
    # the first-level comments plus every reply of each.
    assert metadata_count == len(page.items) + sum(thread.reply_count for thread in page.items)


def test_a_comment_is_not_activity(seeded_database, monkeypatch):
    del seeded_database
    notifications = []
    monkeypatch.setattr(notification_service, "_notifier", notifications.append)

    recipients_before = notification_service.resolve_recipients(
        author_id=PHOTO_AUTHOR.id, restaurant_id=RESTAURANTS[0].id, visibility="public"
    )
    before_feed = feed_service.get_feed(OWNER.id, limit=50)
    before_profile = user_service.get_activity(PHOTO_AUTHOR.handle, viewer_id=OWNER.id, limit=50)
    write("Nada de esto llega a ninguna parte.", author=PHOTO_AUTHOR)
    after_feed = feed_service.get_feed(OWNER.id, limit=50)
    after_profile = user_service.get_activity(PHOTO_AUTHOR.handle, viewer_id=OWNER.id, limit=50)

    # Not in the feed of somebody who follows the author, not on their
    # profile, and nobody is warned about it.
    assert after_feed["items"] == before_feed["items"]
    assert after_profile["items"] == before_profile["items"]
    assert notifications == []
    assert "comment" not in {item["type"] for item in after_feed["items"]}
    # And the recipients of what does warn are the ones they always were:
    # commenting adds nobody to that set and takes nobody out of it.
    assert (
        notification_service.resolve_recipients(
            author_id=PHOTO_AUTHOR.id, restaurant_id=RESTAURANTS[0].id, visibility="public"
        )
        == recipients_before
    )


def test_a_page_of_comments_does_not_cost_a_query_per_comment(seeded_database):
    for ordinal in range(20):
        write(f"Comentario {ordinal}.", author=STRANGER)

    statements = []

    def record(connection, cursor, statement, *rest):
        del connection, cursor, rest
        statements.append(statement)

    event.listen(seeded_database, "before_cursor_execute", record)
    try:
        page = comments(limit=20)
    finally:
        event.remove(seeded_database, "before_cursor_execute", record)

    assert len(page.items) == 20
    # One to authorize the photograph, one for the comments, one for every
    # reply of the page. Three, whatever the number of comments.
    assert len(statements) == 3


def test_the_endpoints_carry_the_thread_and_refuse_what_they_must(seeded_database):
    del seeded_database
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}

    anonymous = client.get(f"/api/v1/photos/{TALKED_ABOUT.id}/comments")
    anonymous_write = client.post(
        f"/api/v1/photos/{TALKED_ABOUT.id}/comments", json={"text": "Hola"}, headers=origin
    )
    app.dependency_overrides[get_current_session] = session
    try:
        listed = client.get(f"/api/v1/photos/{TALKED_ABOUT.id}/comments")
        thread = client.get(f"/api/v1/comments/{THREAD.id}/replies")
        created = client.post(
            f"/api/v1/photos/{TALKED_ABOUT.id}/comments",
            json={"text": "Anotado.", "parent_id": str(THREAD.id)},
            headers=origin,
        )
        untrusted = client.post(
            f"/api/v1/photos/{TALKED_ABOUT.id}/comments",
            json={"text": "Anotado."},
            headers={"Origin": "http://evil.example"},
        )
        blank = client.post(
            f"/api/v1/photos/{TALKED_ABOUT.id}/comments", json={"text": "   "}, headers=origin
        )
        unknown_photo = client.get(f"/api/v1/photos/{uuid4()}/comments")
        unknown_comment = client.get(f"/api/v1/comments/{uuid4()}/replies")
        bad_cursor = client.get(f"/api/v1/photos/{TALKED_ABOUT.id}/comments?cursor=roto")
        private = client.post(
            f"/api/v1/photos/{PRIVATE_PHOTO.id}/comments", json={"text": "Hola"}, headers=origin
        )
    finally:
        app.dependency_overrides.clear()

    assert anonymous.status_code == anonymous_write.status_code == 401
    assert untrusted.status_code == 403
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["items"][0]["comment"]["id"] == str(BY_THE_PHOTO_AUTHOR.id)
    oldest = payload["items"][-1]
    assert oldest["reply_count"] == 4
    assert len(oldest["replies"]) == comment_service.REPLY_PREVIEW
    assert oldest["comment"]["author"]["nationality"] == {"code": "CL", "name": "Chile"}
    assert thread.status_code == 200
    assert len(thread.json()["items"]) == 4
    assert created.status_code == 201
    assert created.headers["Location"] == f"/api/v1/comments/{created.json()['id']}"
    assert created.json()["parent_id"] == str(THREAD.id)
    assert blank.status_code == 422
    assert unknown_photo.status_code == unknown_comment.status_code == 404
    assert bad_cursor.status_code == 422
    assert private.status_code == 422


def test_store_failures_are_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(comment_service, "engine", BrokenEngine())
    with pytest.raises(comment_service.CommentStoreError):
        comments()
    with pytest.raises(comment_service.CommentStoreError):
        replies()
    with pytest.raises(comment_service.CommentStoreError):
        write()
