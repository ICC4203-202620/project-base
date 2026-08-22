import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.api import auth as auth_api
from app.main import handler
from app.services.auth import AuthenticatedSession, IssuedSession


class LambdaContext:
    function_name = "foodie-api-test"
    aws_request_id = "test-request"


def api_gateway_event(method, path, *, body=None, headers=None, cookies=None):
    event = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {
            "host": "example.execute-api.us-east-1.amazonaws.com",
            **(headers or {}),
        },
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "test-api",
            "domainName": "example.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "example",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "test-request",
            "routeKey": "GET /healthz",
            "stage": "$default",
            "time": "21/Aug/2026:00:00:00 +0000",
            "timeEpoch": 1787270400000,
        },
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = body
    if cookies is not None:
        event["cookies"] = cookies
    return event


def test_lambda_handler_serves_health_route():
    event = api_gateway_event("GET", "/healthz")

    response = handler(event, LambdaContext())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}


def test_lambda_handler_preserves_login_and_logout_cookies(monkeypatch):
    session = AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="@demo",
        name="Demo Foodie",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    monkeypatch.setattr(
        auth_api,
        "start_session",
        lambda email, password: IssuedSession(token="signed-token", session=session),
    )
    origin = "https://example.execute-api.us-east-1.amazonaws.com"
    login_event = api_gateway_event(
        "POST",
        "/api/v1/auth/login",
        body=json.dumps({"email": "demo@example.com", "password": "password"}),
        headers={
            "content-type": "application/json",
            "origin": origin,
            "x-forwarded-proto": "https",
        },
    )

    login_response = handler(login_event, LambdaContext())

    assert login_response["statusCode"] == 204
    assert any(cookie.startswith("session=signed-token") for cookie in login_response["cookies"])

    revoked_tokens = []
    monkeypatch.setattr(auth_api, "revoke_session", revoked_tokens.append)
    logout_event = api_gateway_event(
        "POST",
        "/api/v1/auth/logout",
        headers={"origin": origin, "x-forwarded-proto": "https"},
        cookies=["session=signed-token"],
    )

    logout_response = handler(logout_event, LambdaContext())

    assert logout_response["statusCode"] == 204
    assert revoked_tokens == ["signed-token"]
    assert any("Max-Age=0" in cookie for cookie in logout_response["cookies"])
