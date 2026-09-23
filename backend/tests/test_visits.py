from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, RESTAURANTS, VISIT_FIXTURES
from app.db.schema import metadata, visits
from app.main import app
from app.services import feed as feed_service
from app.services import restaurants as restaurant_service
from app.services import users as user_service
from app.services import visits as visit_service
from app.services.auth import AuthenticatedSession

AUTHOR = DEMO_USERS[0]
OTHER = DEMO_USERS[1]
RESTAURANT = RESTAURANTS[0].id


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
    for module in (seed_module, visit_service, feed_service, user_service, restaurant_service):
        monkeypatch.setattr(module, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def session(user=AUTHOR):
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def check_in(restaurant_id=RESTAURANT, visibility="public", occurred_at=None, author=AUTHOR):
    return visit_service.create_visit(
        author_id=author.id,
        restaurant_id=restaurant_id,
        visibility=visibility,
        occurred_at=occurred_at,
    )


def test_a_check_in_defaults_its_moment_to_now_and_keeps_its_visibility(seeded_database):
    del seeded_database
    before = datetime.now(UTC)

    public = check_in()
    private = check_in(visibility="private")

    assert public.visibility == "public"
    assert private.visibility == "private"
    assert before <= public.occurred_at == public.created_at


def test_a_check_in_can_report_a_moment_in_the_past(seeded_database):
    del seeded_database
    yesterday = datetime.now(UTC) - timedelta(days=1)

    visit = check_in(occurred_at=yesterday)

    assert visit.occurred_at == yesterday
    # Recording it is a separate instant from being there.
    assert visit.created_at > visit.occurred_at


def test_a_moment_in_the_future_or_without_a_zone_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(visit_service.InvalidVisitError):
        check_in(occurred_at=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(visit_service.InvalidVisitError):
        check_in(occurred_at=datetime(2026, 8, 1, 12))  # noqa: DTZ001 — sin zona a propósito
    # A slightly fast clock is not a reservation.
    assert check_in(occurred_at=datetime.now(UTC) + timedelta(minutes=1))


def test_an_unknown_visibility_is_rejected_by_the_service(seeded_database):
    del seeded_database

    with pytest.raises(visit_service.InvalidVisitError):
        check_in(visibility="secreta")


def test_a_check_in_on_a_restaurant_that_does_not_exist(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        check_in(restaurant_id=uuid4())


def test_the_same_person_can_check_in_twice_at_the_same_restaurant(seeded_database):
    first = check_in()
    second = check_in()

    assert first.id != second.id

    with seeded_database.connect() as connection:
        stored = set(
            connection.scalars(select(visits.c.id).where(visits.c.author_id == AUTHOR.id)).all()
        )

    assert {first.id, second.id} <= stored


def test_a_visit_is_addressable_and_respects_its_visibility(seeded_database):
    del seeded_database
    public = check_in()
    private = check_in(visibility="private")

    seen_by_other = visit_service.get_visit(public.id, viewer_id=OTHER.id)
    own = visit_service.get_visit(private.id, viewer_id=AUTHOR.id)

    assert seen_by_other["id"] == public.id
    assert seen_by_other["author"]["handle"] == AUTHOR.handle
    assert seen_by_other["restaurant"]["id"] == RESTAURANT
    assert own["visibility"] == "private"
    with pytest.raises(visit_service.VisitNotFoundError):
        visit_service.get_visit(private.id, viewer_id=OTHER.id)
    with pytest.raises(visit_service.VisitNotFoundError):
        visit_service.get_visit(uuid4(), viewer_id=AUTHOR.id)


def test_a_visit_shows_in_its_author_profile_and_only_public_ones_elsewhere(seeded_database):
    del seeded_database
    private = check_in(visibility="private")
    public = check_in()

    own = user_service.get_activity(AUTHOR.handle, viewer_id=AUTHOR.id, limit=50)
    seen = user_service.get_activity(AUTHOR.handle, viewer_id=OTHER.id, limit=50)

    own_ids = {item[item["type"]]["id"] for item in own["items"]}
    seen_ids = {item[item["type"]]["id"] for item in seen["items"]}
    assert {private.id, public.id} <= own_ids
    assert public.id in seen_ids
    assert private.id not in seen_ids


def test_a_private_visit_reaches_nobody_feed(seeded_database):
    del seeded_database
    private = check_in(author=OTHER, visibility="private")

    page = feed_service.get_feed(AUTHOR.id, limit=50)

    assert private.id not in {item[item["type"]]["id"] for item in page["items"]}


def test_a_visit_backdated_today_leads_the_feed_of_the_followers(seeded_database):
    del seeded_database
    # Between two activities of the same person, so where it lands in the
    # profile is observable and different from where it lands in the feed.
    long_ago = datetime(2026, 8, 18, 6, tzinfo=UTC)
    visit = check_in(author=OTHER, occurred_at=long_ago)

    feed = feed_service.get_feed(AUTHOR.id, limit=50)
    profile = user_service.get_activity(OTHER.handle, viewer_id=AUTHOR.id, limit=50)
    profile_ids = [item[item["type"]]["id"] for item in profile["items"]]
    occurrences = [item["occurred_at"] for item in profile["items"]]

    # Recorded last, so it leads the feed of whoever follows that person.
    assert feed["items"][0]["visit"]["id"] == visit.id
    # And it sits by the day it happened in that person's own chronology.
    assert visit.id in profile_ids
    assert profile_ids[0] != visit.id
    assert occurrences == sorted(occurrences, reverse=True)


def test_the_restaurant_counter_differs_between_the_author_and_a_third_party(seeded_database):
    del seeded_database
    check_in(visibility="private")

    own = restaurant_service.get_restaurant_detail(RESTAURANT, viewer_id=AUTHOR.id)
    seen = restaurant_service.get_restaurant_detail(RESTAURANT, viewer_id=OTHER.id)

    assert own.counters.visits == seen.counters.visits + 1


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(visit_service, "engine", BrokenEngine())
    with pytest.raises(visit_service.VisitStoreError):
        check_in()
    with pytest.raises(visit_service.VisitStoreError):
        visit_service.get_visit(VISIT_FIXTURES[0].id, viewer_id=AUTHOR.id)


def test_the_routes_require_a_session_and_a_trusted_origin():
    client = TestClient(app)

    assert client.get(f"/api/v1/visits/{uuid4()}").status_code == 401
    assert (
        client.post(
            "/api/v1/visits",
            json={"restaurant_id": str(RESTAURANT), "visibility": "public"},
        ).status_code
        == 401
    )

    app.dependency_overrides[get_current_session] = session
    try:
        untrusted = client.post(
            "/api/v1/visits",
            headers={"Origin": "http://evil.example"},
            json={"restaurant_id": str(RESTAURANT), "visibility": "public"},
        )
    finally:
        app.dependency_overrides.clear()
    assert untrusted.status_code == 403


def test_the_creation_endpoint_requires_an_explicit_visibility(seeded_database):
    del seeded_database
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    try:
        without_visibility = client.post(
            "/api/v1/visits",
            headers={"Origin": "http://testserver"},
            json={"restaurant_id": str(RESTAURANT)},
        )
        created = client.post(
            "/api/v1/visits",
            headers={"Origin": "http://testserver"},
            json={"restaurant_id": str(RESTAURANT), "visibility": "private"},
        )
        unknown_restaurant = client.post(
            "/api/v1/visits",
            headers={"Origin": "http://testserver"},
            json={"restaurant_id": str(uuid4()), "visibility": "public"},
        )
    finally:
        app.dependency_overrides.clear()

    assert without_visibility.status_code == 422
    assert created.status_code == 201
    assert created.headers["location"] == f"/api/v1/visits/{created.json()['id']}"
    assert created.json()["visibility"] == "private"
    assert created.json()["restaurant"]["id"] == str(RESTAURANT)
    assert unknown_restaurant.status_code == 404
