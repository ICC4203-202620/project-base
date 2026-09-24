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
from app.db.fixtures import DEMO_USERS, RESTAURANTS, REVIEW_FIXTURES
from app.db.schema import metadata
from app.main import app
from app.media.storage import LocalMediaLocation
from app.services import feed as feed_service
from app.services import photos as photo_service
from app.services import reviews as review_service
from app.services import users as user_service
from app.services.auth import AuthenticatedSession

AUTHOR = DEMO_USERS[0]
OTHER = DEMO_USERS[1]
RESTAURANT = RESTAURANTS[0].id


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
    for module in (seed_module, photo_service, review_service, feed_service, user_service):
        monkeypatch.setattr(module, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=MemoryStorage())
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


def png_file() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(stream, format="PNG")
    stream.seek(0)
    return stream


def a_photo(author=AUTHOR, *, kind="dish", visibility="public", dish_name="Merluza austral"):
    return photo_service.store_photo(
        author_id=author.id,
        restaurant_id=RESTAURANT,
        kind=kind,
        dish_name=dish_name if kind == "dish" else None,
        caption=None,
        visibility=visibility,
        photo_stream=png_file(),
        declared_content_type="image/png",
        storage=MemoryStorage(),
    )


def review(photo, author=AUTHOR, *, rating=4, text="Muy fresco", visibility="public"):
    return review_service.create_review(
        author_id=author.id,
        photo_id=photo.id,
        rating=rating,
        text=text,
        visibility=visibility,
    )


def test_a_review_is_added_to_a_photograph_that_already_exists(seeded_database):
    del seeded_database
    photo = a_photo()

    written = review(photo, rating=5, text="  Excelente  ")

    assert written.photo_id == photo.id
    assert written.restaurant_id == RESTAURANT
    assert written.rating == 5
    assert written.text == "Excelente"
    # The dish comes from the photograph, which is where it lives.
    assert written.dish_name == "Merluza austral"


def test_a_private_review_over_a_public_photograph_is_allowed(seeded_database):
    del seeded_database
    photo = a_photo()

    written = review(photo, visibility="private")

    assert written.visibility == "private"
    assert photo.visibility == "public"
    seen = user_service.get_activity(AUTHOR.handle, viewer_id=OTHER.id, limit=50)
    assert written.id not in {
        item["review"]["id"] for item in seen["items"] if item["type"] == "review"
    }


def test_a_review_is_never_more_visible_than_its_photograph(seeded_database):
    del seeded_database
    private_photo = a_photo(visibility="private")

    with pytest.raises(review_service.InvalidReviewError):
        review(private_photo, visibility="public")
    # Private over private is fine.
    assert review(private_photo, visibility="private")


def test_only_the_author_of_the_photograph_reviews_it(seeded_database):
    del seeded_database
    photo = a_photo(author=AUTHOR)

    with pytest.raises(review_service.InvalidReviewError) as raised:
        review(photo, author=OTHER)

    assert "took the photograph" in raised.value.reason
    # And the owner can still write theirs, which is the point.
    assert review(photo, author=AUTHOR)


def test_only_a_photograph_of_a_dish_can_be_reviewed(seeded_database):
    del seeded_database

    for kind in ("menu", "venue"):
        with pytest.raises(review_service.InvalidReviewError):
            review(a_photo(kind=kind))


def test_a_photograph_that_does_not_exist_or_is_not_visible(seeded_database):
    del seeded_database
    someone_elses_private = a_photo(author=OTHER, visibility="private")

    with pytest.raises(review_service.ReviewNotFoundError):
        review_service.create_review(
            author_id=AUTHOR.id,
            photo_id=uuid4(),
            rating=4,
            text="Texto",
            visibility="public",
        )
    with pytest.raises(review_service.ReviewNotFoundError):
        review(someone_elses_private, author=AUTHOR)


def test_a_second_review_over_the_same_photograph_names_the_first(seeded_database):
    del seeded_database
    photo = a_photo()
    first = review(photo)

    with pytest.raises(review_service.DuplicateReviewError) as raised:
        review(photo, text="Otra opinión")

    assert raised.value.existing_id == first.id


def test_the_rating_and_the_text_are_validated(seeded_database):
    del seeded_database
    photo = a_photo()

    for overrides in (
        {"rating": 0},
        {"rating": 6},
        {"rating": 4.5},
        {"rating": True},
        {"text": "   "},
        {"visibility": "secreta"},
    ):
        with pytest.raises(review_service.InvalidReviewError):
            review(photo, **overrides)


def test_a_reviewed_photograph_stops_being_activity_of_its_own(seeded_database):
    del seeded_database
    photo = a_photo(author=OTHER)

    before = feed_service.get_feed(AUTHOR.id, limit=50)
    written = review(photo, author=OTHER)
    after = feed_service.get_feed(AUTHOR.id, limit=50)

    def photo_ids(page):
        return {
            photograph["id"]
            for item in page["items"]
            if item["type"] == "photo"
            for photograph in item["photo"]["photos"]
        }

    assert photo.id in photo_ids(before)
    # The review publishes it now, so it no longer appears on its own.
    assert photo.id not in photo_ids(after)
    assert written.id in {
        item["review"]["id"] for item in after["items"] if item["type"] == "review"
    }


def test_the_rating_travels_in_the_detail_the_profile_and_the_feed(seeded_database):
    del seeded_database
    fixture = REVIEW_FIXTURES[0]

    detail = feed_service.get_review(fixture.id, viewer_id=AUTHOR.id)
    profile = user_service.get_activity(OTHER.handle, viewer_id=AUTHOR.id, limit=50)
    feed = feed_service.get_feed(AUTHOR.id, limit=50)
    in_profile = next(
        item
        for item in profile["items"]
        if item["type"] == "review" and item["review"]["id"] == fixture.id
    )
    in_feed = next(
        item
        for item in feed["items"]
        if item["type"] == "review" and item["review"]["id"] == fixture.id
    )

    assert detail["rating"] == fixture.rating
    assert detail["dish_name"] == fixture.dish_name
    assert in_profile["review"]["rating"] == fixture.rating
    assert in_feed["review"]["rating"] == fixture.rating


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(review_service, "engine", BrokenEngine())
    with pytest.raises(review_service.ReviewStoreError):
        review_service.create_review(
            author_id=AUTHOR.id,
            photo_id=uuid4(),
            rating=4,
            text="Texto",
            visibility="public",
        )


def test_the_endpoint_answers_the_new_contract(seeded_database):
    del seeded_database
    photo = a_photo()
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}
    body = {"photo_id": str(photo.id), "rating": 4, "text": "Muy fresco", "visibility": "public"}
    try:
        created = client.post("/api/v1/reviews", headers=origin, json=body)
        duplicate = client.post("/api/v1/reviews", headers=origin, json=body)
        unknown_photo = client.post(
            "/api/v1/reviews",
            headers=origin,
            json={**body, "photo_id": str(uuid4())},
        )
        bad_rating = client.post("/api/v1/reviews", headers=origin, json={**body, "rating": 9})
        without_visibility = client.post(
            "/api/v1/reviews",
            headers=origin,
            json={"photo_id": str(photo.id), "rating": 4, "text": "Texto"},
        )
        untrusted = client.post(
            "/api/v1/reviews",
            headers={"Origin": "http://evil.example"},
            json=body,
        )
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.headers["location"] == f"/api/v1/reviews/{created.json()['id']}"
    assert created.json()["rating"] == 4
    assert created.json()["dish_name"] == "Merluza austral"
    assert created.json()["photo_id"] == str(photo.id)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["review"]["id"] == created.json()["id"]
    assert unknown_photo.status_code == 404
    assert bad_rating.status_code == 422
    assert without_visibility.status_code == 422
    assert untrusted.status_code == 403


def test_the_route_requires_a_session():
    assert (
        TestClient(app)
        .post(
            "/api/v1/reviews",
            json={"photo_id": str(uuid4()), "rating": 4, "text": "x", "visibility": "public"},
        )
        .status_code
        == 401
    )
