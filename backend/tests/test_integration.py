import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, update

from app.core.config import settings
from app.core.security import create_access_token
from app.db import seed as seed_module
from app.db.fixtures import CUISINE_STYLES, RESTAURANTS
from app.db.schema import auth_sessions, cuisine_styles, restaurants, users
from app.db.session import engine
from app.main import app
from app.services.restaurants import normalize_restaurant_text, restaurant_identity_key

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_test_database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("set TEST_DATABASE_URL to run PostgreSQL integration tests")


def test_migrations_create_application_tables():
    assert inspect(engine).has_table("users")
    assert inspect(engine).has_table("auth_sessions")
    assert inspect(engine).has_table("restaurants")
    assert inspect(engine).has_table("cuisine_styles")
    assert inspect(engine).has_table("restaurant_cuisine_styles")


def test_seeded_user_is_persisted():
    with engine.connect() as connection:
        user = (
            connection.execute(
                select(users.c.email, users.c.handle).where(users.c.email == "demo@example.com")
            )
            .mappings()
            .one()
        )

    assert dict(user) == {"email": "demo@example.com", "handle": "@demo"}


def test_restaurant_fixtures_are_persisted():
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(restaurants)) == len(RESTAURANTS)
        assert connection.scalar(select(func.count()).select_from(cuisine_styles)) == len(
            CUISINE_STYLES
        )


def test_login_session_logout_lifecycle_uses_persisted_revocation():
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": "demo@example.com", "password": "demo-password"},
    )

    assert response.status_code == 204
    assert "session" in response.cookies
    token = response.cookies["session"]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    session_id = UUID(payload["jti"])

    with engine.connect() as connection:
        persisted_session = (
            connection.execute(
                select(
                    auth_sessions.c.user_id,
                    auth_sessions.c.expires_at,
                    auth_sessions.c.revoked_at,
                ).where(auth_sessions.c.id == session_id)
            )
            .mappings()
            .one()
        )

    assert str(persisted_session["user_id"]) == payload["sub"]
    assert persisted_session["revoked_at"] is None

    current_response = client.get("/api/v1/auth/session")
    assert current_response.status_code == 200
    assert current_response.json()["user"]["email"] == "demo@example.com"

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    assert logout_response.status_code == 204

    with engine.connect() as connection:
        revoked_at = connection.scalar(
            select(auth_sessions.c.revoked_at).where(auth_sessions.c.id == session_id)
        )
    assert revoked_at is not None

    replay_client = TestClient(app)
    replay_client.cookies.set("session", token)
    assert replay_client.get("/api/v1/auth/session").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://testserver"},
        ).status_code
        == 204
    )


def test_expired_and_unknown_sessions_are_rejected():
    with engine.connect() as connection:
        user_id = connection.scalar(select(users.c.id).where(users.c.email == "demo@example.com"))

    now = datetime.now(UTC).replace(microsecond=0)
    expired_session_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            auth_sessions.insert().values(
                id=expired_session_id,
                user_id=user_id,
                created_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
                revoked_at=None,
            )
        )

    expired_token = create_access_token(
        user_id,
        expired_session_id,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    expired_client = TestClient(app)
    expired_client.cookies.set("session", expired_token)
    assert expired_client.get("/api/v1/auth/session").status_code == 401

    unknown_token = create_access_token(
        user_id,
        uuid4(),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    unknown_client = TestClient(app)
    unknown_client.cookies.set("session", unknown_token)
    assert unknown_client.get("/api/v1/auth/session").status_code == 401

    mismatched_session_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            auth_sessions.insert().values(
                id=mismatched_session_id,
                user_id=user_id,
                created_at=now,
                expires_at=now + timedelta(hours=1),
                revoked_at=None,
            )
        )
    mismatched_token = create_access_token(
        uuid4(),
        mismatched_session_id,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    mismatched_client = TestClient(app)
    mismatched_client.cookies.set("session", mismatched_token)
    assert mismatched_client.get("/api/v1/auth/session").status_code == 401


def authenticated_client() -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": "demo@example.com", "password": "demo-password"},
    )
    assert response.status_code == 204
    return client


def test_restaurant_collection_is_stable_bounded_and_authenticated():
    client = authenticated_client()

    first = client.get("/api/v1/restaurants?limit=3&offset=1")
    second = client.get("/api/v1/restaurants?limit=3&offset=1")

    assert first.status_code == 200
    assert first.json() == second.json()
    assert len(first.json()) == 3
    assert all(restaurant["cuisine_styles"] for restaurant in first.json())
    assert client.get("/api/v1/restaurants?limit=101").status_code == 422


def test_restaurant_crud_duplicate_detection_and_atomic_style_replacement():
    client = authenticated_client()
    origin = {"Origin": "http://testserver"}
    payload = {
        "name": "Laboratorio Gastronómico",
        "address": "Monjitas 550, Santiago",
        "latitude": -33.4369,
        "longitude": -70.6448,
        "cuisine_styles": ["chilena", "vegana"],
    }

    created = client.post("/api/v1/restaurants", headers=origin, json=payload)
    assert created.status_code == 201
    restaurant_id = created.json()["id"]
    assert created.headers["location"] == f"/api/v1/restaurants/{restaurant_id}"
    assert [style["slug"] for style in created.json()["cuisine_styles"]] == [
        "chilena",
        "vegana",
    ]

    shown = client.get(f"/api/v1/restaurants/{restaurant_id}")
    assert shown.status_code == 200
    assert shown.json() == created.json()

    duplicate_payload = {
        **payload,
        "name": "  LABORATORIO   GASTRONÓMICO ",
        "address": " monjitas 550, SANTIAGO ",
    }
    assert (
        client.post("/api/v1/restaurants", headers=origin, json=duplicate_payload).status_code
        == 409
    )

    updated = client.patch(
        f"/api/v1/restaurants/{restaurant_id}",
        headers=origin,
        json={"name": "Laboratorio actualizado", "cuisine_styles": ["japonesa"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Laboratorio actualizado"
    assert updated.json()["address"] == payload["address"]
    assert [style["slug"] for style in updated.json()["cuisine_styles"]] == ["japonesa"]

    rejected = client.patch(
        f"/api/v1/restaurants/{restaurant_id}",
        headers=origin,
        json={"name": "No debe persistir", "cuisine_styles": ["inexistente"]},
    )
    assert rejected.status_code == 422
    assert client.get(f"/api/v1/restaurants/{restaurant_id}").json()["name"] == (
        "Laboratorio actualizado"
    )

    assert client.delete(f"/api/v1/restaurants/{restaurant_id}", headers=origin).status_code == 204
    assert client.get(f"/api/v1/restaurants/{restaurant_id}").status_code == 404
    assert client.delete(f"/api/v1/restaurants/{restaurant_id}", headers=origin).status_code == 404


def test_restaurant_payload_validation_uses_fastapi_format():
    client = authenticated_client()
    response = client.post(
        "/api/v1/restaurants",
        headers={"Origin": "http://testserver"},
        json={
            "name": "Coordenadas inválidas",
            "address": "Santiago",
            "latitude": -91,
            "longitude": 181,
            "cuisine_styles": [],
        },
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_anonymous_restaurant_requests_do_not_modify_data():
    client = TestClient(app)
    restaurant_id = RESTAURANTS[0].id
    payload = {
        "name": "No autorizado",
        "address": "Santiago",
        "latitude": 0,
        "longitude": 0,
        "cuisine_styles": ["chilena"],
    }
    with engine.connect() as connection:
        count_before = connection.scalar(select(func.count()).select_from(restaurants))

    responses = [
        client.get("/api/v1/restaurants"),
        client.post(
            "/api/v1/restaurants",
            headers={"Origin": "http://testserver"},
            json=payload,
        ),
        client.get(f"/api/v1/restaurants/{restaurant_id}"),
        client.patch(
            f"/api/v1/restaurants/{restaurant_id}",
            headers={"Origin": "http://testserver"},
            json={"name": "No autorizado"},
        ),
        client.delete(
            f"/api/v1/restaurants/{restaurant_id}",
            headers={"Origin": "http://testserver"},
        ),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401, 401]
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(restaurants)) == count_before


def test_seed_is_idempotent_and_preserves_fixture_edits():
    fixture = RESTAURANTS[0]
    edited_name = "Edición persistente del estudiante"
    with engine.begin() as connection:
        connection.execute(
            update(restaurants)
            .where(restaurants.c.id == fixture.id)
            .values(
                name=edited_name,
                normalized_name=normalize_restaurant_text(edited_name),
                identity_key=restaurant_identity_key(edited_name, fixture.address),
            )
        )

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert (
            connection.scalar(select(restaurants.c.name).where(restaurants.c.id == fixture.id))
            == edited_name
        )
