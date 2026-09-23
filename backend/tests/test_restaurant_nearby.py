import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.schema import metadata
from app.services import restaurants as restaurant_service

# A point in the middle of the Santiago fixtures.
SANTIAGO = (-33.4372, -70.6506)


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


def nearby(radius, *, latitude=SANTIAGO[0], longitude=SANTIAGO[1], styles=(), limit=200):
    return restaurant_service.restaurants_nearby(
        latitude=latitude,
        longitude=longitude,
        radius_metres=radius,
        cuisine_style_slugs=styles,
        limit=limit,
    )


def place(name, latitude, longitude, styles=("chilena",)):
    return restaurant_service.create_restaurant(
        name=name,
        address=f"Dirección de {name}",
        latitude=latitude,
        longitude=longitude,
        cuisine_style_slugs=list(styles),
    )


# --- The circumscribing rectangle, without a database -------------------------


def test_the_rectangle_contains_the_circle_and_is_not_much_larger():
    bounds = restaurant_service.circumscribing_bounds(-33.4372, -70.6506, 5_000)

    assert bounds.south < -33.4372 < bounds.north
    assert bounds.west < -70.6506 < bounds.east
    # Five kilometres is about 0.045 degrees of latitude.
    assert 0.044 < (bounds.north - bounds.south) / 2 < 0.046
    # A degree of longitude is shorter away from the equator, so its half-width
    # has to be wider than the latitude one at this parallel.
    assert (bounds.east - bounds.west) > (bounds.north - bounds.south)


def test_a_circle_that_reaches_a_pole_has_no_meridian_bound():
    bounds = restaurant_service.circumscribing_bounds(89.99, 0.0, 50_000)

    assert bounds.west == -180.0
    assert bounds.east == 180.0
    assert bounds.north <= 90.0

    southern = restaurant_service.circumscribing_bounds(-89.99, 0.0, 50_000)
    assert (southern.west, southern.east) == (-180.0, 180.0)
    assert southern.south >= -90.0


def test_a_circle_near_the_antimeridian_wraps_into_two_ranges():
    bounds = restaurant_service.circumscribing_bounds(0.0, 179.99, 5_000)

    # The west edge ends up east of the east edge, which is how the bounds
    # condition recognises the crossing.
    assert bounds.west > bounds.east
    assert bounds.west <= 180.0
    assert bounds.east >= -180.0


def test_the_distance_matches_a_known_pair():
    # Santiago to Valparaíso is about 100 km in a straight line.
    metres = restaurant_service.haversine_metres(-33.4372, -70.6506, -33.0450, -71.6190)

    assert 95_000 < metres < 105_000
    assert restaurant_service.haversine_metres(-33.4372, -70.6506, -33.4372, -70.6506) == 0


# --- The query ---------------------------------------------------------------


def test_results_come_ordered_by_distance_with_the_measured_metres(seeded_database):
    del seeded_database

    result = nearby(50_000)
    distances = [restaurant.distance_m for restaurant in result.items]

    assert distances == sorted(distances)
    assert all(isinstance(distance, int) for distance in distances)
    nearest = result.items[0]
    assert nearest.distance_m == round(
        restaurant_service.haversine_metres(
            *SANTIAGO, float(nearest.latitude), float(nearest.longitude)
        )
    )


def test_a_restaurant_just_inside_and_just_outside_the_radius(seeded_database):
    del seeded_database
    # About 1.1 km north of the centre used by these tests.
    inside = place("A mil metros", SANTIAGO[0] + 0.009, SANTIAGO[1])

    found = {restaurant.id for restaurant in nearby(1_500).items}
    not_found = {restaurant.id for restaurant in nearby(500).items}

    assert inside.id in found
    assert inside.id not in not_found


def test_the_style_filter_is_optional_and_admits_several(seeded_database):
    del seeded_database

    everything = nearby(50_000)
    chilean = nearby(50_000, styles=["chilena"])
    two_styles = nearby(50_000, styles=["chilena", "japonesa"])

    assert len(everything.items) >= len(two_styles.items) > len(chilean.items)
    assert {restaurant.id for restaurant in chilean.items} < {
        restaurant.id for restaurant in two_styles.items
    }
    assert all(
        any(style.slug == "chilena" for style in restaurant.cuisine_styles)
        for restaurant in chilean.items
    )


def test_a_style_with_nothing_nearby_is_not_an_error(seeded_database):
    del seeded_database

    result = nearby(1_000, latitude=-10.0, longitude=-65.0, styles=["japonesa"])

    assert result.items == ()
    assert not result.truncated


def test_an_unknown_style_is_told_apart_from_an_empty_circle(seeded_database):
    del seeded_database

    with pytest.raises(restaurant_service.UnknownCuisineStylesError):
        nearby(5_000, styles=["marciana"])


def test_the_same_style_is_found_in_two_cities(seeded_database):
    del seeded_database

    from_santiago = nearby(50_000, styles=["chilena"])
    from_valparaiso = nearby(50_000, latitude=-33.0450, longitude=-71.6190, styles=["chilena"])

    assert from_santiago.items and from_valparaiso.items
    assert {restaurant.id for restaurant in from_santiago.items} != {
        restaurant.id for restaurant in from_valparaiso.items
    }


def test_a_circle_around_the_antimeridian_finds_both_sides(seeded_database):
    del seeded_database
    east_of_the_line = place("Al este de la línea", 0.0, 179.99)
    west_of_the_line = place("Al oeste de la línea", 0.0, -179.99)

    result = nearby(5_000, latitude=0.0, longitude=180.0)

    assert {restaurant.id for restaurant in result.items} == {
        east_of_the_line.id,
        west_of_the_line.id,
    }


def test_a_circle_over_a_pole_finds_what_is_around_it(seeded_database):
    del seeded_database
    near_the_pole = place("Casi en el polo", 89.995, 120.0)

    result = nearby(50_000, latitude=90.0, longitude=0.0)

    assert near_the_pole.id in {restaurant.id for restaurant in result.items}


def test_invalid_centres_and_radii_are_rejected_by_the_service(seeded_database):
    del seeded_database

    for arguments in (
        {"radius": 0},
        {"radius": -100},
        {"radius": restaurant_service.MAXIMUM_NEARBY_RADIUS_METRES + 1},
        {"radius": 1_000, "latitude": -91.0},
        {"radius": 1_000, "longitude": 181.0},
    ):
        with pytest.raises(restaurant_service.InvalidNearbySearchError):
            nearby(**arguments)


def test_truncated_says_the_circle_held_more_than_was_returned(seeded_database):
    del seeded_database
    inside = len(nearby(50_000).items)

    exact = nearby(50_000, limit=inside)
    short = nearby(50_000, limit=inside - 1)

    assert len(exact.items) == inside
    assert not exact.truncated
    assert len(short.items) == inside - 1
    assert short.truncated
    # Truncation keeps the nearest ones, which is the point of the order.
    assert short.items == exact.items[: inside - 1]


def test_store_failure_is_reported_as_such(seeded_database, monkeypatch):
    del seeded_database

    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(restaurant_service, "engine", BrokenEngine())
    with pytest.raises(restaurant_service.RestaurantStoreError):
        nearby(5_000)
