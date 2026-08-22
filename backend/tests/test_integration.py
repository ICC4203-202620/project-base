import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.schema import auth_sessions, users
from app.db.session import engine
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_test_database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("set TEST_DATABASE_URL to run PostgreSQL integration tests")


def test_migrations_create_authentication_tables():
    assert inspect(engine).has_table("users")
    assert inspect(engine).has_table("auth_sessions")


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
