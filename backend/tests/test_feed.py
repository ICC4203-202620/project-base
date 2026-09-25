from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import (
    DEMO_USERS,
    EVALUATION_FIXTURES,
    PHOTO_FIXTURES,
    RESTAURANT_FOLLOWS,
    REVIEW_FIXTURES,
    VISIT_FIXTURES,
)
from app.db.schema import metadata
from app.main import app
from app.services import feed as feed_service
from app.services import users as user_service
from app.services.activity import ACTIVITY_SOURCES
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError
from app.services.reviews import ReviewNotFoundError, ReviewStoreError


class FixtureStorage:
    def store(self, *, media_id, stream, content_type, extension):
        assert content_type == "image/webp"
        assert stream.read(4) == b"RIFF"
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
    monkeypatch.setattr(feed_service, "engine", database)
    monkeypatch.setattr(user_service, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def session(user_index=0):
    user = DEMO_USERS[user_index]
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def activity_ids(page):
    # A photo item carries a collection of photographs, one in this épica.
    return [
        item["photo"]["photos"][0]["id"] if item["type"] == "photo" else item[item["type"]]["id"]
        for item in page["items"]
    ]


# What the seed puts in front of `demo`, ordered by the instant each activity
# was published. The backdated visit leads precisely because it was recorded
# last, which is the difference the feed orders by.
EXPECTED_FEED = [
    EVALUATION_FIXTURES[1].id,
    EVALUATION_FIXTURES[0].id,
    PHOTO_FIXTURES[6].id,
    PHOTO_FIXTURES[3].id,
    PHOTO_FIXTURES[1].id,
    PHOTO_FIXTURES[0].id,
    VISIT_FIXTURES[3].id,
    REVIEW_FIXTURES[0].id,
    VISIT_FIXTURES[2].id,
    VISIT_FIXTURES[0].id,
    REVIEW_FIXTURES[1].id,
    REVIEW_FIXTURES[3].id,
    VISIT_FIXTURES[6].id,
    VISIT_FIXTURES[5].id,
]


def test_seeded_feed_mixes_both_classes_once_and_excludes_private(seeded_database):
    del seeded_database

    page = feed_service.get_feed(DEMO_USERS[0].id, limit=20)
    ids = activity_ids(page)

    assert ids == EXPECTED_FEED
    # The first review matches both follow criteria and still appears once.
    assert ids.count(REVIEW_FIXTURES[0].id) == 1
    assert REVIEW_FIXTURES[2].id not in ids
    assert VISIT_FIXTURES[1].id not in ids
    assert {item["type"] for item in page["items"]} == {
        "review",
        "visit",
        "photo",
        "evaluation",
    }
    # The private evaluation of another account never reaches this feed.
    assert EVALUATION_FIXTURES[2].id not in ids
    # The private photograph of another account never reaches this feed.
    assert PHOTO_FIXTURES[2].id not in ids
    assert page["next_cursor"] is None
    assert all(
        item["review"]["photo"]["content_url"].startswith("/api/")
        for item in page["items"]
        if item["type"] == "review"
    )


def test_a_backdated_visit_reaches_the_feed_at_the_top(seeded_database):
    del seeded_database
    backdated = VISIT_FIXTURES[3]

    page = feed_service.get_feed(DEMO_USERS[0].id, limit=20)
    first = next(item for item in page["items"] if item["type"] == "visit")

    assert first["visit"]["id"] == backdated.id
    # It happened over a month before the activity around it, and was
    # published after all of it.
    assert first["occurred_at"] < min(
        item["occurred_at"] for item in page["items"] if item is not first
    )
    assert first["published_at"] > min(
        item["published_at"] for item in page["items"] if item is not first
    )


def test_feed_cursor_pages_are_stable_and_invalid_cursor_is_rejected(seeded_database):
    del seeded_database
    seen = []
    cursor = None

    for expected_id in EXPECTED_FEED:
        page = feed_service.get_feed(DEMO_USERS[0].id, limit=1, cursor=cursor)
        assert activity_ids(page) == [expected_id]
        seen.extend(activity_ids(page))
        cursor = page["next_cursor"]

    assert len(seen) == len(set(seen))
    assert cursor is None
    assert feed_service.get_feed(DEMO_USERS[0].id, limit=1, cursor=None)["items"]
    with pytest.raises(InvalidCursorError):
        feed_service.get_feed(DEMO_USERS[0].id, limit=1, cursor="not-a-cursor")


def test_private_review_detail_is_visible_only_to_author(seeded_database):
    del seeded_database
    private = REVIEW_FIXTURES[2]

    detail = feed_service.get_review(private.id, viewer_id=private.author_id)

    assert detail["id"] == private.id
    assert detail["visibility"] == "private"
    with pytest.raises(ReviewNotFoundError):
        feed_service.get_review(private.id, viewer_id=DEMO_USERS[1].id)
    with pytest.raises(ReviewNotFoundError):
        feed_service.get_review(uuid4(), viewer_id=DEMO_USERS[0].id)


def test_empty_feed_and_store_failure(seeded_database, monkeypatch):
    del seeded_database
    assert feed_service.get_feed(DEMO_USERS[2].id, limit=20) == {
        "items": [],
        "next_cursor": None,
    }

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(feed_service, "engine", BrokenEngine())
    with pytest.raises(ReviewStoreError):
        feed_service.get_feed(DEMO_USERS[0].id, limit=20)
    with pytest.raises(ReviewStoreError):
        feed_service.get_review(REVIEW_FIXTURES[0].id, viewer_id=DEMO_USERS[0].id)


def test_feed_routes_require_authentication():
    client = TestClient(app)

    assert client.get("/api/v1/feed").status_code == 401
    assert client.get(f"/api/v1/reviews/{REVIEW_FIXTURES[0].id}").status_code == 401


def test_feed_routes_validate_and_map_domain_errors(monkeypatch):
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    try:
        monkeypatch.setattr(
            feed_service,
            "get_feed",
            lambda *args, **kwargs: (_ for _ in ()).throw(InvalidCursorError()),
        )
        assert client.get("/api/v1/feed?cursor=invalid").status_code == 422

        monkeypatch.setattr(
            feed_service,
            "get_review",
            lambda *args, **kwargs: (_ for _ in ()).throw(ReviewNotFoundError()),
        )
        assert client.get(f"/api/v1/reviews/{uuid4()}").status_code == 404

        monkeypatch.setattr(
            feed_service,
            "get_feed",
            lambda *args, **kwargs: (_ for _ in ()).throw(ReviewStoreError()),
        )
        assert client.get("/api/v1/feed").status_code == 503
        assert client.get("/api/v1/feed?limit=51").status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- What the feed contains, and what it does not -----------------------------


def test_the_feed_holds_every_class_of_activity_with_one_shape(seeded_database):
    del seeded_database

    page = feed_service.get_feed(DEMO_USERS[0].id, limit=50)

    assert {item["type"] for item in page["items"]} == {
        "review",
        "visit",
        "photo",
        "evaluation",
    }
    for item in page["items"]:
        # A screen walks the list by `type` without knowing which classes
        # exist, and every item answers the same three questions.
        assert set(item) == {"type", "occurred_at", "published_at", item["type"]}
        assert item["occurred_at"] and item["published_at"]
        assert item[item["type"]]["author"]["handle"]
        assert item[item["type"]]["restaurant"]["id"]


def test_the_feed_is_ordered_by_the_instant_of_publication(seeded_database):
    del seeded_database

    published = [
        item["published_at"] for item in feed_service.get_feed(DEMO_USERS[0].id, limit=50)["items"]
    ]

    assert published == sorted(published, reverse=True)


def test_nobody_reads_their_own_activity_in_their_feed(seeded_database):
    del seeded_database
    owner = DEMO_USERS[0]
    own_public_visit = VISIT_FIXTURES[4]

    feed = feed_service.get_feed(owner.id, limit=50)
    profile = user_service.get_activity(owner.handle, viewer_id=owner.id, limit=50)

    # It happened at a restaurant they follow, so the follow condition matches
    # and only the author condition keeps it out.
    assert own_public_visit.restaurant_id == RESTAURANT_FOLLOWS[0][1]
    assert own_public_visit.id not in activity_ids(feed)
    assert own_public_visit.id in [
        item[item["type"]]["id"] for item in profile["items"] if item["type"] == "visit"
    ]
    assert all(
        item[item["type"]]["author"]["id"] != owner.id
        for item in feed["items"]
        if item["type"] != "photo"
    )


def test_an_empty_feed_is_not_an_error(seeded_database):
    del seeded_database
    # `la_sibarita` follows nobody and no restaurant.
    lonely = DEMO_USERS[4]

    page = feed_service.get_feed(lonely.id, limit=50)

    assert page == {"items": [], "next_cursor": None}


def test_a_page_costs_one_query_whatever_the_number_of_classes(seeded_database):
    statements = []

    def record(connection, cursor, statement, *rest):
        del connection, cursor, rest
        statements.append(statement)

    event.listen(seeded_database, "before_cursor_execute", record)
    try:
        page = feed_service.get_feed(DEMO_USERS[0].id, limit=50)
    finally:
        event.remove(seeded_database, "before_cursor_execute", record)

    # One query unions the keys of every source, and then the classes present
    # in the page are read, one query each — an evaluation adds two more for
    # its ratings and its photographs, both grouped. What matters is that
    # nothing here is per row: the page holds more items than it cost queries.
    assert len(page["items"]) > len(statements)
    assert len(statements) <= 1 + 3 * len(ACTIVITY_SOURCES)
