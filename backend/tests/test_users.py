from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, REVIEW_FIXTURES
from app.db.schema import metadata, users
from app.main import app
from app.services import users as user_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError

OWNER = DEMO_USERS[0]  # demo: one private review, follows demo2
AUTHOR = DEMO_USERS[1]  # demo2: two public reviews
OTHER = DEMO_USERS[2]  # empty: one public review, follows nobody


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
    return [item["review"]["id"] for item in page["items"]]


def test_owner_sees_private_activity_and_counts_it(seeded_database):
    del seeded_database
    private_review = REVIEW_FIXTURES[2]

    profile = user_service.get_profile(OWNER.handle, viewer_id=OWNER.id)
    page = user_service.get_activity(OWNER.handle, viewer_id=OWNER.id, limit=20)

    assert profile.handle == OWNER.handle
    assert profile.name == OWNER.name
    assert profile.counters.activity == 1
    assert activity_ids(page) == [private_review.id]
    assert page["items"][0]["review"]["visibility"] == "private"
    assert profile.viewer.is_self is True


def test_third_party_sees_neither_the_private_activity_nor_its_count(seeded_database):
    del seeded_database

    profile = user_service.get_profile(OWNER.handle, viewer_id=AUTHOR.id)
    page = user_service.get_activity(OWNER.handle, viewer_id=AUTHOR.id, limit=20)

    assert profile.counters.activity == 0
    assert page["items"] == []
    assert page["next_cursor"] is None
    assert profile.viewer.is_self is False


def test_counters_match_what_the_viewer_can_list(seeded_database):
    del seeded_database

    for viewer in (OWNER, AUTHOR, OTHER):
        for owner in (OWNER, AUTHOR, OTHER):
            profile = user_service.get_profile(owner.handle, viewer_id=viewer.id)
            page = user_service.get_activity(owner.handle, viewer_id=viewer.id, limit=50)
            assert profile.counters.activity == len(page["items"]), (viewer.handle, owner.handle)


def test_activity_envelope_carries_both_instants(seeded_database):
    del seeded_database

    page = user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=20)
    item = page["items"][0]

    assert item["type"] == "review"
    assert item["occurred_at"] == item["published_at"] == item["review"]["created_at"]


def test_profile_resolves_the_nationality_and_the_join_date(seeded_database):
    del seeded_database

    profile = user_service.get_profile(AUTHOR.handle, viewer_id=OWNER.id)

    assert profile.nationality.code == "AR"
    assert profile.nationality.name == "Argentina"
    assert profile.joined_at.tzinfo is not None


def test_handle_is_resolved_however_it_is_written(seeded_database):
    del seeded_database

    for written in (
        AUTHOR.handle,
        AUTHOR.handle.upper(),
        f"@{AUTHOR.handle}",
        f" @{AUTHOR.handle} ",
    ):
        profile = user_service.get_profile(written, viewer_id=OWNER.id)
        page = user_service.get_activity(written, viewer_id=OWNER.id, limit=20)
        assert profile.handle == AUTHOR.handle, written
        assert len(page["items"]) == 2, written


def test_unknown_handle_is_not_an_empty_profile(seeded_database):
    del seeded_database

    with pytest.raises(user_service.UserNotFoundError):
        user_service.get_profile("nadie_aqui", viewer_id=OWNER.id)
    with pytest.raises(user_service.UserNotFoundError):
        user_service.get_activity("nadie_aqui", viewer_id=OWNER.id, limit=20)


def test_profile_without_any_activity(seeded_database):
    newcomer_id = uuid4()
    with seeded_database.connect() as connection:
        connection.execute(
            insert(users).values(
                id=newcomer_id,
                email="recien@example.com",
                handle="recien",
                name="Recién Llegada",
                nationality="CL",
                password_hash="test-password-hash",
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        connection.commit()

    profile = user_service.get_profile("recien", viewer_id=OWNER.id)
    page = user_service.get_activity("recien", viewer_id=OWNER.id, limit=20)

    assert profile.counters == user_service.ProfileCounters(activity=0, followers=0, following=0)
    assert page == {"items": [], "next_cursor": None}


def test_follow_state_is_reported_in_both_directions(seeded_database):
    del seeded_database

    seen_by_follower = user_service.get_profile(AUTHOR.handle, viewer_id=OWNER.id)
    seen_by_followed = user_service.get_profile(OWNER.handle, viewer_id=AUTHOR.id)
    own = user_service.get_profile(OWNER.handle, viewer_id=OWNER.id)

    assert (seen_by_follower.viewer.following, seen_by_follower.viewer.followed_by) == (True, False)
    assert (seen_by_followed.viewer.following, seen_by_followed.viewer.followed_by) == (False, True)
    assert (own.viewer.following, own.viewer.followed_by, own.viewer.is_self) == (
        False,
        False,
        True,
    )
    assert seen_by_follower.counters.followers == 1
    assert own.counters.following == 1


def test_activity_pages_are_stable_and_reject_a_foreign_cursor(seeded_database):
    del seeded_database
    expected = [REVIEW_FIXTURES[0].id, REVIEW_FIXTURES[1].id]
    seen = []
    cursor = None

    for expected_id in expected:
        page = user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=1, cursor=cursor)
        assert activity_ids(page) == [expected_id]
        seen.extend(activity_ids(page))
        cursor = page["next_cursor"]

    assert seen == expected
    assert cursor is None
    with pytest.raises(InvalidCursorError):
        user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=1, cursor="no-cursor")


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(user_service, "engine", BrokenEngine())
    with pytest.raises(user_service.UserStoreError):
        user_service.get_profile(OWNER.handle, viewer_id=OWNER.id)
    with pytest.raises(user_service.UserStoreError):
        user_service.get_activity(OWNER.handle, viewer_id=OWNER.id, limit=20)


def test_user_routes_require_authentication():
    client = TestClient(app)

    assert client.get(f"/api/v1/users/{OWNER.handle}").status_code == 401
    assert client.get(f"/api/v1/users/{OWNER.handle}/activity").status_code == 401


def test_user_routes_map_domain_errors_and_validate_their_parameters(monkeypatch):
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    try:
        monkeypatch.setattr(
            user_service,
            "get_profile",
            lambda *args, **kwargs: (_ for _ in ()).throw(user_service.UserNotFoundError()),
        )
        assert client.get("/api/v1/users/nadie").status_code == 404

        monkeypatch.setattr(
            user_service,
            "get_activity",
            lambda *args, **kwargs: (_ for _ in ()).throw(InvalidCursorError()),
        )
        assert client.get(f"/api/v1/users/{OWNER.handle}/activity?cursor=x").status_code == 422

        monkeypatch.setattr(
            user_service,
            "get_profile",
            lambda *args, **kwargs: (_ for _ in ()).throw(user_service.UserStoreError()),
        )
        assert client.get(f"/api/v1/users/{OWNER.handle}").status_code == 503
        assert client.get(f"/api/v1/users/{OWNER.handle}/activity?limit=51").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_profile_response_shape_is_what_the_interface_needs(seeded_database, monkeypatch):
    del seeded_database
    app.dependency_overrides[get_current_session] = lambda: session(0)
    try:
        response = TestClient(app).get(f"/api/v1/users/{AUTHOR.handle}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["handle"] == AUTHOR.handle
    assert payload["nationality"] == {"code": "AR", "name": "Argentina"}
    assert payload["counters"] == {"activity": 2, "followers": 1, "following": 0}
    assert payload["viewer"] == {"is_self": False, "following": True, "followed_by": False}
