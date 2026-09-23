import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.fixtures import RESTAURANTS
from app.db.schema import metadata
from app.services import restaurants as restaurant_service

# The seed puts twelve restaurants in Santiago and four around Valparaíso.
SANTIAGO = {"south": -33.50, "west": -70.70, "north": -33.40, "east": -70.55}
VALPARAISO = {"south": -33.10, "west": -71.70, "north": -33.00, "east": -71.50}
BOTH_CITIES = {"south": -33.50, "west": -71.70, "north": -33.00, "east": -70.55}
PACIFIC = {"south": -10.0, "west": -70.0, "north": -5.0, "east": -65.0}


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


def names(result):
    return {restaurant.name for restaurant in result.items}


def in_bounds(limit=restaurant_service.MAXIMUM_MAP_RESULTS, **bounds):
    return restaurant_service.restaurants_in_bounds(limit=limit, **bounds)


def place(name, latitude, longitude):
    return restaurant_service.create_restaurant(
        name=name,
        address=f"Dirección de {name}",
        latitude=latitude,
        longitude=longitude,
        cuisine_style_slugs=["chilena"],
    )


def test_a_rectangle_separates_one_city_from_the_other(seeded_database):
    del seeded_database

    santiago = in_bounds(**SANTIAGO)
    valparaiso = in_bounds(**VALPARAISO)

    assert "Cocina del Barrio" in names(santiago)
    assert "Ancla y Sal" in names(valparaiso)
    assert names(santiago) & names(valparaiso) == set()
    assert not santiago.truncated
    assert not valparaiso.truncated


def test_a_rectangle_over_both_cities_holds_the_whole_catalogue(seeded_database):
    del seeded_database

    result = in_bounds(**BOTH_CITIES)

    assert len(result.items) == len(RESTAURANTS)
    assert not result.truncated


def test_a_valid_rectangle_with_nothing_inside_is_not_an_error(seeded_database):
    del seeded_database

    result = in_bounds(**PACIFIC)

    assert result.items == ()
    assert not result.truncated


def test_a_restaurant_exactly_on_the_border_is_inside(seeded_database):
    del seeded_database
    corner = place("Justo en la esquina", -33.200000, -71.000000)

    included = in_bounds(south=-33.2, west=-71.0, north=-33.1, east=-70.9)
    excluded = in_bounds(south=-33.1999, west=-71.0, north=-33.1, east=-70.9)

    assert corner.id in {restaurant.id for restaurant in included.items}
    assert corner.id not in {restaurant.id for restaurant in excluded.items}


def test_a_rectangle_that_crosses_the_antimeridian_is_two_ranges(seeded_database):
    del seeded_database
    east_of_the_line = place("Al este de la línea", 0.0, 179.5)
    west_of_the_line = place("Al oeste de la línea", 0.0, -179.5)

    crossing = in_bounds(south=-1.0, west=179.0, north=1.0, east=-179.0)

    assert {restaurant.id for restaurant in crossing.items} == {
        east_of_the_line.id,
        west_of_the_line.id,
    }


def test_a_rectangle_read_the_other_way_round_covers_the_rest_of_the_world(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.InvalidMapBoundsError):
        in_bounds(south=-1.0, west=-179.0, north=1.0, east=179.0)


def test_malformed_rectangles_are_rejected_by_the_service(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.InvalidMapBoundsError):
        in_bounds(south=-33.0, west=-71.0, north=-33.5, east=-70.0)
    with pytest.raises(restaurant_service.InvalidMapBoundsError):
        in_bounds(south=-91.0, west=-71.0, north=-33.0, east=-70.0)
    with pytest.raises(restaurant_service.InvalidMapBoundsError):
        in_bounds(south=-33.5, west=-181.0, north=-33.0, east=-70.0)


def test_an_area_over_the_maximum_asks_to_zoom_in(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.InvalidMapBoundsError) as raised:
        in_bounds(south=-40.0, west=-80.0, north=-10.0, east=-60.0)

    assert "zoom in" in raised.value.reason

    # Just under the maximum is answered.
    assert in_bounds(south=-10.0, west=-10.0, north=0.0, east=0.0).items == ()


def test_truncated_says_the_rectangle_held_more_than_was_returned(seeded_database):
    del seeded_database
    inside = len(in_bounds(**SANTIAGO).items)

    exact = in_bounds(limit=inside, **SANTIAGO)
    short = in_bounds(limit=inside - 1, **SANTIAGO)

    assert len(exact.items) == inside
    assert not exact.truncated
    assert len(short.items) == inside - 1
    assert short.truncated


def test_a_restaurant_created_by_a_user_appears_on_the_map(seeded_database):
    del seeded_database
    created = place("Recién aportado", -33.45, -70.65)

    assert created.id in {restaurant.id for restaurant in in_bounds(**SANTIAGO).items}


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        in_bounds(**SANTIAGO)
