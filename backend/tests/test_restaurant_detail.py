from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, RESTAURANTS, REVIEW_FIXTURES
from app.db.schema import metadata, photos
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services.cursors import InvalidCursorError

# Restaurant one holds the private review of `demo` and public ones by the
# other two accounts, which is what makes the difference between observers
# visible from the seed alone.
WITH_ACTIVITY = RESTAURANTS[0].id
PRIVATE_REVIEW = REVIEW_FIXTURES[2]
OWNER = DEMO_USERS[0]
OTHER = DEMO_USERS[1]


class FixtureStorage:
    def store(self, *, media_id, stream, content_type, extension):
        del content_type, stream
        return f"test/photos/{media_id}.{extension}"

    def delete(self, storage_key):
        del storage_key


@pytest.fixture
def seeded_database(monkeypatch):
    database = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(database)
    monkeypatch.setattr(seed_module, "engine", database)
    monkeypatch.setattr(restaurant_service, "engine", database)
    monkeypatch.setattr(photo_service, "engine", database)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def detail(restaurant_id=WITH_ACTIVITY, viewer=OWNER):
    return restaurant_service.get_restaurant_detail(restaurant_id, viewer_id=viewer.id)


def gallery(restaurant_id=WITH_ACTIVITY, viewer=OWNER, limit=50, cursor=None):
    return photo_service.list_restaurant_photos(
        restaurant_id, viewer_id=viewer.id, limit=limit, cursor=cursor
    )


def test_the_migration_left_every_photograph_with_its_review_visibility(seeded_database):
    with seeded_database.connect() as connection:
        stored = {
            row["id"]: (row["visibility"], row["kind"])
            for row in connection.execute(
                select(photos.c.id, photos.c.visibility, photos.c.kind)
            ).mappings()
        }

    assert stored[PRIVATE_REVIEW.photo_id] == ("private", "dish")
    for fixture in REVIEW_FIXTURES:
        assert stored[fixture.photo_id] == (fixture.visibility, "dish")


def test_the_page_carries_what_the_screen_needs_without_the_gallery(seeded_database):
    del seeded_database

    page = detail()

    assert page.id == WITH_ACTIVITY
    assert page.name == RESTAURANTS[0].name
    assert page.cuisine_styles
    assert page.counters.followers == 1
    assert page.viewer.following is True
    # Two public evaluations in the seed; the private one moves nothing.
    assert page.ratings.total == 2
    assert page.ratings.average == 3.8
    assert {
        criterion.criterion: criterion.average for criterion in page.ratings.criteria
    } == {"comida": 4.0, "servicio": 3.0, "ambiente": 4.5, "precio-calidad": 3.5}
    assert page.counters.evaluations == page.ratings.total
    # Three public check-ins in the seed, by three different people.
    assert page.counters.visits == 3
    assert not hasattr(page, "photos")


def test_a_restaurant_without_any_activity_is_not_an_error(seeded_database):
    del seeded_database
    quiet = RESTAURANTS[6].id

    page = detail(quiet)

    assert page.counters.photos == 0
    assert page.counters.reviews == 0
    assert page.counters.followers == 0
    assert page.viewer.following is False
    assert gallery(quiet).items == ()


def test_a_private_photograph_is_seen_by_its_author_and_by_nobody_else(seeded_database):
    del seeded_database

    seen_by_author = gallery(viewer=OWNER)
    seen_by_other = gallery(viewer=OTHER)

    assert PRIVATE_REVIEW.photo_id in {photo.id for photo in seen_by_author.items}
    assert PRIVATE_REVIEW.photo_id not in {photo.id for photo in seen_by_other.items}
    assert len(seen_by_author.items) == len(seen_by_other.items) + 1


def test_counters_match_what_each_observer_can_list(seeded_database):
    del seeded_database

    for viewer in (OWNER, OTHER, DEMO_USERS[2]):
        page = detail(viewer=viewer)
        assert page.counters.photos == len(gallery(viewer=viewer).items), viewer.handle


def test_the_gallery_says_which_review_a_photograph_carries(seeded_database):
    del seeded_database

    by_photo = {photo.id: photo for photo in gallery().items}

    assert by_photo[PRIVATE_REVIEW.photo_id].review_id == PRIVATE_REVIEW.id
    assert by_photo[PRIVATE_REVIEW.photo_id].kind == "dish"
    assert by_photo[PRIVATE_REVIEW.photo_id].author.handle == OWNER.handle
    assert by_photo[PRIVATE_REVIEW.photo_id].content_url.endswith(
        f"/api/v1/photos/{PRIVATE_REVIEW.photo_id}/content"
    )


def test_the_gallery_pages_by_cursor_without_repeating_or_skipping(seeded_database):
    del seeded_database
    every_photo = [photo.id for photo in gallery().items]
    assert len(every_photo) > 1

    seen = []
    cursor = None
    while True:
        page = gallery(limit=1, cursor=cursor)
        seen.extend(photo.id for photo in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == every_photo
    assert len(seen) == len(set(seen))


def test_a_cursor_this_api_did_not_issue_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(InvalidCursorError):
        gallery(cursor="no-es-un-cursor")


def test_an_unknown_restaurant_is_not_an_empty_page(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        detail(uuid4())


def test_store_failures_are_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    monkeypatch.setattr(photo_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        detail()
    with pytest.raises(photo_service.PhotoStoreError):
        gallery()
