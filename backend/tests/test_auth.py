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
    EmailAlreadyRegisteredError,
    HandleAlreadyTakenError,
    InvalidCredentialsError,
    InvalidSessionError,
    IssuedSession,
    is_valid_handle,
    normalize_email,
    normalize_handle,
)


def sample_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="demo",
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


def valid_registration(**overrides) -> dict:
    payload = {
        "name": "Nueva Foodie",
        "email": "nueva@example.com",
        "handle": "nueva_foodie",
        "nationality": "CL",
        "password": "a-long-enough-password",
    }
    payload.update(overrides)
    return payload


def register(monkeypatch, payload, issued=None, failure=None):
    """Post a registration with the service replaced, and report what it saw."""
    seen = {}

    def fake_register_user(**kwargs):
        seen.update(kwargs)
        if failure is not None:
            raise failure
        return issued

    monkeypatch.setattr(auth_api, "register_user", fake_register_user)
    response = TestClient(app).post(
        "/api/v1/auth/register",
        headers={"Origin": "http://testserver"},
        json=payload,
    )
    return response, seen


def issued_session_for(session: AuthenticatedSession) -> IssuedSession:
    return IssuedSession(
        token=create_access_token(session.user_id, session.id, expires_at=session.expires_at),
        session=session,
    )


def test_normalized_handle_drops_the_at_sign_and_the_case():
    assert normalize_handle("@Demo") == "demo"
    assert normalize_handle("  DEMO  ") == "demo"
    assert normalize_handle("demo") == "demo"


def test_normalized_email_only_lowers_and_trims():
    assert normalize_email("  Nueva@Example.COM ") == "nueva@example.com"


def test_handle_pattern_accepts_the_stored_form_only():
    assert is_valid_handle("demo_2")
    assert not is_valid_handle("de")
    assert not is_valid_handle("d" * 31)
    assert not is_valid_handle("@demo")
    assert not is_valid_handle("Demo")
    assert not is_valid_handle("demo foodie")


def test_register_creates_the_session_and_answers_like_the_session_endpoint(monkeypatch):
    session = sample_session()
    response, seen = register(
        monkeypatch,
        valid_registration(),
        issued=issued_session_for(session),
    )

    assert response.status_code == 201
    assert response.json() == {
        "user": {
            "id": str(session.user_id),
            "email": session.email,
            "handle": session.handle,
            "name": session.name,
        },
        "expires_at": session.expires_at.isoformat().replace("+00:00", "Z"),
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert response.cookies["session"]
    assert seen["nationality"] == "CL"


def test_register_normalizes_the_handle_before_reaching_the_service(monkeypatch):
    session = sample_session()
    response, seen = register(
        monkeypatch,
        valid_registration(handle="@Nueva_Foodie", email="NUEVA@Example.com"),
        issued=issued_session_for(session),
    )

    assert response.status_code == 201
    assert seen["handle"] == "nueva_foodie"
    assert seen["email"] == "nueva@example.com"


def test_register_reports_which_field_is_already_taken(monkeypatch):
    for failure, field in (
        (EmailAlreadyRegisteredError(), "email"),
        (HandleAlreadyTakenError(), "handle"),
    ):
        response, _ = register(monkeypatch, valid_registration(), failure=failure)
        assert response.status_code == 409
        assert response.json()["detail"]["field"] == field
        assert "set-cookie" not in response.headers


def test_register_rejects_a_handle_outside_the_pattern(monkeypatch):
    for handle in ("ab", "d" * 31, "nueva foodie", "nueva-foodie", "ñandú_foodie"):
        response, seen = register(monkeypatch, valid_registration(handle=handle))
        assert response.status_code == 422, handle
        assert seen == {}


def test_register_rejects_a_short_password(monkeypatch):
    response, seen = register(monkeypatch, valid_registration(password="corta"))

    assert response.status_code == 422
    assert seen == {}


def test_register_rejects_an_unknown_country_code(monkeypatch):
    for nationality in ("ZZ", "Chile", "CHL", ""):
        response, seen = register(monkeypatch, valid_registration(nationality=nationality))
        assert response.status_code == 422, nationality
        assert seen == {}


def test_register_rejects_a_blank_name(monkeypatch):
    response, seen = register(monkeypatch, valid_registration(name="   "))

    assert response.status_code == 422
    assert seen == {}


def test_register_rejects_an_untrusted_origin(monkeypatch):
    monkeypatch.setattr(auth_api, "register_user", lambda **kwargs: None)

    response = TestClient(app).post(
        "/api/v1/auth/register",
        headers={"Origin": "http://evil.example"},
        json=valid_registration(),
    )

    assert response.status_code == 403


def test_register_translates_a_store_failure_without_leaking_details(monkeypatch):
    response, _ = register(
        monkeypatch,
        valid_registration(),
        failure=AuthenticationStoreError("connection refused to db-1"),
    )

    assert response.status_code == 503
    assert "db-1" not in response.text
