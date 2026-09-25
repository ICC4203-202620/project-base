from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import (
    DEMO_USERS,
    EVALUATION_FIXTURES,
    PHOTO_FIXTURES,
    RESTAURANTS,
    REVIEW_FIXTURES,
    VISIT_FIXTURES,
)
from app.db.schema import metadata, photos, users, visits
from app.main import app
from app.services import feed as feed_service
from app.services import users as user_service
from app.services.activity import ACTIVITY_SOURCES
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


def activity_ids(page):
    # A photo item carries a collection of photographs, one in this épica.
    return [
        item["photo"]["photos"][0]["id"] if item["type"] == "photo" else item[item["type"]]["id"]
        for item in page["items"]
    ]


def test_owner_sees_private_activity_and_counts_it(seeded_database):
    del seeded_database
    private_review = REVIEW_FIXTURES[2]
    private_visit = VISIT_FIXTURES[1]
    private_photo = PHOTO_FIXTURES[2]
    private_evaluation = EVALUATION_FIXTURES[2]

    profile = user_service.get_profile(OWNER.handle, viewer_id=OWNER.id)
    page = user_service.get_activity(OWNER.handle, viewer_id=OWNER.id, limit=20)

    assert profile.handle == OWNER.handle
    assert profile.name == OWNER.name
    # Four private and one public: the profile shows everything of its owner.
    assert profile.counters.activity == 5
    assert {
        private_review.id,
        private_visit.id,
        private_photo.id,
        private_evaluation.id,
    } <= set(activity_ids(page))
    assert {item["type"] for item in page["items"]} == {
        "review",
        "visit",
        "photo",
        "evaluation",
    }
    assert profile.viewer.is_self is True


def test_third_party_sees_neither_the_private_activity_nor_its_count(seeded_database):
    del seeded_database

    profile = user_service.get_profile(OWNER.handle, viewer_id=AUTHOR.id)
    page = user_service.get_activity(OWNER.handle, viewer_id=AUTHOR.id, limit=20)

    # Only the public visit of the owner, none of their four private ones.
    assert profile.counters.activity == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["visit"]["visibility"] == "public"
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
    review = next(item for item in page["items"] if item["type"] == "review")
    backdated_visit = page["items"][-1]

    assert review["occurred_at"] == review["published_at"] == review["review"]["created_at"]
    # A visit recorded long after it happened keeps both instants apart, and
    # the profile places it by the first one.
    assert backdated_visit["type"] == "visit"
    assert backdated_visit["occurred_at"] < backdated_visit["published_at"]


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
        assert len(page["items"]) == 8, written


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
    assert own.counters.following == 3


def test_activity_pages_are_stable_and_reject_a_foreign_cursor(seeded_database):
    del seeded_database
    # Ordered by when each activity happened, which is what a profile is. The
    # backdated visit comes last here and first in the feed.
    expected = [
        EVALUATION_FIXTURES[0].id,
        # The three menu photographs are one act, dated by the earliest.
        PHOTO_FIXTURES[3].id,
        PHOTO_FIXTURES[0].id,
        REVIEW_FIXTURES[0].id,
        VISIT_FIXTURES[0].id,
        REVIEW_FIXTURES[1].id,
        VISIT_FIXTURES[5].id,
        VISIT_FIXTURES[3].id,
    ]
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
    # Eight acts, not ten rows: the three menu photographs are one publication.
    assert payload["counters"] == {"activity": 8, "followers": 1, "following": 0}
    assert payload["viewer"] == {"is_self": False, "following": True, "followed_by": False}


# --- Finding people by handle -------------------------------------------------


def search(term, viewer=OWNER, **kwargs):
    return user_service.search_users(
        query=term, viewer_id=viewer.id, limit=kwargs.pop("limit", 50), **kwargs
    )


def handles(page):
    return [result.handle for result in page.items]


def test_search_matches_a_prefix_and_a_term_inside_the_handle(seeded_database):
    del seeded_database

    assert handles(search("demo")) == ["demo", "demo2", "demo_viajera"]
    assert handles(search("sibarita")) == ["la_sibarita"]
    assert handles(search("nadie")) == []


def test_the_term_is_read_the_way_a_handle_is_written(seeded_database):
    del seeded_database

    for written in ("@demo2", "DEMO2", " @Demo2 "):
        assert handles(search(written)) == ["demo2"], written


def test_a_term_that_would_return_the_register_is_rejected(seeded_database):
    del seeded_database

    for term in ("", "   ", "d", "@d"):
        with pytest.raises(user_service.SearchTermTooShortError):
            search(term)


def test_wildcards_typed_by_the_user_are_not_wildcards(seeded_database):
    del seeded_database

    assert handles(search("%%")) == []
    assert handles(search("__")) == []


def test_results_carry_the_follow_state_in_both_directions(seeded_database):
    del seeded_database

    seen_by_follower = {result.handle: result.following for result in search("demo").items}
    seen_by_followed = {
        result.handle: result.following for result in search("demo", viewer=AUTHOR).items
    }

    assert seen_by_follower[AUTHOR.handle] is True
    assert seen_by_follower[OWNER.handle] is False
    # The viewer appears among their own results, and does not follow themself.
    assert seen_by_followed[AUTHOR.handle] is False
    assert seen_by_followed[OWNER.handle] is False


def test_results_carry_the_shared_summary_of_a_person(seeded_database):
    del seeded_database

    result = next(item for item in search("demo2").items if item.handle == AUTHOR.handle)

    assert result.name == AUTHOR.name
    assert result.nationality.code == "AR"
    assert result.nationality.name == "Argentina"
    assert not hasattr(result, "email")


def test_search_pages_by_cursor_without_repeating_or_skipping(seeded_database):
    del seeded_database
    every = handles(search("demo"))

    seen = []
    cursor = None
    while True:
        page = search("demo", limit=1, cursor=cursor)
        seen.extend(handles(page))
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == every
    assert len(seen) == len(set(seen))


def test_a_cursor_this_api_did_not_issue_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(InvalidCursorError):
        search("demo", cursor="no-es-un-cursor")


def test_search_failures_are_reported_as_store_errors(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(user_service, "engine", BrokenEngine())
    with pytest.raises(user_service.UserStoreError):
        search("demo")


def test_the_search_endpoint_answers_the_contract(seeded_database):
    del seeded_database
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    try:
        found = client.get("/api/v1/users?q=@Demo2")
        short = client.get("/api/v1/users?q=d")
        broken_cursor = client.get("/api/v1/users?q=demo&cursor=roto")
        empty = client.get("/api/v1/users?q=nadie_asi")
    finally:
        app.dependency_overrides.clear()

    assert found.status_code == 200
    result = found.json()["items"][0]
    assert result["handle"] == AUTHOR.handle
    assert result["nationality"] == {"code": "AR", "name": "Argentina"}
    assert result["following"] is True
    assert "email" not in result
    assert short.status_code == 422
    assert short.json()["detail"][0]["loc"] == ["query", "q"]
    assert broken_cursor.status_code == 422
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None}


def test_the_search_requires_a_session():
    assert TestClient(app).get("/api/v1/users?q=demo").status_code == 401


# --- Following and unfollowing ------------------------------------------------


def follow(handle, follower=OTHER):
    return user_service.follow_user(follower_id=follower.id, handle=handle)


def unfollow(handle, follower=OTHER):
    return user_service.unfollow_user(follower_id=follower.id, handle=handle)


def follows(follower, followed):
    return user_service.get_profile(followed.handle, viewer_id=follower.id).viewer.following


def test_following_and_unfollowing_are_reversible(seeded_database):
    del seeded_database

    assert follows(OTHER, OWNER) is False
    follow(OWNER.handle)
    assert follows(OTHER, OWNER) is True
    unfollow(OWNER.handle)
    assert follows(OTHER, OWNER) is False


def test_both_operations_are_idempotent(seeded_database):
    del seeded_database

    follow(OWNER.handle)
    follow(OWNER.handle)
    assert follows(OTHER, OWNER) is True

    unfollow(OWNER.handle)
    unfollow(OWNER.handle)
    assert follows(OTHER, OWNER) is False


def test_the_handle_is_read_however_it_is_written(seeded_database):
    del seeded_database

    follow(f"@{OWNER.handle.upper()}")

    assert follows(OTHER, OWNER) is True


def test_nobody_follows_themself(seeded_database):
    del seeded_database

    with pytest.raises(user_service.SelfFollowError):
        follow(OTHER.handle)


def test_an_unknown_handle_is_not_a_silent_success(seeded_database):
    del seeded_database

    with pytest.raises(user_service.UserNotFoundError):
        follow("nadie_aqui")
    with pytest.raises(user_service.UserNotFoundError):
        unfollow("nadie_aqui")


def test_following_changes_what_the_feed_shows(seeded_database):
    del seeded_database
    # `empty` follows nobody, so its feed starts empty.
    lonely = DEMO_USERS[2]

    before = feed_service.get_feed(lonely.id, limit=50)
    user_service.follow_user(follower_id=lonely.id, handle=AUTHOR.handle)
    after = feed_service.get_feed(lonely.id, limit=50)

    assert before["items"] == []
    assert after["items"]

    user_service.unfollow_user(follower_id=lonely.id, handle=AUTHOR.handle)
    assert feed_service.get_feed(lonely.id, limit=50)["items"] == []


def test_the_search_results_reflect_the_change(seeded_database):
    del seeded_database

    follow(OWNER.handle)
    found = next(
        result for result in search("demo", viewer=OTHER).items if result.handle == OWNER.handle
    )

    assert found.following is True


def test_follow_failures_are_reported_as_store_errors(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(user_service, "engine", BrokenEngine())
    with pytest.raises(user_service.UserStoreError):
        follow(OWNER.handle)
    with pytest.raises(user_service.UserStoreError):
        unfollow(OWNER.handle)


def test_the_endpoints_answer_204_whatever_the_previous_state(seeded_database):
    del seeded_database
    app.dependency_overrides[get_current_session] = lambda: session(1)
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}
    try:
        first = client.put(f"/api/v1/users/{OWNER.handle}/follow", headers=origin)
        repeated = client.put(f"/api/v1/users/{OWNER.handle}/follow", headers=origin)
        profile = client.get(f"/api/v1/users/{OWNER.handle}").json()
        removed = client.delete(f"/api/v1/users/{OWNER.handle}/follow", headers=origin)
        removed_again = client.delete(f"/api/v1/users/{OWNER.handle}/follow", headers=origin)
        oneself = client.put(f"/api/v1/users/{AUTHOR.handle}/follow", headers=origin)
        unknown = client.put("/api/v1/users/nadie_aqui/follow", headers=origin)
        untrusted = client.put(
            f"/api/v1/users/{OWNER.handle}/follow",
            headers={"Origin": "http://evil.example"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == repeated.status_code == 204
    assert first.content == b""
    assert profile["viewer"]["following"] is True
    assert removed.status_code == removed_again.status_code == 204
    assert oneself.status_code == 422
    assert unknown.status_code == 404
    assert untrusted.status_code == 403


def test_the_follow_routes_require_a_session():
    client = TestClient(app)

    assert client.put(f"/api/v1/users/{OWNER.handle}/follow").status_code == 401
    assert client.delete(f"/api/v1/users/{OWNER.handle}/follow").status_code == 401


# Enough of each class that an unbounded branch of the union would hand back
# far more keys than any page can hold.
BULK = 30


def fill_with_activity(database, author):
    """Publish BULK visits and BULK photographs, all public, for one author."""
    restaurant_id = RESTAURANTS[0].id
    with database.begin() as connection:
        for ordinal in range(BULK):
            moment = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=ordinal)
            connection.execute(
                insert(visits).values(
                    id=uuid4(),
                    author_id=author.id,
                    restaurant_id=restaurant_id,
                    occurred_at=moment,
                    visibility="public",
                    created_at=moment,
                )
            )
            photo_id = uuid4()
            connection.execute(
                insert(photos).values(
                    id=photo_id,
                    author_id=author.id,
                    restaurant_id=restaurant_id,
                    storage_key=f"test/photos/{photo_id}.webp",
                    content_type="image/webp",
                    size_bytes=1,
                    visibility="public",
                    kind="dish",
                    dish_name=f"Plato {ordinal}",
                    search_dish_name=f"plato {ordinal}",
                    created_at=moment,
                )
            )


def test_no_source_hands_back_more_keys_than_a_profile_page_can_hold(seeded_database):
    fill_with_activity(seeded_database, AUTHOR)
    statements = []

    def record(connection, cursor, statement, *rest):
        del connection, cursor, rest
        statements.append(statement)

    event.listen(seeded_database, "before_cursor_execute", record)
    try:
        page = user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=5)
    finally:
        event.remove(seeded_database, "before_cursor_execute", record)

    # The handle is resolved first, and the union comes next: every branch
    # carries its own cut plus the one that produces the page.
    assert statements[1].upper().count("LIMIT") == len(ACTIVITY_SOURCES) + 1
    assert len(page["items"]) == 5


def test_bounding_each_branch_does_not_change_any_profile_page(seeded_database):
    fill_with_activity(seeded_database, AUTHOR)
    whole = activity_ids(user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=200))

    seen = []
    cursor = None
    while True:
        page = user_service.get_activity(AUTHOR.handle, viewer_id=OWNER.id, limit=5, cursor=cursor)
        seen.extend(activity_ids(page))
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(whole) > 2 * BULK
    assert seen == whole
    assert len(seen) == len(set(seen))
