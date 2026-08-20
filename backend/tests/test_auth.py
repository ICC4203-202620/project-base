from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.api import auth
from app.core.config import settings
from app.core.security import hash_password
from app.main import app


class FakeResult:
    def __init__(self, user):
        self.user = user

    def mappings(self):
        return self

    def first(self):
        return self.user


class FakeConnection:
    def __init__(self, user):
        self.user = user

    def execute(self, statement):
        return FakeResult(self.user)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeEngine:
    def __init__(self, user):
        self.user = user

    def connect(self):
        return FakeConnection(self.user)


def test_login_sets_http_only_jwt_cookie(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        auth,
        "engine",
        FakeEngine({"id": user_id, "password_hash": hash_password("correct-password")}),
    )
    monkeypatch.setattr(settings, "cookie_secure", True)

    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "correct-password"},
    )

    assert response.status_code == 204
    assert response.content == b""
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie
    token = response.cookies["session"]
    assert jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"] == str(user_id)


def test_login_rejects_invalid_credentials_without_session_cookie(monkeypatch):
    monkeypatch.setattr(auth, "engine", FakeEngine(None))

    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in response.headers
