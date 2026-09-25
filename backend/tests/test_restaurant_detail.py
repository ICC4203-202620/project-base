from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, RESTAURANTS, REVIEW_FIXTURES
from app.db.schema import metadata, photos, user_follows, users, visits
from app.main import app
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import users as user_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError

# Restaurant one holds the private review of `demo` and public ones by the
# other two accounts, which is what makes the difference between observers
# visible from the seed alone.
WITH_ACTIVITY = RESTAURANTS[0].id
PRIVATE_REVIEW = REVIEW_FIXTURES[2]
OWNER = DEMO_USERS[0]
OTHER = DEMO_USERS[1]
# `demo` follows these three. The first two left a public visit at the same
# restaurant, the third only a private one.
KNOWN = DEMO_USERS[1]
ALSO_KNOWN = DEMO_USERS[3]
DISCREET = DEMO_USERS[4]
# Public visit at the same restaurant, and nobody follows them.
STRANGER = DEMO_USERS[2]


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
    monkeypatch.setattr(seed_module, "engine", database)
    monkeypatch.setattr(restaurant_service, "engine", database)
    monkeypatch.setattr(photo_service, "engine", database)
    monkeypatch.setattr(user_service, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def detail(restaurant_id=WITH_ACTIVITY, viewer=OWNER):
    return restaurant_service.get_restaurant_detail(restaurant_id, viewer_id=viewer.id)


def gallery(restaurant_id=WITH_ACTIVITY, viewer=OWNER, limit=50, cursor=None):
    return photo_service.list_restaurant_photos(
        restaurant_id, viewer_id=viewer.id, limit=limit, cursor=cursor
    )


def known_visitors(restaurant_id=WITH_ACTIVITY, viewer=OWNER):
    return detail(restaurant_id, viewer).known_visitors


def session(user=OWNER):
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def add_followed_visitor(database, ordinal, *, when):
    """One more person the owner follows, with one public visit."""
    visitor_id = uuid4()
    with database.begin() as connection:
        connection.execute(
            insert(users).values(
                id=visitor_id,
                email=f"visitante{ordinal}@example.com",
                handle=f"visitante{ordinal}",
                name=f"Visitante {ordinal}",
                nationality="CL",
                password_hash="test-password-hash",
            )
        )
        connection.execute(
            insert(user_follows).values(follower_id=OWNER.id, followed_id=visitor_id)
        )
        connection.execute(
            insert(visits).values(
                id=uuid4(),
                author_id=visitor_id,
                restaurant_id=WITH_ACTIVITY,
                occurred_at=when,
                visibility="public",
                created_at=when,
            )
        )
    return visitor_id


def test_the_migration_left_every_photograph_with_its_review_visibility(seeded_database):
    with seeded_database.connect() as connection:
        stored = {
            row["id"]: (row["visibility"], row["kind"])
            for row in connection.execute(
                select(photos.c.id, photos.c.visibility, photos.c.kind)
            ).mappings()
        }

    assert stored[PRIVATE_REVIEW.photo_id] == ("private", "dish")
    for fixture in REVIEW_FIXTURES:
        assert stored[fixture.photo_id] == (fixture.visibility, "dish")


def test_the_page_carries_what_the_screen_needs_without_the_gallery(seeded_database):
    del seeded_database

    page = detail()

    assert page.id == WITH_ACTIVITY
    assert page.name == RESTAURANTS[0].name
    assert page.cuisine_styles
    assert page.counters.followers == 1
    assert page.viewer.following is True
    # Two public evaluations in the seed; the private one moves nothing.
    assert page.ratings.total == 2
    assert page.ratings.average == 3.8
    assert {criterion.criterion: criterion.average for criterion in page.ratings.criteria} == {
        "comida": 4.0,
        "servicio": 3.0,
        "ambiente": 4.5,
        "precio-calidad": 3.5,
    }
    assert page.counters.evaluations == page.ratings.total
    # Five public check-ins in the seed; the private one of another account
    # is not among them.
    assert page.counters.visits == 5
    assert not hasattr(page, "photos")


def test_a_restaurant_without_any_activity_is_not_an_error(seeded_database):
    del seeded_database
    quiet = RESTAURANTS[6].id

    page = detail(quiet)

    assert page.counters.photos == 0
    assert page.counters.reviews == 0
    assert page.counters.followers == 0
    assert page.viewer.following is False
    assert gallery(quiet).items == ()


def test_a_private_photograph_is_seen_by_its_author_and_by_nobody_else(seeded_database):
    del seeded_database

    seen_by_author = gallery(viewer=OWNER)
    seen_by_other = gallery(viewer=OTHER)

    assert PRIVATE_REVIEW.photo_id in {photo.id for photo in seen_by_author.items}
    assert PRIVATE_REVIEW.photo_id not in {photo.id for photo in seen_by_other.items}
    assert len(seen_by_author.items) == len(seen_by_other.items) + 1


def test_counters_match_what_each_observer_can_list(seeded_database):
    del seeded_database

    for viewer in (OWNER, OTHER, DEMO_USERS[2]):
        page = detail(viewer=viewer)
        assert page.counters.photos == len(gallery(viewer=viewer).items), viewer.handle


def test_the_gallery_says_which_review_a_photograph_carries(seeded_database):
    del seeded_database

    by_photo = {photo.id: photo for photo in gallery().items}

    assert by_photo[PRIVATE_REVIEW.photo_id].review_id == PRIVATE_REVIEW.id
    assert by_photo[PRIVATE_REVIEW.photo_id].kind == "dish"
    assert by_photo[PRIVATE_REVIEW.photo_id].author.handle == OWNER.handle
    assert by_photo[PRIVATE_REVIEW.photo_id].content_url.endswith(
        f"/api/v1/photos/{PRIVATE_REVIEW.photo_id}/content"
    )


def test_the_gallery_pages_by_cursor_without_repeating_or_skipping(seeded_database):
    del seeded_database
    every_photo = [photo.id for photo in gallery().items]
    assert len(every_photo) > 1

    seen = []
    cursor = None
    while True:
        page = gallery(limit=1, cursor=cursor)
        seen.extend(photo.id for photo in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == every_photo
    assert len(seen) == len(set(seen))


def test_a_cursor_this_api_did_not_issue_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(InvalidCursorError):
        gallery(cursor="no-es-un-cursor")


def test_an_unknown_restaurant_is_not_an_empty_page(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        detail(uuid4())


def test_store_failures_are_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    monkeypatch.setattr(photo_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        detail()
    with pytest.raises(photo_service.PhotoStoreError):
        gallery()


def test_the_page_says_who_the_viewer_follows_was_here_and_when(seeded_database):
    del seeded_database

    block = known_visitors()

    assert block.total == 2
    assert [visitor.handle for visitor in block.items] == [KNOWN.handle, ALSO_KNOWN.handle]
    # Ordered by the most recent visit of each person, which is what answers
    # «¿cuándo?».
    assert block.items[0].last_visit_at == datetime(2026, 8, 19, 20, tzinfo=UTC)
    assert block.items[1].last_visit_at == datetime(2026, 8, 14, 19, tzinfo=UTC)
    # The summary of a person, the same one a profile and the search return.
    assert block.items[0].name == KNOWN.name
    assert block.items[0].nationality.code == "AR"
    assert block.items[0].nationality.name == "Argentina"


def test_somebody_who_came_twice_appears_once_with_the_later_visit(seeded_database):
    del seeded_database

    block = known_visitors()

    assert [visitor.id for visitor in block.items].count(KNOWN.id) == 1
    # Two public visits in the seed: the older one does not show and does not
    # take a second slot either.
    assert block.items[0].last_visit_at == datetime(2026, 8, 19, 20, tzinfo=UTC)


def test_a_private_visit_of_somebody_followed_stays_out(seeded_database):
    del seeded_database

    block = known_visitors()

    # Theirs is the most recent visit of all: if the rule leaked, they would
    # lead the block.
    assert DISCREET.id not in {visitor.id for visitor in block.items}
    assert block.total == 2


def test_the_block_leaves_out_strangers_and_the_viewer_themselves(seeded_database):
    del seeded_database

    identifiers = {visitor.id for visitor in known_visitors().items}

    # A public visit, at this restaurant, by somebody the viewer does not
    # follow.
    assert STRANGER.id not in identifiers
    # And the viewer's own public visit here: the block is about other people.
    assert OWNER.id not in identifiers


def test_two_viewers_read_different_blocks_on_the_same_page(seeded_database):
    del seeded_database

    seen_by_owner = known_visitors(viewer=OWNER)
    seen_by_other = known_visitors(viewer=OTHER)

    assert seen_by_owner.total == 2
    # Follows nobody, although they were here themselves.
    assert seen_by_other.total == 0
    assert seen_by_other.items == ()


def test_following_nobody_is_an_empty_block_and_not_a_missing_one(seeded_database):
    del seeded_database

    block = known_visitors(viewer=STRANGER)

    assert block.total == 0
    assert block.items == ()


def test_more_people_than_the_block_names_are_counted_all_the_same(seeded_database):
    extra = restaurant_service.MAXIMUM_KNOWN_VISITORS + 3
    for ordinal in range(extra):
        add_followed_visitor(
            seeded_database, ordinal, when=datetime(2026, 9, 1 + ordinal, 12, tzinfo=UTC)
        )

    block = known_visitors()

    assert block.total == 2 + extra
    assert len(block.items) == restaurant_service.MAXIMUM_KNOWN_VISITORS
    # Cut by the date, so what the block names is the most recent.
    assert block.items[0].last_visit_at > block.items[-1].last_visit_at
    assert KNOWN.id not in {visitor.id for visitor in block.items}


def test_unfollowing_somebody_takes_them_out_of_the_block(seeded_database):
    del seeded_database

    user_service.unfollow_user(follower_id=OWNER.id, handle=KNOWN.handle)
    block = known_visitors()

    assert block.total == 1
    assert [visitor.handle for visitor in block.items] == [ALSO_KNOWN.handle]


def test_the_endpoint_carries_the_block_and_refuses_an_anonymous_request(seeded_database):
    del seeded_database
    client = TestClient(app)

    without_session = client.get(f"/api/v1/restaurants/{WITH_ACTIVITY}")
    app.dependency_overrides[get_current_session] = session
    try:
        response = client.get(f"/api/v1/restaurants/{WITH_ACTIVITY}")
    finally:
        app.dependency_overrides.clear()

    assert without_session.status_code == 401
    assert response.status_code == 200
    block = response.json()["known_visitors"]
    assert block["total"] == 2
    assert [visitor["handle"] for visitor in block["items"]] == [KNOWN.handle, ALSO_KNOWN.handle]
    assert block["items"][0]["nationality"] == {"code": "AR", "name": "Argentina"}
    assert block["items"][0]["last_visit_at"].startswith("2026-08-19T20:00:00")
