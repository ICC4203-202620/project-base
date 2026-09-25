import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, inspect, select, text, update

from app.core.config import settings
from app.core.security import create_access_token
from app.db import seed as seed_module
from app.db.fixtures import (
    CUISINE_STYLES,
    DEMO_USERS,
    RESTAURANTS,
    REVIEW_FIXTURES,
    VISIT_FIXTURES,
)
from app.db.schema import (
    auth_sessions,
    cuisine_styles,
    photos,
    restaurants,
    reviews,
    users,
)
from app.db.session import engine
from app.main import app
from app.media.storage import LocalMediaStorage, get_media_storage
from app.services.restaurants import (
    normalize_restaurant_search_text,
    normalize_restaurant_text,
    restaurant_identity_key,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_test_database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("set TEST_DATABASE_URL to run PostgreSQL integration tests")


def test_migrations_create_application_tables():
    inspector = inspect(engine)
    assert inspector.has_table("users")
    assert inspector.has_table("auth_sessions")
    assert inspector.has_table("restaurants")
    assert inspector.has_table("cuisine_styles")
    assert inspector.has_table("restaurant_cuisine_styles")
    assert inspector.has_table("photos")
    assert inspector.has_table("reviews")
    assert inspector.has_table("user_follows")
    assert inspector.has_table("restaurant_follows")
    assert inspector.get_pk_constraint("user_follows")["constrained_columns"] == [
        "follower_id",
        "followed_id",
    ]
    assert {
        constraint["name"] for constraint in inspector.get_check_constraints("user_follows")
    } == {"ck_user_follows_not_self"}
    restaurant_indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("restaurants")
    }
    assert restaurant_indexes["ix_restaurants_search_name_id"] == ["search_name", "id"]
    assert restaurant_indexes["ix_restaurants_location"] == ["latitude", "longitude"]
    photo_indexes = {
        index["name"]: index["column_names"] for index in inspector.get_indexes("photos")
    }
    assert photo_indexes["ix_photos_restaurant_created_id"] == [
        "restaurant_id",
        "created_at",
        "id",
    ]
    assert "ix_photos_restaurant_id" not in photo_indexes


def test_seeded_user_is_persisted():
    with engine.connect() as connection:
        user = (
            connection.execute(
                select(users.c.email, users.c.handle).where(users.c.email == "demo@example.com")
            )
            .mappings()
            .one()
        )

    assert dict(user) == {"email": "demo@example.com", "handle": "demo"}


def test_all_seeded_demo_users_are_persisted():
    with engine.connect() as connection:
        seeded_users = (
            connection.execute(
                select(users.c.id, users.c.email, users.c.handle).where(
                    users.c.email.in_(fixture.email for fixture in DEMO_USERS)
                )
            )
            .mappings()
            .all()
        )

    assert {(user["id"], user["email"], user["handle"]) for user in seeded_users} == {
        (fixture.id, fixture.email, fixture.handle) for fixture in DEMO_USERS
    }


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


def test_registration_authenticates_and_persists_the_normalized_account():
    client = TestClient(app)
    handle = f"nueva_{uuid4().hex[:8]}"
    email = f"{handle}@Example.com"

    response = client.post(
        "/api/v1/auth/register",
        headers={"Origin": "http://testserver"},
        json={
            "name": "  Nueva Foodie  ",
            "email": email,
            "handle": f"@{handle.upper()}",
            "nationality": "cl",
            "password": "a-long-enough-password",
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["handle"] == handle
    assert response.json()["user"]["email"] == email.lower()

    session_response = client.get("/api/v1/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"]["handle"] == handle

    with engine.connect() as connection:
        persisted = (
            connection.execute(
                select(users.c.handle, users.c.name, users.c.nationality, users.c.email).where(
                    users.c.handle == handle
                )
            )
            .mappings()
            .one()
        )
    assert dict(persisted) == {
        "handle": handle,
        "name": "Nueva Foodie",
        "nationality": "CL",
        "email": email.lower(),
    }

    returning = TestClient(app)
    login_response = returning.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": email.lower(), "password": "a-long-enough-password"},
    )
    assert login_response.status_code == 204


def test_registration_conflicts_name_the_field_and_ignore_case():
    client = TestClient(app)
    taken_handle = f"nueva_{uuid4().hex[:8]}"
    taken_email = f"{taken_handle}@example.com"
    registration = {
        "name": "Nueva Foodie",
        "email": taken_email,
        "handle": taken_handle,
        "nationality": "CL",
        "password": "a-long-enough-password",
    }

    assert (
        client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://testserver"},
            json=registration,
        ).status_code
        == 201
    )

    same_email_upper = dict(
        registration, email=taken_email.upper(), handle=f"otra_{uuid4().hex[:8]}"
    )
    conflicting_email = TestClient(app).post(
        "/api/v1/auth/register",
        headers={"Origin": "http://testserver"},
        json=same_email_upper,
    )
    assert conflicting_email.status_code == 409
    assert conflicting_email.json()["detail"]["field"] == "email"

    same_handle = dict(registration, email=f"otra_{uuid4().hex[:8]}@example.com")
    conflicting_handle = TestClient(app).post(
        "/api/v1/auth/register",
        headers={"Origin": "http://testserver"},
        json=same_handle,
    )
    assert conflicting_handle.status_code == 409
    assert conflicting_handle.json()["detail"]["field"] == "handle"

    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count()).select_from(users).where(users.c.email == taken_email)
            )
            == 1
        )


def test_seeded_handles_are_stored_without_the_at_sign():
    with engine.connect() as connection:
        handles = set(
            connection.scalars(
                select(users.c.handle).where(users.c.id.in_(fixture.id for fixture in DEMO_USERS))
            ).all()
        )

    assert handles == {fixture.handle for fixture in DEMO_USERS}
    assert not any(handle.startswith("@") for handle in handles)


def test_demo_users_have_independent_sessions_and_revocations():
    sender = TestClient(app)
    receiver = TestClient(app)

    for client, fixture in zip((sender, receiver), DEMO_USERS[:2], strict=True):
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://testserver"},
            json={"email": fixture.email, "password": fixture.password},
        )
        assert response.status_code == 204
        assert client.get("/api/v1/auth/session").json()["user"]["email"] == fixture.email

    assert (
        sender.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"}).status_code
        == 204
    )
    assert sender.get("/api/v1/auth/session").status_code == 401
    assert receiver.get("/api/v1/auth/session").json()["user"]["email"] == DEMO_USERS[1].email


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


def authenticated_client(email="demo@example.com", password="demo-password") -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://testserver"},
        json={"email": email, "password": password},
    )
    assert response.status_code == 204
    return client


def test_restaurant_collection_pages_by_cursor_and_searches_with_postgresql():
    client = authenticated_client()

    first = client.get("/api/v1/restaurants?limit=3")
    repeated = client.get("/api/v1/restaurants?limit=3")

    assert first.status_code == 200
    assert first.json() == repeated.json()
    assert len(first.json()["items"]) == 3
    assert all(restaurant["cuisine_styles"] for restaurant in first.json()["items"])
    assert all("latitude" in restaurant for restaurant in first.json()["items"])

    walked = []
    cursor = first.json()["next_cursor"]
    walked.extend(restaurant["id"] for restaurant in first.json()["items"])
    while cursor:
        page = client.get(f"/api/v1/restaurants?limit=3&cursor={cursor}").json()
        walked.extend(restaurant["id"] for restaurant in page["items"])
        cursor = page["next_cursor"]

    assert len(walked) == len(set(walked))
    assert len(walked) >= len(RESTAURANTS)

    # Accents and case are folded for search but not for duplicate detection.
    found = client.get("/api/v1/restaurants?q=CAFE").json()
    assert "Café Ñielol" in [restaurant["name"] for restaurant in found["items"]]

    assert client.get("/api/v1/restaurants?limit=101").status_code == 422
    assert client.get("/api/v1/restaurants?q=c").status_code == 422
    assert client.get("/api/v1/restaurants?cursor=roto").status_code == 422

    catalogue = client.get("/api/v1/cuisine-styles")
    assert catalogue.status_code == 200
    assert {style["slug"] for style in catalogue.json()} == {style.slug for style in CUISINE_STYLES}


def test_map_rectangle_uses_the_coordinate_index_with_postgresql():
    client = authenticated_client()

    santiago = client.get("/api/v1/restaurants/map?south=-33.5&west=-70.7&north=-33.4&east=-70.55")
    valparaiso = client.get("/api/v1/restaurants/map?south=-33.1&west=-71.7&north=-33.0&east=-71.5")

    assert santiago.status_code == 200
    assert valparaiso.status_code == 200
    santiago_names = {restaurant["name"] for restaurant in santiago.json()["items"]}
    valparaiso_names = {restaurant["name"] for restaurant in valparaiso.json()["items"]}
    assert "Cocina del Barrio" in santiago_names
    assert "Ancla y Sal" in valparaiso_names
    assert santiago_names & valparaiso_names == set()
    assert santiago.json()["truncated"] is False

    empty = client.get("/api/v1/restaurants/map?south=-10&west=-70&north=-5&east=-65")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "truncated": False}

    assert (
        client.get("/api/v1/restaurants/map?south=-40&west=-80&north=-10&east=-60").status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/restaurants/map?south=-33.0&west=-70.7&north=-33.5&east=-70.5"
        ).status_code
        == 422
    )

    # With a seed of a few rows the planner prefers a sequential scan whatever
    # indexes exist. Disabling that choice shows whether the query is sargable
    # against the coordinate index at all, which is what the index is for.
    with engine.connect() as connection:
        connection.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text(
                    "EXPLAIN SELECT id FROM restaurants "
                    "WHERE latitude BETWEEN -33.5 AND -33.4 "
                    "AND longitude BETWEEN -70.7 AND -70.55"
                )
            )
        )
    assert "ix_restaurants_location" in plan


def test_nearby_orders_by_measured_distance_with_postgresql():
    client = authenticated_client()
    centre = "latitude=-33.4372&longitude=-70.6506"

    close_by = client.get(f"/api/v1/restaurants/nearby?{centre}&radius=3000")
    wide = client.get(f"/api/v1/restaurants/nearby?{centre}&radius=50000")
    chilean = client.get(f"/api/v1/restaurants/nearby?{centre}&radius=50000&cuisine_style=chilena")

    assert close_by.status_code == 200
    distances = [restaurant["distance_m"] for restaurant in wide.json()["items"]]
    assert distances == sorted(distances)
    assert all(distance <= 50_000 for distance in distances)
    assert len(close_by.json()["items"]) < len(wide.json()["items"])
    assert wide.json()["truncated"] is False

    assert chilean.status_code == 200
    assert 0 < len(chilean.json()["items"]) < len(wide.json()["items"])
    assert all(
        any(style["slug"] == "chilena" for style in restaurant["cuisine_styles"])
        for restaurant in chilean.json()["items"]
    )

    empty = client.get("/api/v1/restaurants/nearby?latitude=-10&longitude=-65&radius=1000")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "truncated": False}

    assert client.get(f"/api/v1/restaurants/nearby?{centre}&radius=0").status_code == 422
    assert client.get(f"/api/v1/restaurants/nearby?{centre}&radius=60000").status_code == 422
    assert (
        client.get(
            f"/api/v1/restaurants/nearby?{centre}&radius=1000&cuisine_style=marciana"
        ).status_code
        == 422
    )


def test_restaurant_page_and_gallery_apply_visibility_with_postgresql():
    owner, other = DEMO_USERS[0], DEMO_USERS[1]
    owner_client, other_client = TestClient(app), TestClient(app)
    for client, user in ((owner_client, owner), (other_client, other)):
        assert (
            client.post(
                "/api/v1/auth/login",
                headers={"Origin": "http://testserver"},
                json={"email": user.email, "password": user.password},
            ).status_code
            == 204
        )

    private_review = next(fixture for fixture in REVIEW_FIXTURES if fixture.visibility == "private")
    restaurant_id = private_review.restaurant_id

    own_page = owner_client.get(f"/api/v1/restaurants/{restaurant_id}").json()
    seen_page = other_client.get(f"/api/v1/restaurants/{restaurant_id}").json()
    own_gallery = owner_client.get(f"/api/v1/restaurants/{restaurant_id}/photos").json()
    seen_gallery = other_client.get(f"/api/v1/restaurants/{restaurant_id}/photos").json()

    assert own_page["name"] and own_page["cuisine_styles"]
    assert own_page["ratings"]["total"] == own_page["counters"]["evaluations"]
    assert len(own_page["ratings"]["criteria"]) == 4
    # The same averages for both observers: the summary is public only.
    assert own_page["ratings"] == seen_page["ratings"]
    assert own_page["viewer"] == {"following": True}
    assert seen_page["viewer"] == {"following": False}

    own_ids = {photo["id"] for photo in own_gallery["items"]}
    seen_ids = {photo["id"] for photo in seen_gallery["items"]}
    assert str(private_review.photo_id) in own_ids
    assert str(private_review.photo_id) not in seen_ids
    assert own_page["counters"]["photos"] == len(own_gallery["items"])
    assert seen_page["counters"]["photos"] == len(seen_gallery["items"])
    assert seen_page["counters"]["photos"] < own_page["counters"]["photos"]

    # The content of a photograph is authorized against the photograph itself
    # now, so it still reaches its author and nobody else.
    content = f"/api/v1/photos/{private_review.photo_id}/content"
    assert owner_client.get(content).status_code == 200
    assert other_client.get(content).status_code == 404
    public_photo = next(fixture for fixture in REVIEW_FIXTURES if fixture.visibility == "public")
    assert other_client.get(f"/api/v1/photos/{public_photo.photo_id}/content").status_code == 200

    assert owner_client.get(f"/api/v1/restaurants/{uuid4()}").status_code == 404
    assert owner_client.get(f"/api/v1/restaurants/{uuid4()}/photos").status_code == 404
    assert (
        owner_client.get(f"/api/v1/restaurants/{restaurant_id}/photos?cursor=roto").status_code
        == 422
    )


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
    # The page is a superset of what creation answers: the same resource plus
    # the blocks that depend on who is asking.
    assert created.json().items() <= shown.json().items()
    assert shown.json()["counters"] == {
        "photos": 0,
        "reviews": 0,
        "evaluations": 0,
        "visits": 0,
        "followers": 0,
    }
    assert shown.json()["viewer"] == {"following": False}

    duplicate_payload = {
        **payload,
        "name": "  LABORATORIO   GASTRONÓMICO ",
        "address": " monjitas 550, SANTIAGO ",
    }
    duplicate = client.post("/api/v1/restaurants", headers=origin, json=duplicate_payload)
    assert duplicate.status_code == 409
    # The interface has to be able to send the person to the page that exists.
    assert duplicate.json()["detail"]["restaurant"] == {
        "id": str(restaurant_id),
        "name": created.json()["name"],
    }

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


def test_publishing_a_photograph_and_reviewing_it_with_postgresql(tmp_path):
    client = authenticated_client()
    storage = LocalMediaStorage(tmp_path)
    app.dependency_overrides[get_media_storage] = lambda: storage
    image = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(image, format="PNG")
    try:
        # First the photograph, which is what gets published.
        published = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={
                "restaurant_id": str(RESTAURANTS[0].id),
                "kind": "dish",
                "dish_name": "Ceviche docente",
                "visibility": "public",
            },
            files={"photo": ("dish.png", image.getvalue(), "image/png")},
        )
        assert published.status_code == 201
        photo_payload = published.json()

        # Then the review of it, which is another action.
        response = client.post(
            "/api/v1/reviews",
            headers={"Origin": "http://testserver"},
            json={
                "photo_id": photo_payload["id"],
                "rating": 5,
                "text": "Reseña creada por la prueba de integración",
                "visibility": "public",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["rating"] == 5
        assert payload["dish_name"] == "Ceviche docente"

        with engine.connect() as connection:
            persisted_review = (
                connection.execute(select(reviews).where(reviews.c.id == UUID(payload["id"])))
                .mappings()
                .one()
            )
            persisted_photo = (
                connection.execute(select(photos).where(photos.c.id == UUID(photo_payload["id"])))
                .mappings()
                .one()
            )
        assert persisted_review["photo_id"] == persisted_photo["id"]
        assert persisted_review["visibility"] == "public"
        assert persisted_photo["dish_name"] == "Ceviche docente"
        assert (tmp_path / persisted_photo["storage_key"]).is_file()

        downloaded = client.get(photo_payload["content_url"])
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"] == "image/png"
        assert downloaded.content == image.getvalue()

        # A second review over the same photograph names the first.
        duplicate = client.post(
            "/api/v1/reviews",
            headers={"Origin": "http://testserver"},
            json={
                "photo_id": photo_payload["id"],
                "rating": 3,
                "text": "Otra opinión",
                "visibility": "public",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["review"]["id"] == payload["id"]
    finally:
        app.dependency_overrides.clear()


def test_profile_and_activity_apply_visibility_with_postgresql():
    owner, author = DEMO_USERS[0], DEMO_USERS[1]
    owner_client, author_client = TestClient(app), TestClient(app)
    for client, user in ((owner_client, owner), (author_client, author)):
        assert (
            client.post(
                "/api/v1/auth/login",
                headers={"Origin": "http://testserver"},
                json={"email": user.email, "password": user.password},
            ).status_code
            == 204
        )

    own_profile = owner_client.get(f"/api/v1/users/{owner.handle.upper()}").json()
    own_activity = owner_client.get(f"/api/v1/users/{owner.handle}/activity").json()
    seen_profile = author_client.get(f"/api/v1/users/{owner.handle}").json()
    seen_activity = author_client.get(f"/api/v1/users/{owner.handle}/activity").json()

    private_review = next(fixture for fixture in REVIEW_FIXTURES if fixture.visibility == "private")

    def activity_ids(page):
        return {
            item["photo"]["photos"][0]["id"]
            if item["type"] == "photo"
            else item[item["type"]]["id"]
            for item in page["items"]
        }

    own_ids = activity_ids(own_activity)
    seen_ids = activity_ids(seen_activity)

    assert own_profile["handle"] == owner.handle
    assert own_profile["nationality"] == {"code": "CL", "name": "Chile"}
    # Other tests in this module publish reviews as this same user, so the
    # assertions compare what each observer gets rather than fixed contents.
    assert str(private_review.id) in own_ids
    assert str(private_review.id) not in seen_ids
    assert seen_ids < own_ids
    assert own_profile["counters"]["activity"] == len(own_activity["items"])
    assert seen_profile["counters"]["activity"] == len(seen_activity["items"])
    assert seen_profile["counters"]["activity"] < own_profile["counters"]["activity"]
    assert seen_profile["viewer"] == {"is_self": False, "following": False, "followed_by": True}

    assert owner_client.get("/api/v1/users/nadie_aqui").status_code == 404
    assert owner_client.get(f"/api/v1/users/{owner.handle}/activity?cursor=roto").status_code == 422


def test_seeded_feed_and_review_detail_work_with_postgresql():
    client = authenticated_client()

    response = client.get("/api/v1/feed?limit=50")
    assert response.status_code == 200
    # The feed mixes classes of activity, each under a key named after its
    # type. A photo item carries a collection of photographs.
    activity_ids = [
        item["photo"]["photos"][0]["id"] if item["type"] == "photo" else item[item["type"]]["id"]
        for item in response.json()["items"]
    ]
    review_ids = [
        item["review"]["id"] for item in response.json()["items"] if item["type"] == "review"
    ]
    fixture_ids = [
        review_id
        for review_id in review_ids
        if review_id in {str(fixture.id) for fixture in REVIEW_FIXTURES}
    ]
    assert fixture_ids == [
        str(REVIEW_FIXTURES[0].id),
        str(REVIEW_FIXTURES[1].id),
        str(REVIEW_FIXTURES[3].id),
    ]
    assert str(REVIEW_FIXTURES[2].id) not in activity_ids
    visit_ids = {
        item["visit"]["id"] for item in response.json()["items"] if item["type"] == "visit"
    }
    assert {str(fixture.id) for fixture in VISIT_FIXTURES if fixture.visibility == "public"} & (
        visit_ids
    )
    assert str(VISIT_FIXTURES[1].id) not in activity_ids

    private = client.get(f"/api/v1/reviews/{REVIEW_FIXTURES[2].id}")
    assert private.status_code == 200
    assert private.json()["visibility"] == "private"
    photo = client.get(private.json()["photo"]["content_url"])
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/webp"

    other_client = authenticated_client("demo2@example.com")
    assert other_client.get(f"/api/v1/reviews/{REVIEW_FIXTURES[2].id}").status_code == 404
    assert other_client.get(f"/api/v1/reviews/{uuid4()}").status_code == 404

    empty_client = authenticated_client("empty@example.com")
    assert empty_client.get("/api/v1/feed").json() == {"items": [], "next_cursor": None}


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
                search_name=normalize_restaurant_search_text(edited_name),
                identity_key=restaurant_identity_key(edited_name, fixture.address),
            )
        )

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert (
            connection.scalar(select(restaurants.c.name).where(restaurants.c.id == fixture.id))
            == edited_name
        )
