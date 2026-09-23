import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.fixtures import CUISINE_STYLES, RESTAURANTS
from app.db.schema import metadata
from app.services import restaurants as restaurant_service
from app.services.cursors import InvalidCursorError


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
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed(storage=FixtureStorage())
    return database


def names(page):
    return [restaurant.name for restaurant in page.items]


def search(term, **kwargs):
    return restaurant_service.list_restaurants(query=term, limit=kwargs.pop("limit", 50), **kwargs)


def test_search_form_folds_diacritics_and_case_but_the_duplicate_form_does_not():
    assert restaurant_service.normalize_restaurant_search_text("Café Perú") == "cafe peru"
    assert restaurant_service.normalize_restaurant_search_text("  CAFE   PERU ") == "cafe peru"
    assert restaurant_service.normalize_restaurant_text("Café Perú") == "café perú"
    assert restaurant_service.normalize_restaurant_text(
        "Café Perú"
    ) != restaurant_service.normalize_restaurant_text("Cafe Peru")


def test_search_matches_a_prefix_and_a_term_inside_the_name(seeded_database):
    del seeded_database

    assert names(search("cocina")) == ["Cocina Andina", "Cocina del Barrio"]
    assert names(search("barrio")) == ["Cocina del Barrio"]
    assert names(search("no existe nada asi")) == []


def test_search_ignores_case_and_diacritics_in_both_directions(seeded_database):
    del seeded_database
    accented = "Café Ñielol"

    assert names(search("cafe")) == [accented]
    assert names(search("CAFÉ")) == [accented]
    assert names(search("ñielol")) == [accented]
    assert names(search("nielol")) == [accented]


def test_search_rejects_a_term_that_would_return_everything(seeded_database):
    del seeded_database

    for term in ("c", "", "   ", "é"):
        with pytest.raises(restaurant_service.SearchTermTooShortError):
            search(term)


def test_wildcards_typed_by_the_user_are_not_wildcards(seeded_database):
    del seeded_database

    assert names(search("%%")) == []
    assert names(search("__")) == []


def test_collection_pages_by_cursor_without_repeating_or_skipping(seeded_database):
    del seeded_database
    every_name = names(restaurant_service.list_restaurants(query=None, limit=100))
    assert len(every_name) == len(RESTAURANTS)
    assert every_name == sorted(every_name, key=restaurant_service.normalize_restaurant_search_text)

    seen = []
    cursor = None
    while True:
        page = restaurant_service.list_restaurants(query=None, limit=3, cursor=cursor)
        seen.extend(names(page))
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == every_name
    assert len(seen) == len(set(seen))


def test_search_pages_by_cursor_too(seeded_database):
    del seeded_database

    first = search("cocina", limit=1)
    assert names(first) == ["Cocina Andina"]
    assert first.next_cursor is not None

    second = search("cocina", limit=1, cursor=first.next_cursor)
    assert names(second) == ["Cocina del Barrio"]
    assert second.next_cursor is None


def test_a_cursor_this_api_did_not_issue_is_rejected(seeded_database):
    del seeded_database

    with pytest.raises(InvalidCursorError):
        restaurant_service.list_restaurants(query=None, limit=5, cursor="no-es-un-cursor")


def test_duplicate_creation_reports_the_restaurant_that_already_exists(seeded_database):
    del seeded_database
    existing = RESTAURANTS[0]

    with pytest.raises(restaurant_service.DuplicateRestaurantError) as raised:
        restaurant_service.create_restaurant(
            name=existing.name.upper(),
            address=existing.address,
            latitude=float(existing.latitude),
            longitude=float(existing.longitude),
            cuisine_style_slugs=["chilena"],
        )

    assert raised.value.existing is not None
    assert raised.value.existing.id == existing.id
    assert raised.value.existing.name == existing.name


def test_a_name_that_differs_only_in_accents_is_another_restaurant(seeded_database):
    del seeded_database
    accented = restaurant_service.create_restaurant(
        name="Café Perú",
        address="Bandera 200, Santiago",
        latitude=-33.44,
        longitude=-70.65,
        cuisine_style_slugs=["peruana"],
    )
    plain = restaurant_service.create_restaurant(
        name="Cafe Peru",
        address="Bandera 200, Santiago",
        latitude=-33.44,
        longitude=-70.65,
        cuisine_style_slugs=["peruana"],
    )

    assert accented.id != plain.id
    # Search brings them together even though duplicate detection kept them apart.
    assert {restaurant.id for restaurant in search("cafe peru").items} == {accented.id, plain.id}


def test_cuisine_style_catalogue_matches_the_slugs_creation_accepts(seeded_database):
    del seeded_database
    catalogue = restaurant_service.list_cuisine_styles()

    assert {style.slug for style in catalogue} == {style.slug for style in CUISINE_STYLES}
    created = restaurant_service.create_restaurant(
        name="Con estilos del catálogo",
        address="Moneda 1000, Santiago",
        latitude=-33.44,
        longitude=-70.65,
        cuisine_style_slugs=[catalogue[0].slug],
    )
    assert created.cuisine_styles[0].slug == catalogue[0].slug


def test_store_failures_are_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        restaurant_service.list_restaurants(query=None, limit=5)
    with pytest.raises(restaurant_service.RestaurantStoreError):
        restaurant_service.list_cuisine_styles()
