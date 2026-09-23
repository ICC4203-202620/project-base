import base64
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from PIL import Image

from app.api import auth as auth_api
from app.api.dependencies import get_current_session
from app.main import app, handler
from app.media.storage import get_media_storage
from app.services import feed as feed_service
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import reviews as review_service
from app.services.auth import AuthenticatedSession, IssuedSession


class LambdaContext:
    function_name = "foodie-api-test"
    aws_request_id = "test-request"


def api_gateway_event(
    method,
    path,
    *,
    body=None,
    headers=None,
    cookies=None,
    query_string="",
    is_base64_encoded=False,
):
    event = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": query_string,
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
        "isBase64Encoded": is_base64_encoded,
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
        handle="demo",
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


def test_lambda_handler_serves_protected_restaurant_collection(monkeypatch):
    timestamp = datetime(2026, 8, 22, tzinfo=UTC)
    restaurant = restaurant_service.Restaurant(
        id=uuid4(),
        name="Restaurante Lambda",
        address="Santiago",
        latitude=Decimal("-33.437200"),
        longitude=Decimal("-70.650600"),
        cuisine_styles=(
            restaurant_service.CuisineStyle(id=uuid4(), slug="chilena", name="Chilena"),
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )
    received = {}

    def list_restaurants(*, query, limit, cursor):
        received.update(query=query, limit=limit, cursor=cursor)
        return restaurant_service.RestaurantPage(items=(restaurant,), next_cursor=None)

    monkeypatch.setattr(restaurant_service, "list_restaurants", list_restaurants)
    app.dependency_overrides[get_current_session] = lambda: None
    try:
        response = handler(
            api_gateway_event(
                "GET",
                "/api/v1/restaurants",
                query_string="q=lambda&limit=5",
            ),
            LambdaContext(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["items"][0]["id"] == str(restaurant.id)
    assert received == {"query": "lambda", "limit": 5, "cursor": None}


def test_lambda_handler_parses_multipart_review_upload(monkeypatch):
    session = AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="demo",
        name="Demo Foodie",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    timestamp = datetime(2026, 8, 25, tzinfo=UTC)
    restaurant_id = uuid4()
    photo = photo_service.Photo(
        id=uuid4(),
        author_id=session.user_id,
        restaurant_id=restaurant_id,
        storage_key="photos/lambda.png",
        content_type="image/png",
        size_bytes=42,
        visibility="public",
        kind="dish",
        dish_name="Ceviche",
        caption=None,
        created_at=timestamp,
    )
    review = review_service.Review(
        id=uuid4(),
        author_id=session.user_id,
        restaurant_id=restaurant_id,
        dish_name="Ceviche",
        text="Muy fresco",
        visibility="public",
        photo=photo,
        created_at=timestamp,
        updated_at=timestamp,
    )
    image = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(image, format="PNG")
    image_bytes = image.getvalue()
    boundary = "foodie-boundary"
    multipart = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="restaurant_id"\r\n\r\n'
            f"{restaurant_id}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dish_name"\r\n\r\n'
            "Ceviche\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="text"\r\n\r\n'
            "Muy fresco\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="photo"; filename="dish.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + image_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    received = {}

    def create_review(**kwargs):
        received.update(kwargs)
        assert kwargs["photo_stream"].read() == image_bytes
        return review

    monkeypatch.setattr(review_service, "create_review", create_review)
    app.dependency_overrides[get_current_session] = lambda: session
    app.dependency_overrides[get_media_storage] = lambda: object()
    origin = "https://example.execute-api.us-east-1.amazonaws.com"
    try:
        response = handler(
            api_gateway_event(
                "POST",
                "/api/v1/reviews",
                body=base64.b64encode(multipart).decode(),
                headers={
                    "content-type": f"multipart/form-data; boundary={boundary}",
                    "origin": origin,
                    "x-forwarded-proto": "https",
                },
                is_base64_encoded=True,
            ),
            LambdaContext(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response["statusCode"] == 201
    assert json.loads(response["body"])["id"] == str(review.id)
    assert received["author_id"] == session.user_id
    assert received["declared_content_type"] == "image/png"


def test_lambda_handler_serves_feed_and_review_detail(monkeypatch):
    session = AuthenticatedSession(
        id=uuid4(),
        user_id=uuid4(),
        email="demo@example.com",
        handle="demo",
        name="Demo Foodie",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    timestamp = datetime(2026, 8, 25, 12, tzinfo=UTC)
    review_id = uuid4()
    review = {
        "id": review_id,
        "dish_name": "Ceviche",
        "text": "Muy fresco",
        "visibility": "public",
        "author": {"id": session.user_id, "handle": session.handle, "name": session.name},
        "restaurant": {"id": uuid4(), "name": "Puerto Lima", "address": "Santiago"},
        "photo": {
            "id": uuid4(),
            "content_type": "image/webp",
            "content_url": f"/api/v1/photos/{uuid4()}/content",
            "caption": None,
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    monkeypatch.setattr(
        feed_service,
        "get_feed",
        lambda viewer_id, **kwargs: {
            "items": [
                {
                    "type": "review",
                    "occurred_at": timestamp,
                    "published_at": timestamp,
                    "review": review,
                }
            ],
            "next_cursor": None,
        },
    )
    monkeypatch.setattr(
        feed_service,
        "get_review",
        lambda requested_id, **kwargs: review,
    )
    app.dependency_overrides[get_current_session] = lambda: session
    try:
        feed_response = handler(
            api_gateway_event("GET", "/api/v1/feed", query_string="limit=5"),
            LambdaContext(),
        )
        detail_response = handler(
            api_gateway_event("GET", f"/api/v1/reviews/{review_id}"),
            LambdaContext(),
        )
    finally:
        app.dependency_overrides.clear()

    assert feed_response["statusCode"] == 200
    assert json.loads(feed_response["body"])["items"][0]["review"]["id"] == str(review_id)
    assert detail_response["statusCode"] == 200
    assert json.loads(detail_response["body"])["id"] == str(review_id)
