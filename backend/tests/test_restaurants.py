from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_session
from app.main import app
from app.services import restaurants as restaurant_service
from app.services.auth import AuthenticatedSession


def sample_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="@demo",
        name="Demo Foodie",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def sample_restaurant() -> restaurant_service.Restaurant:
    timestamp = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    return restaurant_service.Restaurant(
        id=uuid4(),
        name="Cocina de prueba",
        address="Av. Siempre Viva 123, Santiago",
        latitude=Decimal("-33.437200"),
        longitude=Decimal("-70.650600"),
        cuisine_styles=(
            restaurant_service.CuisineStyle(
                id=uuid4(),
                slug="chilena",
                name="Chilena",
            ),
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.fixture
def authenticated():
    app.dependency_overrides[get_current_session] = sample_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/v1/restaurants", None),
        ("POST", "/api/v1/restaurants", {}),
        ("GET", f"/api/v1/restaurants/{uuid4()}", None),
        ("PATCH", f"/api/v1/restaurants/{uuid4()}", {}),
        ("DELETE", f"/api/v1/restaurants/{uuid4()}", None),
    ],
)
def test_all_routes_require_a_session_before_calling_service(monkeypatch, method, path, payload):
    def unexpected(*args, **kwargs):
        raise AssertionError("restaurant service must not run without authentication")

    monkeypatch.setattr(restaurant_service, "list_restaurants", unexpected)
    monkeypatch.setattr(restaurant_service, "create_restaurant", unexpected)
    monkeypatch.setattr(restaurant_service, "get_restaurant", unexpected)
    monkeypatch.setattr(restaurant_service, "update_restaurant", unexpected)
    monkeypatch.setattr(restaurant_service, "delete_restaurant", unexpected)

    response = TestClient(app).request(method, path, json=payload)

    assert response.status_code == 401


def test_index_uses_bounded_pagination_and_serializes_styles(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def list_restaurants(*, limit, offset):
        received.update(limit=limit, offset=offset)
        return [restaurant]

    monkeypatch.setattr(restaurant_service, "list_restaurants", list_restaurants)

    response = TestClient(app).get("/api/v1/restaurants?limit=5&offset=2")

    assert response.status_code == 200
    assert received == {"limit": 5, "offset": 2}
    assert response.json()[0]["id"] == str(restaurant.id)
    assert response.json()[0]["latitude"] == -33.4372
    assert response.json()[0]["cuisine_styles"][0]["slug"] == "chilena"
    assert TestClient(app).get("/api/v1/restaurants?limit=101").status_code == 422


def test_create_returns_resource_and_location(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def create_restaurant(**kwargs):
        received.update(kwargs)
        return restaurant

    monkeypatch.setattr(restaurant_service, "create_restaurant", create_restaurant)
    response = TestClient(app).post(
        "/api/v1/restaurants",
        headers={"Origin": "http://testserver"},
        json={
            "name": "  Cocina de prueba  ",
            "address": "Av. Siempre Viva 123, Santiago",
            "latitude": -33.4372,
            "longitude": -70.6506,
            "cuisine_styles": ["chilena"],
        },
    )

    assert response.status_code == 201
    assert response.headers["location"] == f"/api/v1/restaurants/{restaurant.id}"
    assert received["name"] == "Cocina de prueba"
    assert received["cuisine_style_slugs"] == ["chilena"]


def test_patch_passes_only_present_fields(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def update_restaurant(restaurant_id, changes):
        received.update(restaurant_id=restaurant_id, changes=changes)
        return restaurant

    monkeypatch.setattr(restaurant_service, "update_restaurant", update_restaurant)
    response = TestClient(app).patch(
        f"/api/v1/restaurants/{restaurant.id}",
        headers={"Origin": "http://testserver"},
        json={"name": "Nuevo nombre"},
    )

    assert response.status_code == 200
    assert received == {"restaurant_id": restaurant.id, "changes": {"name": "Nuevo nombre"}}


def test_delete_returns_no_content(monkeypatch, authenticated):
    restaurant_id = uuid4()
    deleted = []
    monkeypatch.setattr(restaurant_service, "delete_restaurant", deleted.append)

    response = TestClient(app).delete(
        f"/api/v1/restaurants/{restaurant_id}",
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 204
    assert response.content == b""
    assert deleted == [restaurant_id]


def test_domain_errors_map_to_http_statuses(monkeypatch, authenticated):
    restaurant_id = uuid4()
    monkeypatch.setattr(
        restaurant_service,
        "get_restaurant",
        lambda identifier: (_ for _ in ()).throw(restaurant_service.RestaurantNotFoundError()),
    )
    assert TestClient(app).get(f"/api/v1/restaurants/{restaurant_id}").status_code == 404

    monkeypatch.setattr(
        restaurant_service,
        "create_restaurant",
        lambda **kwargs: (_ for _ in ()).throw(restaurant_service.DuplicateRestaurantError()),
    )
    duplicate = TestClient(app).post(
        "/api/v1/restaurants",
        headers={"Origin": "http://testserver"},
        json={
            "name": "Duplicado",
            "address": "Dirección 123",
            "latitude": 0,
            "longitude": 0,
            "cuisine_styles": ["chilena"],
        },
    )
    assert duplicate.status_code == 409

    monkeypatch.setattr(
        restaurant_service,
        "list_restaurants",
        lambda **kwargs: (_ for _ in ()).throw(restaurant_service.RestaurantStoreError()),
    )
    assert TestClient(app).get("/api/v1/restaurants").status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "Inválido",
            "address": "Dirección 123",
            "latitude": -91,
            "longitude": 0,
            "cuisine_styles": ["chilena"],
        },
        {
            "name": "Inválido",
            "address": "Dirección 123",
            "latitude": 0,
            "longitude": 181,
            "cuisine_styles": ["chilena"],
        },
        {
            "name": "Inválido",
            "address": "Dirección 123",
            "latitude": 0,
            "longitude": 0,
            "cuisine_styles": [],
        },
        {
            "name": "Inválido",
            "address": "Dirección 123",
            "latitude": 0,
            "longitude": 0,
            "cuisine_styles": ["chilena", "chilena"],
        },
    ],
)
def test_create_validates_coordinates_and_cuisine_styles(monkeypatch, authenticated, payload):
    monkeypatch.setattr(
        restaurant_service,
        "create_restaurant",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("invalid payload reached service")),
    )

    response = TestClient(app).post(
        "/api/v1/restaurants",
        headers={"Origin": "http://testserver"},
        json=payload,
    )

    assert response.status_code == 422


def test_patch_rejects_empty_null_and_untrusted_requests(monkeypatch, authenticated):
    restaurant_id = uuid4()
    monkeypatch.setattr(
        restaurant_service,
        "update_restaurant",
        lambda *args: (_ for _ in ()).throw(AssertionError("invalid request reached service")),
    )
    client = TestClient(app)

    assert (
        client.patch(
            f"/api/v1/restaurants/{restaurant_id}",
            headers={"Origin": "http://testserver"},
            json={},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/restaurants/{restaurant_id}",
            headers={"Origin": "http://testserver"},
            json={"name": None},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/restaurants/{restaurant_id}",
            headers={"Origin": "https://evil.example"},
            json={"name": "Cambio"},
        ).status_code
        == 403
    )


def test_restaurant_identity_normalization_is_case_and_whitespace_insensitive():
    assert restaurant_service.normalize_restaurant_text("  CAFÉ\tCentral ") == "café central"
    assert restaurant_service.restaurant_identity_key(
        "  CAFÉ\tCentral ", " Avenida Uno 123 "
    ) == restaurant_service.restaurant_identity_key("café central", "avenida uno 123")
