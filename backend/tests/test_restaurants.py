from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_session
from app.main import app
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError


def sample_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="demo",
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


def test_index_pages_by_cursor_and_serializes_the_shared_summary(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def list_restaurants(*, query, limit, cursor):
        received.update(query=query, limit=limit, cursor=cursor)
        return restaurant_service.RestaurantPage(items=(restaurant,), next_cursor="siguiente")

    monkeypatch.setattr(restaurant_service, "list_restaurants", list_restaurants)

    response = TestClient(app).get("/api/v1/restaurants?q=cocina&limit=5&cursor=previo")

    assert response.status_code == 200
    assert received == {"query": "cocina", "limit": 5, "cursor": "previo"}
    payload = response.json()
    assert payload["next_cursor"] == "siguiente"
    assert payload["items"][0]["id"] == str(restaurant.id)
    assert payload["items"][0]["address"] == restaurant.address
    assert payload["items"][0]["latitude"] == -33.4372
    assert payload["items"][0]["cuisine_styles"][0]["slug"] == "chilena"
    assert TestClient(app).get("/api/v1/restaurants?limit=101").status_code == 422


def test_index_rejects_a_short_term_and_a_foreign_cursor(monkeypatch, authenticated):
    monkeypatch.setattr(
        restaurant_service,
        "list_restaurants",
        lambda **kwargs: (_ for _ in ()).throw(restaurant_service.SearchTermTooShortError()),
    )
    short = TestClient(app).get("/api/v1/restaurants?q=c")
    assert short.status_code == 422
    assert short.json()["detail"][0]["loc"] == ["query", "q"]

    monkeypatch.setattr(
        restaurant_service,
        "list_restaurants",
        lambda **kwargs: (_ for _ in ()).throw(InvalidCursorError()),
    )
    assert TestClient(app).get("/api/v1/restaurants?cursor=roto").status_code == 422


def test_cuisine_style_catalogue_requires_a_session(monkeypatch):
    monkeypatch.setattr(
        restaurant_service,
        "list_cuisine_styles",
        lambda: [restaurant_service.CuisineStyle(id=uuid4(), slug="chilena", name="Chilena")],
    )
    assert TestClient(app).get("/api/v1/cuisine-styles").status_code == 401

    app.dependency_overrides[get_current_session] = sample_session
    try:
        response = TestClient(app).get("/api/v1/cuisine-styles")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "chilena"


def test_map_answers_a_rectangle_and_announces_truncation(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def restaurants_in_bounds(*, south, west, north, east, limit):
        received.update(south=south, west=west, north=north, east=east, limit=limit)
        return restaurant_service.RestaurantMapResult(items=(restaurant,), truncated=True)

    monkeypatch.setattr(restaurant_service, "restaurants_in_bounds", restaurants_in_bounds)

    response = TestClient(app).get(
        "/api/v1/restaurants/map?south=-33.5&west=-70.7&north=-33.4&east=-70.5&limit=50"
    )

    assert response.status_code == 200
    assert received == {
        "south": -33.5,
        "west": -70.7,
        "north": -33.4,
        "east": -70.5,
        "limit": 50,
    }
    payload = response.json()
    assert payload["truncated"] is True
    assert payload["items"][0]["id"] == str(restaurant.id)
    assert payload["items"][0]["latitude"] == -33.4372
    assert payload["items"][0]["cuisine_styles"][0]["slug"] == "chilena"


def test_map_route_is_not_read_as_a_restaurant_identifier(monkeypatch, authenticated):
    def unexpected(restaurant_id):
        raise AssertionError(f"the show route received {restaurant_id}")

    monkeypatch.setattr(restaurant_service, "get_restaurant", unexpected)
    monkeypatch.setattr(
        restaurant_service,
        "restaurants_in_bounds",
        lambda **kwargs: restaurant_service.RestaurantMapResult(items=(), truncated=False),
    )

    response = TestClient(app).get(
        "/api/v1/restaurants/map?south=-33.5&west=-70.7&north=-33.4&east=-70.5"
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "truncated": False}


def test_map_validates_its_rectangle(monkeypatch, authenticated):
    client = TestClient(app)

    assert client.get("/api/v1/restaurants/map?south=-33.5&west=-70.7").status_code == 422
    assert (
        client.get(
            "/api/v1/restaurants/map?south=-91&west=-70.7&north=-33.4&east=-70.5"
        ).status_code
        == 422
    )

    monkeypatch.setattr(
        restaurant_service,
        "restaurants_in_bounds",
        lambda **kwargs: (_ for _ in ()).throw(restaurant_service.InvalidMapBoundsError("zoom in")),
    )
    too_large = client.get("/api/v1/restaurants/map?south=-40&west=-80&north=-10&east=-60")
    assert too_large.status_code == 422
    assert too_large.json()["detail"][0]["loc"] == ["query", "bounds"]


def test_map_requires_a_session():
    assert (
        TestClient(app)
        .get("/api/v1/restaurants/map?south=-33.5&west=-70.7&north=-33.4&east=-70.5")
        .status_code
        == 401
    )


def test_nearby_passes_its_circle_and_serializes_the_distance(monkeypatch, authenticated):
    restaurant = sample_restaurant()
    received = {}

    def restaurants_nearby(*, latitude, longitude, radius_metres, cuisine_style_slugs, limit):
        received.update(
            latitude=latitude,
            longitude=longitude,
            radius_metres=radius_metres,
            cuisine_style_slugs=list(cuisine_style_slugs),
            limit=limit,
        )
        return restaurant_service.RestaurantNearbyResult(
            items=(restaurant_service.NearbyRestaurant.of(restaurant, 1234),),
            truncated=False,
        )

    monkeypatch.setattr(restaurant_service, "restaurants_nearby", restaurants_nearby)

    response = TestClient(app).get(
        "/api/v1/restaurants/nearby"
        "?latitude=-33.4372&longitude=-70.6506&radius=2000"
        "&cuisine_style=chilena&cuisine_style=peruana&limit=10"
    )

    assert response.status_code == 200
    assert received == {
        "latitude": -33.4372,
        "longitude": -70.6506,
        "radius_metres": 2000,
        "cuisine_style_slugs": ["chilena", "peruana"],
        "limit": 10,
    }
    payload = response.json()
    assert payload["truncated"] is False
    assert payload["items"][0]["distance_m"] == 1234
    assert payload["items"][0]["address"] == restaurant.address
    assert payload["items"][0]["cuisine_styles"][0]["slug"] == "chilena"


def test_nearby_works_without_a_style_filter(monkeypatch, authenticated):
    received = {}

    def restaurants_nearby(**kwargs):
        received.update(kwargs)
        return restaurant_service.RestaurantNearbyResult(items=(), truncated=False)

    monkeypatch.setattr(restaurant_service, "restaurants_nearby", restaurants_nearby)

    response = TestClient(app).get(
        "/api/v1/restaurants/nearby?latitude=-33.4&longitude=-70.6&radius=1000"
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "truncated": False}
    assert list(received["cuisine_style_slugs"]) == []


def test_nearby_validates_its_circle(monkeypatch, authenticated):
    client = TestClient(app)

    assert client.get("/api/v1/restaurants/nearby?latitude=-33.4").status_code == 422
    assert (
        client.get("/api/v1/restaurants/nearby?latitude=-33.4&longitude=-70.6&radius=0").status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/restaurants/nearby?latitude=-91&longitude=-70.6&radius=1000"
        ).status_code
        == 422
    )

    monkeypatch.setattr(
        restaurant_service,
        "restaurants_nearby",
        lambda **kwargs: (_ for _ in ()).throw(
            restaurant_service.InvalidNearbySearchError("radius must not exceed 50000 metres")
        ),
    )
    too_far = client.get("/api/v1/restaurants/nearby?latitude=-33.4&longitude=-70.6&radius=40000")
    assert too_far.status_code == 422
    assert too_far.json()["detail"][0]["loc"] == ["query", "radius"]

    monkeypatch.setattr(
        restaurant_service,
        "restaurants_nearby",
        lambda **kwargs: (_ for _ in ()).throw(
            restaurant_service.UnknownCuisineStylesError(["marciana"])
        ),
    )
    unknown_style = client.get(
        "/api/v1/restaurants/nearby?latitude=-33.4&longitude=-70.6&radius=1000"
        "&cuisine_style=marciana"
    )
    assert unknown_style.status_code == 422


def test_nearby_requires_a_session():
    assert (
        TestClient(app)
        .get("/api/v1/restaurants/nearby?latitude=-33.4&longitude=-70.6&radius=1000")
        .status_code
        == 401
    )


def test_detail_and_gallery_map_their_domain_errors(monkeypatch, authenticated):
    restaurant_id = uuid4()
    client = TestClient(app)

    monkeypatch.setattr(
        restaurant_service,
        "get_restaurant",
        lambda identifier: (_ for _ in ()).throw(restaurant_service.RestaurantNotFoundError()),
    )
    assert client.get(f"/api/v1/restaurants/{restaurant_id}/photos").status_code == 404

    monkeypatch.setattr(restaurant_service, "get_restaurant", lambda identifier: None)
    monkeypatch.setattr(
        photo_service,
        "list_restaurant_photos",
        lambda *args, **kwargs: (_ for _ in ()).throw(InvalidCursorError()),
    )
    assert client.get(f"/api/v1/restaurants/{restaurant_id}/photos?cursor=roto").status_code == 422

    monkeypatch.setattr(
        photo_service,
        "list_restaurant_photos",
        lambda *args, **kwargs: (_ for _ in ()).throw(photo_service.PhotoStoreError()),
    )
    assert client.get(f"/api/v1/restaurants/{restaurant_id}/photos").status_code == 503


def test_detail_and_gallery_require_a_session():
    restaurant_id = uuid4()
    client = TestClient(app)

    assert client.get(f"/api/v1/restaurants/{restaurant_id}").status_code == 401
    assert client.get(f"/api/v1/restaurants/{restaurant_id}/photos").status_code == 401


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
        "get_restaurant_detail",
        lambda identifier, **kwargs: (_ for _ in ()).throw(
            restaurant_service.RestaurantNotFoundError()
        ),
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
