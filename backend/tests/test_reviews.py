from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.dependencies import get_current_session
from app.main import app
from app.media.storage import LocalMediaLocation, RemoteMediaLocation, get_media_storage
from app.services import reviews as review_service
from app.services.auth import AuthenticatedSession


class DummyStorage:
    def store(self, **kwargs):
        return "unused"

    def delete(self, storage_key):
        pass

    def resolve(self, storage_key):
        raise AssertionError("unexpected storage lookup")


def sample_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="@demo",
        name="Demo Foodie",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def sample_review(session=None) -> review_service.Review:
    session = session or sample_session()
    timestamp = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    photo = review_service.Photo(
        id=uuid4(),
        author_id=session.user_id,
        restaurant_id=uuid4(),
        storage_key="photos/test.png",
        content_type="image/png",
        size_bytes=42,
        created_at=timestamp,
    )
    return review_service.Review(
        id=uuid4(),
        author_id=session.user_id,
        restaurant_id=photo.restaurant_id,
        dish_name="Ceviche",
        text="Muy fresco",
        visibility="public",
        photo=photo,
        created_at=timestamp,
        updated_at=timestamp,
    )


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def authenticated():
    session = sample_session()
    app.dependency_overrides[get_current_session] = lambda: session
    app.dependency_overrides[get_media_storage] = DummyStorage
    yield session
    app.dependency_overrides.clear()


def test_review_routes_require_authentication_before_service(monkeypatch):
    monkeypatch.setattr(
        review_service,
        "create_review",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("service must not run")),
    )
    response = TestClient(app).post(
        "/api/v1/reviews",
        data={"restaurant_id": str(uuid4()), "dish_name": "Plato", "text": "Texto"},
        files={"photo": ("photo.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 401


def test_create_review_normalizes_fields_and_returns_location(monkeypatch, authenticated):
    review = sample_review(authenticated)
    received = {}

    def create_review(**kwargs):
        received.update(kwargs)
        return review

    monkeypatch.setattr(review_service, "create_review", create_review)
    response = TestClient(app).post(
        "/api/v1/reviews",
        headers={"Origin": "http://testserver"},
        data={
            "restaurant_id": str(review.restaurant_id),
            "dish_name": "  Ceviche  ",
            "text": "  Muy fresco  ",
        },
        files={"photo": ("dish.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 201
    assert response.headers["location"] == f"/api/v1/reviews/{review.id}"
    assert response.json()["photo"]["content_url"] == (f"/api/v1/photos/{review.photo.id}/content")
    assert received["author_id"] == authenticated.user_id
    assert received["dish_name"] == "Ceviche"
    assert received["text"] == "Muy fresco"
    assert received["declared_content_type"] == "image/png"


def test_create_review_rejects_blank_fields_and_untrusted_origin(monkeypatch, authenticated):
    monkeypatch.setattr(
        review_service,
        "create_review",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("invalid request reached service")),
    )
    client = TestClient(app)
    request = {
        "data": {"restaurant_id": str(uuid4()), "dish_name": "   ", "text": "Texto"},
        "files": {"photo": ("dish.png", png_bytes(), "image/png")},
    }
    assert (
        client.post(
            "/api/v1/reviews", headers={"Origin": "http://testserver"}, **request
        ).status_code
        == 422
    )
    request["data"]["dish_name"] = "Plato"
    assert (
        client.post(
            "/api/v1/reviews", headers={"Origin": "https://evil.example"}, **request
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (review_service.InvalidReviewPhotoError(), 422),
        (review_service.ReviewPhotoTooLargeError(), 413),
        (review_service.ReviewNotFoundError(), 404),
        (review_service.ReviewMediaError(), 503),
        (review_service.ReviewStoreError(), 503),
    ],
)
def test_create_maps_domain_errors(monkeypatch, authenticated, error, expected_status):
    monkeypatch.setattr(
        review_service,
        "create_review",
        lambda **kwargs: (_ for _ in ()).throw(error),
    )
    response = TestClient(app).post(
        "/api/v1/reviews",
        headers={"Origin": "http://testserver"},
        data={"restaurant_id": str(uuid4()), "dish_name": "Plato", "text": "Texto"},
        files={"photo": ("dish.png", png_bytes(), "image/png")},
    )
    assert response.status_code == expected_status


def test_photo_content_streams_local_file(monkeypatch, authenticated, tmp_path):
    review = sample_review(authenticated)
    path = tmp_path / "photo.png"
    path.write_bytes(png_bytes())
    monkeypatch.setattr(
        review_service,
        "resolve_photo",
        lambda *args, **kwargs: (review.photo, LocalMediaLocation(path=path)),
    )

    response = TestClient(app).get(f"/api/v1/photos/{review.photo.id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == path.read_bytes()
    assert response.headers["cache-control"] == "private, max-age=300"


def test_photo_content_redirects_to_short_lived_s3_url(monkeypatch, authenticated):
    review = sample_review(authenticated)
    monkeypatch.setattr(
        review_service,
        "resolve_photo",
        lambda *args, **kwargs: (
            review.photo,
            RemoteMediaLocation(url="https://signed.example/photo"),
        ),
    )

    response = TestClient(app).get(
        f"/api/v1/photos/{review.photo.id}/content",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://signed.example/photo"
    assert response.headers["cache-control"] == "private, no-store"
