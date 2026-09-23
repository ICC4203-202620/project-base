from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, REVIEW_FIXTURES
from app.db.schema import metadata
from app.main import app
from app.services import feed as feed_service
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


def test_seeded_feed_includes_both_follow_types_once_and_excludes_private(seeded_database):
    del seeded_database

    page = feed_service.get_feed(DEMO_USERS[0].id, limit=20)
    review_ids = [item["review"]["id"] for item in page["items"]]

    assert review_ids == [
        REVIEW_FIXTURES[0].id,
        REVIEW_FIXTURES[1].id,
        REVIEW_FIXTURES[3].id,
    ]
    assert review_ids.count(REVIEW_FIXTURES[0].id) == 1
    assert REVIEW_FIXTURES[2].id not in review_ids
    assert page["next_cursor"] is None
    assert all(item["review"]["photo"]["content_url"].startswith("/api/") for item in page["items"])


def test_feed_cursor_pages_are_stable_and_invalid_cursor_is_rejected(seeded_database):
    del seeded_database
    seen = []
    cursor = None

    for expected_id in (REVIEW_FIXTURES[0].id, REVIEW_FIXTURES[1].id, REVIEW_FIXTURES[3].id):
        page = feed_service.get_feed(DEMO_USERS[0].id, limit=1, cursor=cursor)
        assert [item["review"]["id"] for item in page["items"]] == [expected_id]
        seen.extend(item["review"]["id"] for item in page["items"])
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
