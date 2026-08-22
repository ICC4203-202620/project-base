from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import dependencies
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.services.auth import (
    AuthenticatedSession,
    AuthenticationStoreError,
    InvalidCredentialsError,
    InvalidSessionError,
    IssuedSession,
)


def sample_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="@demo",
        name="Demo Foodie",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_login_persists_session_before_setting_complete_jwt_cookie(monkeypatch):
    session = sample_session()
    token = create_access_token(
        session.user_id,
        session.id,
        expires_at=session.expires_at,
    )
    monkeypatch.setattr(
        auth_api,
        "start_session",
        lambda email, password: IssuedSession(token=token, session=session),
    )
    monkeypatch.setattr(settings, "cookie_secure", True)

    response = TestClient(app, base_url="https://testserver").post(
        "/api/v1/auth/login",
        headers={"Origin": "https://testserver"},
        json={"email": "demo@example.com", "password": "correct-password"},
    )

    assert response.status_code == 204
    assert response.content == b""
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=" in cookie
    assert "expires=" in cookie
    payload = jwt.decode(
        response.cookies["session"],
        settings.jwt_secret,
        algorithms=["HS256"],
    )
    assert payload["sub"] == str(session.user_id)
    assert payload["jti"] == str(session.id)
    assert {"iat", "exp"} <= payload.keys()


def test_login_rejects_invalid_credentials_without_session_cookie(monkeypatch):
    def reject_credentials(email, password):
        raise InvalidCredentialsError

    monkeypatch.setattr(auth_api, "start_session", reject_credentials)

    response = TestClient(app).post(
        "/api/v1/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": "demo@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in response.headers


def test_login_rejects_untrusted_browser_origin_before_checking_credentials(monkeypatch):
    def unexpected_login(email, password):
        raise AssertionError("login must not run for an untrusted origin")

    monkeypatch.setattr(auth_api, "start_session", unexpected_login)

    response = TestClient(app).post(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"email": "demo@example.com", "password": "password"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted request origin"}


def test_login_rejects_cross_site_fetch_without_origin():
    response = TestClient(app).post(
        "/api/v1/auth/login",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"email": "demo@example.com", "password": "password"},
    )

    assert response.status_code == 403


def test_current_session_returns_minimal_identity_and_expiration(monkeypatch):
    session = sample_session()
    monkeypatch.setattr(dependencies, "authenticate_session", lambda token: session)
    client = TestClient(app)
    client.cookies.set("session", "signed-token")

    response = client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": str(session.user_id),
            "email": session.email,
            "handle": session.handle,
            "name": session.name,
        },
        "expires_at": session.expires_at.isoformat().replace("+00:00", "Z"),
    }


def test_current_session_rejects_missing_invalid_and_unavailable_sessions(monkeypatch):
    client = TestClient(app)
    assert client.get("/api/v1/auth/session").status_code == 401

    client.cookies.set("session", "invalid-token")
    monkeypatch.setattr(
        dependencies,
        "authenticate_session",
        lambda token: (_ for _ in ()).throw(InvalidSessionError()),
    )
    assert client.get("/api/v1/auth/session").status_code == 401

    monkeypatch.setattr(
        dependencies,
        "authenticate_session",
        lambda token: (_ for _ in ()).throw(AuthenticationStoreError()),
    )
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}


def test_logout_revokes_session_and_clears_cookie_idempotently(monkeypatch):
    revoked_tokens = []
    monkeypatch.setattr(auth_api, "revoke_session", revoked_tokens.append)
    client = TestClient(app)
    client.cookies.set("session", "signed-token")

    first_response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    anonymous_client = TestClient(app)
    second_response = anonymous_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 204
    assert revoked_tokens == ["signed-token", None]
    cleared_cookie = first_response.headers["set-cookie"]
    assert "Max-Age=0" in cleared_cookie
    assert "HttpOnly" in cleared_cookie
    assert "SameSite=lax" in cleared_cookie
    assert "Path=/" in cleared_cookie


def test_authentication_store_failures_return_service_unavailable(monkeypatch):
    def unavailable(*args):
        raise AuthenticationStoreError

    monkeypatch.setattr(auth_api, "start_session", unavailable)
    login_response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "password"},
    )
    assert login_response.status_code == 503

    monkeypatch.setattr(auth_api, "revoke_session", unavailable)
    client = TestClient(app)
    client.cookies.set("session", "signed-token")
    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 503
