from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, RESTAURANTS
from app.db.schema import metadata
from app.main import app
from app.media.storage import LocalMediaLocation
from app.services import evaluations as evaluation_service
from app.services import notifications as notification_service
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import reviews as review_service
from app.services import users as user_service
from app.services import visits as visit_service
from app.services.auth import AuthenticatedSession

# `demo` follows `demo2` and restaurant one. `empty` follows nobody.
FOLLOWER = DEMO_USERS[0]
AUTHOR = DEMO_USERS[1]
STRANGER = DEMO_USERS[2]
FOLLOWED_RESTAURANT = RESTAURANTS[0].id
OTHER_RESTAURANT = RESTAURANTS[6].id
FULL_RATINGS = {"comida": 5, "servicio": 4, "ambiente": 3, "precio-calidad": 4}


class MemoryStorage:
    def store(self, *, media_id, stream, content_type, extension):
        stream.read()
        return f"photos/{media_id}.{extension}"

    def delete(self, storage_key):
        del storage_key

    def resolve(self, storage_key):
        return LocalMediaLocation(path=storage_key)


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
        notification_service,
        visit_service,
        photo_service,
        review_service,
        evaluation_service,
        restaurant_service,
        user_service,
    ):
        monkeypatch.setattr(module, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=MemoryStorage())
    return database


@pytest.fixture
def sent(monkeypatch):
    """Install an emitter the way a group would, and record what it receives."""
    notifications = []
    notification_service.set_notifier(notifications.append)
    monkeypatch.setattr(notification_service, "_notifier", notifications.append)
    yield notifications
    notification_service.set_notifier(None)


def session(user=AUTHOR):
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def png_file() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(stream, format="PNG")
    stream.seek(0)
    return stream


def check_in(visibility="public", restaurant_id=FOLLOWED_RESTAURANT, author=AUTHOR):
    return visit_service.create_visit(
        author_id=author.id,
        restaurant_id=restaurant_id,
        visibility=visibility,
        occurred_at=None,
    )


def publish(visibility="public", restaurant_id=FOLLOWED_RESTAURANT, **overrides):
    arguments = {
        "author_id": AUTHOR.id,
        "restaurant_id": restaurant_id,
        "kind": "menu",
        "dish_name": None,
        "caption": None,
        "visibility": visibility,
        "photo_stream": png_file(),
        "declared_content_type": "image/png",
        "storage": MemoryStorage(),
    }
    arguments.update(overrides)
    return photo_service.store_photo(**arguments)


# --- Who should hear about an activity ---------------------------------------


def test_a_public_activity_reaches_followers_of_the_author_and_of_the_restaurant(
    seeded_database,
):
    del seeded_database

    by_author = notification_service.resolve_recipients(
        author_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT, visibility="public"
    )
    by_restaurant = notification_service.resolve_recipients(
        author_id=STRANGER.id, restaurant_id=FOLLOWED_RESTAURANT, visibility="public"
    )

    assert FOLLOWER.id in by_author
    assert FOLLOWER.id in by_restaurant


def test_somebody_who_follows_both_is_one_recipient(seeded_database):
    del seeded_database

    recipients = notification_service.resolve_recipients(
        author_id=AUTHOR.id, restaurant_id=FOLLOWED_RESTAURANT, visibility="public"
    )

    assert list(recipients).count(FOLLOWER.id) == 1


def test_the_author_is_never_a_recipient_of_their_own_activity(seeded_database):
    del seeded_database
    # The author follows the restaurant they publish at.
    restaurant_service.follow_restaurant(user_id=AUTHOR.id, restaurant_id=FOLLOWED_RESTAURANT)

    recipients = notification_service.resolve_recipients(
        author_id=AUTHOR.id, restaurant_id=FOLLOWED_RESTAURANT, visibility="public"
    )

    assert AUTHOR.id not in recipients


def test_a_private_activity_reaches_nobody(seeded_database):
    del seeded_database

    assert (
        notification_service.resolve_recipients(
            author_id=AUTHOR.id, restaurant_id=FOLLOWED_RESTAURANT, visibility="private"
        )
        == ()
    )


def test_an_activity_nobody_follows_is_not_an_error(seeded_database):
    del seeded_database

    assert (
        notification_service.resolve_recipients(
            author_id=STRANGER.id, restaurant_id=OTHER_RESTAURANT, visibility="public"
        )
        == ()
    )


# --- Where the emitter is plugged in ------------------------------------------


def test_every_class_of_activity_announces_itself(seeded_database, sent):
    del seeded_database

    check_in()
    publish()
    photo = publish(kind="dish", dish_name="Merluza austral")
    review_service.create_review(
        author_id=AUTHOR.id,
        photo_id=photo.id,
        rating=4,
        text="Muy fresco",
        visibility="public",
    )
    # This author already evaluated the followed restaurant in the seed, so
    # this one goes to another of the same followed author.
    evaluation_service.create_evaluation(
        author_id=AUTHOR.id,
        restaurant_id=OTHER_RESTAURANT,
        ratings=FULL_RATINGS,
        comment="Muy bien",
        visibility="public",
    )

    assert [notification.type for notification in sent] == [
        "visit",
        "photo",
        "photo",
        "review",
        "evaluation",
    ]
    assert all(FOLLOWER.id in notification.recipients for notification in sent)


def test_a_group_of_photographs_announces_itself_once(seeded_database, sent):
    del seeded_database
    upload_group = uuid4()

    for _ in range(3):
        publish(upload_group=upload_group)

    assert len(sent) == 1
    # The act is named by its group, not by one of its photographs.
    assert sent[0].id == upload_group


def test_a_private_activity_announces_nothing(seeded_database, sent):
    del seeded_database

    check_in(visibility="private")
    publish(visibility="private")

    assert sent == []


def test_an_activity_that_failed_announces_nothing(seeded_database, sent):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        check_in(restaurant_id=uuid4())

    assert sent == []


def test_a_failing_emitter_does_not_undo_the_activity(seeded_database, monkeypatch):
    del seeded_database

    def broken(notification):
        raise RuntimeError("push provider unavailable")

    monkeypatch.setattr(notification_service, "_notifier", broken)

    visit = check_in()

    assert visit_service.get_visit(visit.id, viewer_id=AUTHOR.id)["id"] == visit.id


def test_without_an_emitter_nothing_is_resolved(seeded_database, monkeypatch):
    del seeded_database
    asked = []

    monkeypatch.setattr(notification_service, "_notifier", None)
    monkeypatch.setattr(
        notification_service,
        "resolve_recipients",
        lambda **kwargs: asked.append(kwargs) or (),
    )

    check_in()

    assert asked == []


# --- Following a restaurant ---------------------------------------------------


def follows(user, restaurant_id):
    return restaurant_service.get_restaurant_detail(
        restaurant_id, viewer_id=user.id
    ).viewer.following


def test_following_a_restaurant_is_reversible_and_idempotent(seeded_database):
    del seeded_database

    assert follows(AUTHOR, OTHER_RESTAURANT) is False
    restaurant_service.follow_restaurant(user_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT)
    restaurant_service.follow_restaurant(user_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT)
    assert follows(AUTHOR, OTHER_RESTAURANT) is True

    restaurant_service.unfollow_restaurant(user_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT)
    restaurant_service.unfollow_restaurant(user_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT)
    assert follows(AUTHOR, OTHER_RESTAURANT) is False


def test_following_a_restaurant_that_does_not_exist(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        restaurant_service.follow_restaurant(user_id=AUTHOR.id, restaurant_id=uuid4())
    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        restaurant_service.unfollow_restaurant(user_id=AUTHOR.id, restaurant_id=uuid4())


def test_following_a_restaurant_changes_the_feed_and_the_recipients(seeded_database):
    del seeded_database

    before = notification_service.resolve_recipients(
        author_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT, visibility="public"
    )
    restaurant_service.follow_restaurant(user_id=STRANGER.id, restaurant_id=OTHER_RESTAURANT)
    after = notification_service.resolve_recipients(
        author_id=AUTHOR.id, restaurant_id=OTHER_RESTAURANT, visibility="public"
    )

    assert STRANGER.id not in before
    assert STRANGER.id in after


def test_store_failures_are_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        restaurant_service.follow_restaurant(user_id=AUTHOR.id, restaurant_id=FOLLOWED_RESTAURANT)


def test_the_endpoints_answer_204_whatever_the_previous_state(seeded_database):
    del seeded_database
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}
    try:
        first = client.put(f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow", headers=origin)
        repeated = client.put(f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow", headers=origin)
        page = client.get(f"/api/v1/restaurants/{OTHER_RESTAURANT}").json()
        removed = client.delete(f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow", headers=origin)
        removed_again = client.delete(
            f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow", headers=origin
        )
        unknown = client.put(f"/api/v1/restaurants/{uuid4()}/follow", headers=origin)
        untrusted = client.put(
            f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow",
            headers={"Origin": "http://evil.example"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == repeated.status_code == 204
    assert page["viewer"]["following"] is True
    assert page["counters"]["followers"] == 1
    assert removed.status_code == removed_again.status_code == 204
    assert unknown.status_code == 404
    assert untrusted.status_code == 403


def test_the_follow_routes_require_a_session():
    client = TestClient(app)

    assert client.put(f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow").status_code == 401
    assert client.delete(f"/api/v1/restaurants/{OTHER_RESTAURANT}/follow").status_code == 401
