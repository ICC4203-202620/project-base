from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.core.rating_criteria import RATING_CRITERIA, RATING_CRITERION_SLUGS
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, EVALUATION_FIXTURES, RESTAURANTS
from app.db.schema import metadata
from app.main import app
from app.media.storage import LocalMediaLocation
from app.services import evaluations as evaluation_service
from app.services import feed as feed_service
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import users as user_service
from app.services.auth import AuthenticatedSession

AUTHOR = DEMO_USERS[0]
OTHER = DEMO_USERS[1]
# The seed already holds two public evaluations of this one, plus a private
# one of another restaurant.
EVALUATED = RESTAURANTS[0].id
UNEVALUATED = RESTAURANTS[6].id
FULL_RATINGS = {"comida": 5, "servicio": 4, "ambiente": 3, "precio-calidad": 4}


class MemoryStorage:
    def store(self, *, media_id, stream, content_type, extension):
        stream.read()
        return f"photos/{media_id}.{extension}"

    def delete(self, storage_key):
        del storage_key

    def resolve(self, storage_key):
        return LocalMediaLocation(path=storage_key)


@pytest.fixture
def seeded_database(monkeypatch):
    database = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(database)
    for module in (
        seed_module,
        evaluation_service,
        photo_service,
        restaurant_service,
        feed_service,
        user_service,
    ):
        monkeypatch.setattr(module, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=MemoryStorage())
    return database


def session(user=AUTHOR):
    return AuthenticatedSession(
        id=uuid4(),
        user_id=user.id,
        email=user.email,
        handle=user.handle,
        name=user.name,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    )


def png_file() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(stream, format="PNG")
    stream.seek(0)
    return stream


def evaluate(restaurant_id=UNEVALUATED, author=AUTHOR, **overrides):
    arguments = {
        "author_id": author.id,
        "restaurant_id": restaurant_id,
        "ratings": dict(FULL_RATINGS),
        "comment": "Muy bien atendido",
        "visibility": "public",
    }
    arguments.update(overrides)
    return evaluation_service.create_evaluation(**arguments)


def a_photo(kind="menu", *, author=AUTHOR, restaurant_id=UNEVALUATED, visibility="public"):
    return photo_service.store_photo(
        author_id=author.id,
        restaurant_id=restaurant_id,
        kind=kind,
        dish_name="Merluza austral" if kind == "dish" else None,
        caption=None,
        visibility=visibility,
        photo_stream=png_file(),
        declared_content_type="image/png",
        storage=MemoryStorage(),
    )


def test_an_evaluation_carries_every_criterion_and_a_comment(seeded_database):
    del seeded_database

    evaluation = evaluate()

    assert {rating.criterion for rating in evaluation.ratings} == set(RATING_CRITERION_SLUGS)
    assert evaluation.comment == "Muy bien atendido"
    assert evaluation.visibility == "public"


def test_the_criteria_are_all_required_exactly_once(seeded_database):
    del seeded_database
    partial = dict(FULL_RATINGS)
    partial.pop("ambiente")

    with pytest.raises(evaluation_service.InvalidEvaluationError) as missing:
        evaluate(ratings=partial)
    with pytest.raises(evaluation_service.InvalidEvaluationError) as unknown:
        evaluate(ratings={**FULL_RATINGS, "estacionamiento": 4})

    assert "missing" in missing.value.reason
    assert "unknown" in unknown.value.reason


def test_the_ratings_the_comment_and_the_visibility_are_validated(seeded_database):
    del seeded_database

    for overrides in (
        {"ratings": {**FULL_RATINGS, "comida": 0}},
        {"ratings": {**FULL_RATINGS, "comida": 6}},
        {"ratings": {**FULL_RATINGS, "comida": 4.5}},
        {"ratings": {**FULL_RATINGS, "comida": True}},
        {"comment": "   "},
        {"visibility": "secreta"},
    ):
        with pytest.raises(evaluation_service.InvalidEvaluationError):
            evaluate(**overrides)


def test_one_evaluation_per_person_and_restaurant(seeded_database):
    del seeded_database
    first = evaluate()

    with pytest.raises(evaluation_service.DuplicateEvaluationError) as raised:
        evaluate(comment="Otra opinión")

    assert raised.value.existing_id == first.id
    # Another person may still evaluate the same restaurant.
    assert evaluate(author=OTHER)


def test_an_evaluation_of_a_restaurant_that_does_not_exist(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        evaluate(restaurant_id=uuid4())


def test_your_own_menu_photograph_can_be_associated(seeded_database):
    del seeded_database
    mine = a_photo()

    assert evaluate(photo_ids=[mine.id]).photo_ids == (mine.id,)


def test_a_photograph_of_a_dish_cannot_be_associated(seeded_database):
    del seeded_database
    restaurant = RESTAURANTS[7].id
    of_a_dish = a_photo("dish", restaurant_id=restaurant)

    with pytest.raises(evaluation_service.InvalidEvaluationError) as raised:
        evaluate(restaurant_id=restaurant, photo_ids=[of_a_dish.id])

    assert "menu or venue" in raised.value.reason


def test_someone_elses_photograph_cannot_be_associated(seeded_database):
    del seeded_database
    restaurant = RESTAURANTS[8].id
    theirs = a_photo(author=OTHER, restaurant_id=restaurant)

    with pytest.raises(evaluation_service.InvalidEvaluationError) as raised:
        evaluate(restaurant_id=restaurant, photo_ids=[theirs.id])

    assert "your own" in raised.value.reason


def test_a_photograph_of_another_restaurant_cannot_be_associated(seeded_database):
    del seeded_database
    elsewhere = a_photo(restaurant_id=RESTAURANTS[9].id)

    with pytest.raises(evaluation_service.InvalidEvaluationError) as raised:
        evaluate(photo_ids=[elsewhere.id])

    assert "restaurant evaluated" in raised.value.reason


def test_a_photograph_that_does_not_exist_or_repeats(seeded_database):
    del seeded_database
    mine = a_photo()

    with pytest.raises(evaluation_service.InvalidEvaluationError):
        evaluate(photo_ids=[uuid4()])
    with pytest.raises(evaluation_service.InvalidEvaluationError):
        evaluate(photo_ids=[mine.id, mine.id])


def test_an_evaluation_is_never_more_visible_than_its_photographs(seeded_database):
    del seeded_database
    private_photo = a_photo(visibility="private")

    with pytest.raises(evaluation_service.InvalidEvaluationError):
        evaluate(photo_ids=[private_photo.id], visibility="public")
    assert evaluate(photo_ids=[private_photo.id], visibility="private")


def test_the_summary_averages_only_public_evaluations(seeded_database):
    del seeded_database

    page = restaurant_service.get_restaurant_detail(EVALUATED, viewer_id=AUTHOR.id)
    seen_by_other = restaurant_service.get_restaurant_detail(EVALUATED, viewer_id=OTHER.id)

    assert page.ratings.total == 2
    assert page.ratings.average == 3.8
    # Two observers read the same number on the same page.
    assert seen_by_other.ratings == page.ratings
    assert page.counters.evaluations == page.ratings.total


def test_a_private_evaluation_moves_no_average_not_even_for_its_author(seeded_database):
    del seeded_database
    before = restaurant_service.get_restaurant_detail(UNEVALUATED, viewer_id=AUTHOR.id)

    private = evaluate(visibility="private", ratings=dict.fromkeys(RATING_CRITERION_SLUGS, 5))
    after = restaurant_service.get_restaurant_detail(UNEVALUATED, viewer_id=AUTHOR.id)
    own_profile = user_service.get_activity(AUTHOR.handle, viewer_id=AUTHOR.id, limit=50)

    assert before.ratings.total == after.ratings.total == 0
    assert after.ratings.average is None
    # It does appear in the profile of whoever wrote it, which is where the
    # statement places it.
    assert private.id in {
        item["evaluation"]["id"] for item in own_profile["items"] if item["type"] == "evaluation"
    }


def test_the_list_of_a_restaurant_holds_what_the_summary_averages(seeded_database):
    del seeded_database

    page = restaurant_service.get_restaurant_detail(EVALUATED, viewer_id=AUTHOR.id)
    listed = evaluation_service.list_restaurant_evaluations(EVALUATED, limit=50)

    assert len(listed["items"]) == page.ratings.total == page.counters.evaluations
    assert {item["visibility"] for item in listed["items"]} == {"public"}
    assert listed["items"][0]["created_at"] >= listed["items"][-1]["created_at"]
    assert listed["items"][0]["ratings"]
    assert listed["next_cursor"] is None


def test_the_list_pages_by_cursor(seeded_database):
    del seeded_database
    every = [
        item["id"]
        for item in evaluation_service.list_restaurant_evaluations(EVALUATED, limit=50)["items"]
    ]

    seen = []
    cursor = None
    while True:
        page = evaluation_service.list_restaurant_evaluations(EVALUATED, limit=1, cursor=cursor)
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == every


def test_an_evaluation_is_addressable_and_respects_its_visibility(seeded_database):
    del seeded_database
    public = EVALUATION_FIXTURES[0]
    private = EVALUATION_FIXTURES[2]

    seen = evaluation_service.get_evaluation(public.id, viewer_id=AUTHOR.id)
    own = evaluation_service.get_evaluation(private.id, viewer_id=AUTHOR.id)

    assert seen["id"] == public.id
    assert seen["author"]["handle"] == OTHER.handle
    assert len(seen["ratings"]) == len(RATING_CRITERIA)
    assert seen["photos"]
    assert own["visibility"] == "private"
    with pytest.raises(evaluation_service.EvaluationNotFoundError):
        evaluation_service.get_evaluation(private.id, viewer_id=OTHER.id)
    with pytest.raises(evaluation_service.EvaluationNotFoundError):
        evaluation_service.get_evaluation(uuid4(), viewer_id=AUTHOR.id)


def test_a_restaurant_without_evaluations_is_not_an_error(seeded_database):
    del seeded_database

    page = restaurant_service.get_restaurant_detail(UNEVALUATED, viewer_id=AUTHOR.id)
    listed = evaluation_service.list_restaurant_evaluations(UNEVALUATED, limit=50)

    assert page.ratings == restaurant_service.RatingSummary(criteria=(), average=None, total=0)
    assert listed == {"items": [], "next_cursor": None}


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

        def begin(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(evaluation_service, "engine", BrokenEngine())
    with pytest.raises(evaluation_service.EvaluationStoreError):
        evaluate()
    with pytest.raises(evaluation_service.EvaluationStoreError):
        evaluation_service.get_evaluation(EVALUATION_FIXTURES[0].id, viewer_id=AUTHOR.id)


def test_the_endpoints_answer_the_contract(seeded_database):
    del seeded_database
    app.dependency_overrides[get_current_session] = session
    client = TestClient(app)
    origin = {"Origin": "http://testserver"}
    body = {
        "restaurant_id": str(UNEVALUATED),
        "ratings": FULL_RATINGS,
        "comment": "Muy bien atendido",
        "visibility": "public",
    }
    try:
        criteria = client.get("/api/v1/rating-criteria")
        created = client.post("/api/v1/evaluations", headers=origin, json=body)
        duplicate = client.post("/api/v1/evaluations", headers=origin, json=body)
        unknown_restaurant = client.post(
            "/api/v1/evaluations",
            headers=origin,
            json={**body, "restaurant_id": str(uuid4())},
        )
        partial = client.post(
            "/api/v1/evaluations",
            headers=origin,
            json={**body, "restaurant_id": str(RESTAURANTS[7].id), "ratings": {"comida": 4}},
        )
        untrusted = client.post(
            "/api/v1/evaluations",
            headers={"Origin": "http://evil.example"},
            json=body,
        )
        shown = client.get(f"/api/v1/evaluations/{created.json()['id']}")
        listed = client.get(f"/api/v1/restaurants/{EVALUATED}/evaluations")
        listed_unknown = client.get(f"/api/v1/restaurants/{uuid4()}/evaluations")
    finally:
        app.dependency_overrides.clear()

    assert [criterion["slug"] for criterion in criteria.json()] == list(RATING_CRITERION_SLUGS)
    assert created.status_code == 201
    assert created.headers["location"] == f"/api/v1/evaluations/{created.json()['id']}"
    assert len(created.json()["ratings"]) == len(RATING_CRITERIA)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["evaluation"]["id"] == created.json()["id"]
    assert unknown_restaurant.status_code == 404
    assert partial.status_code == 422
    assert untrusted.status_code == 403
    assert shown.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert listed_unknown.status_code == 404


def test_the_routes_require_a_session():
    client = TestClient(app)

    assert client.get("/api/v1/rating-criteria").status_code == 401
    assert client.get(f"/api/v1/evaluations/{uuid4()}").status_code == 401
    assert client.get(f"/api/v1/restaurants/{EVALUATED}/evaluations").status_code == 401
    assert (
        client.post(
            "/api/v1/evaluations",
            json={
                "restaurant_id": str(UNEVALUATED),
                "ratings": FULL_RATINGS,
                "comment": "x",
                "visibility": "public",
            },
        ).status_code
        == 401
    )
