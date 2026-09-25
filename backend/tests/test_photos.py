from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_session
from app.db import seed as seed_module
from app.db.fixtures import DEMO_USERS, PHOTO_FIXTURES, RESTAURANTS, REVIEW_FIXTURES
from app.db.schema import metadata, photos
from app.main import app
from app.media.storage import LocalMediaLocation, MediaStorageError, get_media_storage
from app.services import feed as feed_service
from app.services import photos as photo_service
from app.services import restaurants as restaurant_service
from app.services import reviews as review_service
from app.services import users as user_service
from app.services.auth import AuthenticatedSession

AUTHOR = DEMO_USERS[0]
OTHER = DEMO_USERS[1]
RESTAURANT = RESTAURANTS[0].id


class MemoryStorage:
    def __init__(self, *, fail_store=False):
        self.fail_store = fail_store
        self.stored = []
        self.deleted = []

    def store(self, *, media_id, stream, content_type, extension):
        if self.fail_store:
            raise MediaStorageError
        key = f"photos/{media_id}.{extension}"
        self.stored.append(key)
        stream.read()
        return key

    def delete(self, storage_key):
        self.deleted.append(storage_key)

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
    for module in (seed_module, photo_service, restaurant_service, feed_service, user_service):
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


def publish(storage=None, **overrides):
    arguments = {
        "author_id": AUTHOR.id,
        "restaurant_id": RESTAURANT,
        "kind": "dish",
        "dish_name": "Merluza austral",
        "caption": None,
        "visibility": "public",
        "photo_stream": png_file(),
        "declared_content_type": "image/png",
        "storage": storage or MemoryStorage(),
    }
    arguments.update(overrides)
    return photo_service.store_photo(**arguments)


def test_a_photograph_is_published_on_its_own(seeded_database):
    del seeded_database
    storage = MemoryStorage()

    photo = publish(storage=storage, caption="  Con pebre  ")

    assert photo.kind == "dish"
    assert photo.dish_name == "Merluza austral"
    assert photo.caption == "Con pebre"
    assert photo.visibility == "public"
    assert photo.content_url == f"/api/v1/photos/{photo.id}/content"
    assert storage.stored == [photo.storage_key]

    metadata_of = photo_service.get_photo(photo.id, viewer_id=AUTHOR.id)
    assert metadata_of.dish_name == "Merluza austral"
    assert metadata_of.author.handle == AUTHOR.handle
    # Published on its own: no review carries it.
    assert metadata_of.review_id is None


def test_the_dish_is_normalized_so_the_same_dish_groups(seeded_database):
    photo = publish(dish_name="  Ají   de   Gallina ")

    with seeded_database.connect() as connection:
        stored = (
            connection.execute(
                select(photos.c.dish_name, photos.c.search_dish_name).where(photos.c.id == photo.id)
            )
            .mappings()
            .one()
        )

    assert stored["dish_name"] == "Ají   de   Gallina"
    assert stored["search_dish_name"] == "aji de gallina"


def test_a_photograph_of_a_dish_has_to_name_the_dish(seeded_database):
    del seeded_database

    for overrides in (
        {"dish_name": None},
        {"dish_name": "   "},
        {"kind": "menu"},
        {"kind": "venue"},
        {"kind": "mural"},
        {"visibility": "secreta"},
    ):
        with pytest.raises(photo_service.InvalidPhotoPublicationError):
            publish(**overrides)


def test_the_file_is_validated_before_anything_is_stored(seeded_database):
    del seeded_database
    storage = MemoryStorage()

    with pytest.raises(photo_service.InvalidPhotoError):
        publish(storage=storage, declared_content_type="image/jpeg")
    with pytest.raises(photo_service.InvalidPhotoError):
        publish(storage=storage, photo_stream=BytesIO(b"not an image"))
    with pytest.raises(photo_service.InvalidPhotoError):
        publish(storage=storage, photo_stream=BytesIO(b""))

    assert storage.stored == []


def test_a_file_over_the_limit_is_rejected(seeded_database, monkeypatch):
    del seeded_database
    monkeypatch.setattr(photo_service.settings, "media_max_upload_bytes", 1)
    storage = MemoryStorage()

    with pytest.raises(photo_service.PhotoTooLargeError):
        publish(storage=storage)

    assert storage.stored == []


def test_a_restaurant_that_does_not_exist_leaves_no_row_and_no_object(seeded_database):
    storage = MemoryStorage()

    with pytest.raises(restaurant_service.RestaurantNotFoundError):
        publish(storage=storage, restaurant_id=uuid4())

    assert storage.deleted == storage.stored
    with seeded_database.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(photos)
                .where(photos.c.dish_name == "Merluza austral")
            )
            == 0
        )


def test_a_media_failure_leaves_no_row(seeded_database):
    with pytest.raises(photo_service.PhotoMediaError):
        publish(storage=MemoryStorage(fail_store=True))

    with seeded_database.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(photos)
                .where(photos.c.dish_name == "Merluza austral")
            )
            == 0
        )


def test_a_database_failure_removes_the_object(seeded_database, monkeypatch):
    del seeded_database
    storage = MemoryStorage()
    monkeypatch.setattr(
        photo_service,
        "run_transaction_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )

    with pytest.raises(photo_service.PhotoStoreError):
        publish(storage=storage)

    assert storage.deleted == storage.stored


def test_a_private_photograph_is_metadata_for_its_author_only(seeded_database):
    del seeded_database
    private = publish(visibility="private")

    assert photo_service.get_photo(private.id, viewer_id=AUTHOR.id).visibility == "private"
    with pytest.raises(photo_service.PhotoNotFoundError):
        photo_service.get_photo(private.id, viewer_id=OTHER.id)
    with pytest.raises(photo_service.PhotoNotFoundError):
        photo_service.get_photo(uuid4(), viewer_id=AUTHOR.id)


def test_a_published_photograph_shows_in_the_gallery_and_in_the_profile(seeded_database):
    del seeded_database
    photo = publish()

    gallery = photo_service.list_restaurant_photos(RESTAURANT, viewer_id=AUTHOR.id, limit=50)
    profile = user_service.get_activity(AUTHOR.handle, viewer_id=AUTHOR.id, limit=50)
    published = [item for item in profile["items"] if item["type"] == "photo"]

    assert photo.id in {item.id for item in gallery.items}
    assert photo.id in {item["photo"]["photos"][0]["id"] for item in published}


def test_a_photograph_with_a_review_is_activity_once(seeded_database):
    del seeded_database
    reviewed = REVIEW_FIXTURES[0]

    feed = feed_service.get_feed(DEMO_USERS[0].id, limit=50)
    photo_items = [item for item in feed["items"] if item["type"] == "photo"]
    review_items = [item for item in feed["items"] if item["type"] == "review"]

    # Its photograph never appears on its own; the review carries it.
    assert reviewed.photo_id not in {item["photo"]["photos"][0]["id"] for item in photo_items}
    assert str(reviewed.id) in {str(item["review"]["id"]) for item in review_items}
    # And the photographs published without a review do appear.
    assert {PHOTO_FIXTURES[0].id, PHOTO_FIXTURES[1].id} <= {
        item["photo"]["photos"][0]["id"] for item in photo_items
    }


def test_the_activity_item_carries_a_collection_from_the_start(seeded_database):
    del seeded_database

    feed = feed_service.get_feed(DEMO_USERS[0].id, limit=50)
    item = next(item for item in feed["items"] if item["type"] == "photo")

    assert isinstance(item["photo"]["photos"], list)
    assert len(item["photo"]["photos"]) == 1
    assert item["photo"]["author"]["handle"]
    assert item["photo"]["restaurant"]["id"]


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(photo_service, "engine", BrokenEngine())
    with pytest.raises(photo_service.PhotoStoreError):
        photo_service.get_photo(uuid4(), viewer_id=AUTHOR.id)


def test_the_endpoint_publishes_and_rejects_what_it_must(seeded_database):
    del seeded_database
    storage = MemoryStorage()
    app.dependency_overrides[get_current_session] = session
    app.dependency_overrides[get_media_storage] = lambda: storage
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={
                "restaurant_id": str(RESTAURANT),
                "kind": "dish",
                "dish_name": "Sopaipillas",
                "visibility": "public",
                "caption": "Con pebre",
            },
            files={"photo": ("dish.png", png_file().read(), "image/png")},
        )
        without_dish = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={"restaurant_id": str(RESTAURANT), "kind": "dish", "visibility": "public"},
            files={"photo": ("dish.png", png_file().read(), "image/png")},
        )
        menu_kind = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={
                "restaurant_id": str(RESTAURANT),
                "kind": "menu",
                "visibility": "public",
            },
            files={"photo": ("menu.png", png_file().read(), "image/png")},
        )
        menu_with_dish = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={
                "restaurant_id": str(RESTAURANT),
                "kind": "menu",
                "dish_name": "Sopaipillas",
                "visibility": "public",
            },
            files={"photo": ("menu.png", png_file().read(), "image/png")},
        )
        unknown_restaurant = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://testserver"},
            data={
                "restaurant_id": str(uuid4()),
                "kind": "dish",
                "dish_name": "Sopaipillas",
                "visibility": "public",
            },
            files={"photo": ("dish.png", png_file().read(), "image/png")},
        )
        untrusted = client.post(
            "/api/v1/photos",
            headers={"Origin": "http://evil.example"},
            data={
                "restaurant_id": str(RESTAURANT),
                "kind": "dish",
                "dish_name": "Sopaipillas",
                "visibility": "public",
            },
            files={"photo": ("dish.png", png_file().read(), "image/png")},
        )
        metadata_of = client.get(f"/api/v1/photos/{created.json()['id']}")
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.headers["location"] == f"/api/v1/photos/{created.json()['id']}"
    assert created.json()["dish_name"] == "Sopaipillas"
    assert created.json()["caption"] == "Con pebre"
    assert created.json()["review_id"] is None
    assert without_dish.status_code == 422
    # A menu no longer needs a dish, and must not carry one.
    assert menu_kind.status_code == 201
    assert menu_kind.json()["dish_name"] is None
    assert menu_with_dish.status_code == 422
    assert unknown_restaurant.status_code == 404
    assert untrusted.status_code == 403
    assert metadata_of.status_code == 200


def test_the_routes_require_a_session():
    client = TestClient(app)

    assert client.get(f"/api/v1/photos/{uuid4()}").status_code == 401
    assert client.get(f"/api/v1/photos/{uuid4()}/content").status_code == 401
    assert (
        client.post(
            "/api/v1/photos",
            data={"restaurant_id": str(RESTAURANT), "visibility": "public"},
            files={"photo": ("dish.png", png_file().read(), "image/png")},
        ).status_code
        == 401
    )


def test_the_review_contract_did_not_change(seeded_database):
    del seeded_database
    storage = MemoryStorage()

    review = review_service.create_review(
        author_id=AUTHOR.id,
        restaurant_id=RESTAURANT,
        dish_name="Charquicán",
        text="Muy casero",
        photo_stream=png_file(),
        declared_content_type="image/png",
        storage=storage,
    )

    assert review.dish_name == "Charquicán"
    assert review.visibility == "public"
    assert review.photo.dish_name == "Charquicán"
    assert review.photo.visibility == "public"
    assert review.created_at == review.photo.created_at


# --- Menus, premises and the act of publishing several ------------------------


def group_of(count, *, storage=None, author=AUTHOR, **overrides):
    """Publish `count` photographs as a single act, one request each."""
    storage = storage or MemoryStorage()
    upload_group = uuid4()
    arguments = {"kind": "menu", "dish_name": None, "author_id": author.id}
    arguments.update(overrides)
    return upload_group, [
        publish(storage=storage, upload_group=upload_group, **arguments) for _ in range(count)
    ]


def test_a_menu_and_a_venue_photograph_carry_no_dish(seeded_database):
    del seeded_database

    menu = publish(kind="menu", dish_name=None, visibility="public")
    venue = publish(kind="venue", dish_name=None, visibility="private")

    assert (menu.kind, menu.dish_name) == ("menu", None)
    assert (venue.kind, venue.dish_name, venue.visibility) == ("venue", None, "private")


def test_a_menu_or_venue_photograph_refuses_a_dish(seeded_database):
    del seeded_database

    for kind in ("menu", "venue"):
        with pytest.raises(photo_service.InvalidPhotoPublicationError):
            publish(kind=kind, dish_name="Sopaipillas")


def test_a_group_is_one_activity_in_the_feed_and_in_the_profile(seeded_database):
    del seeded_database
    upload_group, published = group_of(3, author=OTHER)

    feed = feed_service.get_feed(AUTHOR.id, limit=50)
    profile = user_service.get_activity(OTHER.handle, viewer_id=AUTHOR.id, limit=50)
    entries = [
        item
        for item in feed["items"]
        if item["type"] == "photo"
        and {photo["id"] for photo in item["photo"]["photos"]} & {p.id for p in published}
    ]

    assert len(entries) == 1
    assert {photo["id"] for photo in entries[0]["photo"]["photos"]} == {p.id for p in published}
    # And the same single entry in the profile of whoever published it.
    profile_entries = [
        item
        for item in profile["items"]
        if item["type"] == "photo"
        and {photo["id"] for photo in item["photo"]["photos"]} & {p.id for p in published}
    ]
    assert len(profile_entries) == 1
    del upload_group


def test_a_group_is_dated_by_its_first_photograph(seeded_database):
    del seeded_database
    _, published = group_of(2, author=OTHER)

    feed = feed_service.get_feed(AUTHOR.id, limit=50)
    entry = next(
        item
        for item in feed["items"]
        if item["type"] == "photo"
        and {photo["id"] for photo in item["photo"]["photos"]} & {p.id for p in published}
    )

    assert entry["published_at"] == min(photo.created_at for photo in published)


def test_a_group_refuses_a_photograph_that_does_not_belong_to_it(seeded_database):
    del seeded_database
    upload_group, _ = group_of(1, author=AUTHOR)

    for overrides in (
        {"author_id": OTHER.id},
        {"restaurant_id": RESTAURANTS[1].id},
        {"kind": "venue"},
        {"visibility": "private"},
        {"kind": "dish", "dish_name": "Sopaipillas"},
    ):
        arguments = {"kind": "menu", "dish_name": None, **overrides}
        with pytest.raises(photo_service.InvalidPhotoPublicationError):
            publish(upload_group=upload_group, **arguments)


def test_a_group_stops_at_its_maximum(seeded_database):
    del seeded_database
    upload_group, _ = group_of(photo_service.MAXIMUM_PHOTOS_PER_GROUP, author=AUTHOR)

    with pytest.raises(photo_service.InvalidPhotoPublicationError) as raised:
        publish(upload_group=upload_group, kind="menu", dish_name=None)

    assert "at most" in raised.value.reason


def test_a_rejected_photograph_of_a_group_leaves_no_object_behind(seeded_database):
    del seeded_database
    upload_group, _ = group_of(1, author=AUTHOR)
    storage = MemoryStorage()

    with pytest.raises(photo_service.InvalidPhotoPublicationError):
        publish(storage=storage, upload_group=upload_group, kind="venue", dish_name=None)

    assert storage.deleted == storage.stored


def test_a_private_group_is_all_or_nothing_for_a_third_party(seeded_database):
    del seeded_database
    _, published = group_of(2, author=AUTHOR, visibility="private")

    seen = feed_service.get_feed(OTHER.id, limit=50)
    own = user_service.get_activity(AUTHOR.handle, viewer_id=AUTHOR.id, limit=50)
    own_entry = next(
        item
        for item in own["items"]
        if item["type"] == "photo"
        and {photo["id"] for photo in item["photo"]["photos"]} & {p.id for p in published}
    )

    assert not any(
        {photo["id"] for photo in item["photo"]["photos"]} & {p.id for p in published}
        for item in seen["items"]
        if item["type"] == "photo"
    )
    assert len(own_entry["photo"]["photos"]) == 2


def test_the_gallery_filters_by_kind(seeded_database):
    del seeded_database

    def gallery(kind=None):
        return photo_service.list_restaurant_photos(
            RESTAURANT, viewer_id=AUTHOR.id, limit=50, kind=kind
        )

    every = gallery()
    dishes = gallery("dish")
    menus = gallery("menu")
    venues = gallery("venue")

    assert {photo.kind for photo in dishes.items} == {"dish"}
    assert {photo.kind for photo in menus.items} == {"menu"}
    assert {photo.kind for photo in venues.items} == {"venue"}
    assert len(every.items) == len(dishes.items) + len(menus.items) + len(venues.items)
    with pytest.raises(photo_service.UnknownPhotoKindError):
        gallery("mural")


def test_a_kind_without_photographs_is_not_an_error(seeded_database):
    del seeded_database
    quiet = RESTAURANTS[6].id

    page = photo_service.list_restaurant_photos(quiet, viewer_id=AUTHOR.id, limit=50, kind="menu")

    assert page.items == ()
    assert page.next_cursor is None


def test_the_endpoint_publishes_a_group_and_the_gallery_filters_it(seeded_database):
    del seeded_database
    storage = MemoryStorage()
    upload_group = str(uuid4())
    app.dependency_overrides[get_current_session] = session
    app.dependency_overrides[get_media_storage] = lambda: storage
    client = TestClient(app)
    try:
        responses = [
            client.post(
                "/api/v1/photos",
                headers={"Origin": "http://testserver"},
                data={
                    "restaurant_id": str(RESTAURANT),
                    "kind": "venue",
                    "visibility": "public",
                    "upload_group": upload_group,
                },
                files={"photo": (f"venue{index}.png", png_file().read(), "image/png")},
            )
            for index in range(2)
        ]
        filtered = client.get(f"/api/v1/restaurants/{RESTAURANT}/photos?kind=venue")
        unknown_kind = client.get(f"/api/v1/restaurants/{RESTAURANT}/photos?kind=mural")
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [201, 201]
    assert filtered.status_code == 200
    assert {photo["kind"] for photo in filtered.json()["items"]} == {"venue"}
    assert {response.json()["id"] for response in responses} <= {
        photo["id"] for photo in filtered.json()["items"]
    }
    assert unknown_kind.status_code == 422
    assert unknown_kind.json()["detail"][0]["loc"] == ["query", "kind"]
