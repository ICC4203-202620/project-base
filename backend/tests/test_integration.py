import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.db.schema import users
from app.db.session import engine
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_test_database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("set TEST_DATABASE_URL to run PostgreSQL integration tests")


def test_migrations_create_users_table():
    assert inspect(engine).has_table("users")


def test_seeded_user_is_persisted():
    with engine.connect() as connection:
        user = connection.execute(
            select(users.c.email, users.c.handle).where(users.c.email == "demo@example.com")
        ).mappings().one()

    assert dict(user) == {"email": "demo@example.com", "handle": "@demo"}


def test_login_uses_migrated_database_and_seeded_user():
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "demo-password"},
    )

    assert response.status_code == 204
    assert "session" in response.cookies
