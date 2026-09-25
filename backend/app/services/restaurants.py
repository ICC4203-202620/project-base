from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from typing import Any, cast
from unicodedata import combining, normalize
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.retry import run_transaction_with_retry
from app.db.schema import (
    cuisine_styles,
    photos,
    restaurant_cuisine_styles,
    restaurant_follows,
    restaurants,
    reviews,
    visits,
)
from app.db.session import engine
from app.services.cursors import decode_cursor, encode_cursor
from app.services.visibility import PUBLIC, visible_to

MINIMUM_SEARCH_LENGTH = 2
LIKE_ESCAPE = "\\"

# A map view of a city spans fractions of a degree. A hundred square degrees is
# roughly a thousand kilometres on a side at these latitudes: far more than any
# reasonable view, and small enough to reject someone who zoomed out to a
# continent. The measure is deliberately crude, in square degrees: it is a
# guard, not a measurement of surface.
MAXIMUM_MAP_AREA_SQUARE_DEGREES = 100.0
# Shared with the nearby search, so the same map does not behave in two ways
# depending on whether a style filter is active.
MAXIMUM_MAP_RESULTS = 200

# Mean Earth radius (IUGG), in metres. Distances here are spherical: the error
# against the ellipsoid is a few parts in a thousand over the radii this
# endpoint admits, and irrelevant next to the accuracy of a position reported
# by a browser.
EARTH_RADIUS_METRES = 6_371_008.8
# Fifty kilometres. A "nearby" search of a thousand kilometres is not a nearby
# search: it is the whole collection, which already has its own endpoint.
MAXIMUM_NEARBY_RADIUS_METRES = 50_000


class RestaurantNotFoundError(Exception):
    """The requested restaurant does not exist."""


class DuplicateRestaurantError(Exception):
    """A restaurant already uses the normalized name and address.

    It carries the existing row when it is known. The statement asks that what
    different people contribute end up on a single page, and for that the
    interface has to be able to take the person to the page that already
    exists instead of leaving them on an error.
    """

    def __init__(self, existing: "Restaurant | None" = None):
        self.existing = existing
        super().__init__(str(existing.id) if existing else "")


class SearchTermTooShortError(Exception):
    """A one-character term would return the whole collection."""


class InvalidMapBoundsError(Exception):
    """The rectangle is malformed, out of range or too large to answer."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class InvalidNearbySearchError(Exception):
    """The centre or the radius of the circle cannot be answered."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class UnknownCuisineStylesError(Exception):
    """One or more cuisine slugs do not exist."""

    def __init__(self, slugs: Sequence[str]):
        self.slugs = tuple(sorted(slugs))
        super().__init__(", ".join(self.slugs))


class RestaurantStoreError(Exception):
    """The restaurant store could not complete an operation."""


@dataclass(frozen=True)
class CuisineStyle:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True)
class RestaurantPage:
    items: tuple["Restaurant", ...]
    next_cursor: str | None


@dataclass(frozen=True)
class NearbyRestaurant:
    """A restaurant with the distance the server measured to it.

    The statement asks for a list ordered by distance. Letting the client
    recompute it invites showing a number different from the one the server
    ordered by.
    """

    id: UUID
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    cuisine_styles: tuple["CuisineStyle", ...]
    distance_m: int

    @classmethod
    def of(cls, restaurant: "Restaurant", distance_m: int) -> "NearbyRestaurant":
        return cls(
            id=restaurant.id,
            name=restaurant.name,
            address=restaurant.address,
            latitude=restaurant.latitude,
            longitude=restaurant.longitude,
            cuisine_styles=restaurant.cuisine_styles,
            distance_m=distance_m,
        )


@dataclass(frozen=True)
class RestaurantNearbyResult:
    items: tuple[NearbyRestaurant, ...]
    truncated: bool


@dataclass(frozen=True)
class CriterionAverage:
    criterion: str
    average: float


@dataclass(frozen=True)
class RatingSummary:
    """What the page shows about the evaluations a restaurant received.

    Declared now and filled by épica 11. Fixing the shape once means the
    client that reads it today keeps working when the numbers arrive.
    """

    criteria: tuple[CriterionAverage, ...]
    average: float | None
    total: int


@dataclass(frozen=True)
class RestaurantCounters:
    """What the viewer can see, not what exists.

    A counter that included someone else's private activity would announce its
    existence without showing it.
    """

    photos: int
    reviews: int
    evaluations: int
    visits: int
    followers: int


@dataclass(frozen=True)
class RestaurantViewerRelationship:
    following: bool


@dataclass(frozen=True)
class RestaurantDetail:
    id: UUID
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    cuisine_styles: tuple[CuisineStyle, ...]
    created_at: datetime
    updated_at: datetime
    counters: RestaurantCounters
    ratings: RatingSummary
    viewer: RestaurantViewerRelationship


@dataclass(frozen=True)
class MapBounds:
    south: float
    west: float
    north: float
    east: float


@dataclass(frozen=True)
class RestaurantMapResult:
    """What fits inside a rectangle, and whether something did not.

    A rectangle is a map query and not a list to walk, so it is not paged: if
    the answer does not fit, the answer is to zoom in. `truncated` is what
    lets the interface say so instead of drawing an incomplete map as if it
    were complete.
    """

    items: tuple["Restaurant", ...]
    truncated: bool


@dataclass(frozen=True)
class Restaurant:
    id: UUID
    name: str
    address: str
    latitude: Decimal
    longitude: Decimal
    cuisine_styles: tuple[CuisineStyle, ...]
    created_at: datetime
    updated_at: datetime


def normalize_restaurant_text(value: str) -> str:
    """Return the stable comparison form used by the duplicate constraint.

    It keeps diacritics, so «Café Perú» and «Cafe Peru» remain two different
    names that two different people may have contributed.
    """
    return " ".join(normalize("NFKC", value).split()).casefold()


def normalize_restaurant_search_text(value: str) -> str:
    """Return the comparison form used by search, without diacritics.

    Someone typing «cafe» expects to find «Café». This is deliberately not the
    form above: search brings both together, duplicate detection keeps them
    apart.
    """
    decomposed = normalize("NFKD", value)
    without_marks = "".join(character for character in decomposed if not combining(character))
    return " ".join(normalize("NFKC", without_marks).split()).casefold()


def _contains_pattern(term: str) -> str:
    """Escape what LIKE would otherwise read as a wildcard."""
    escaped = term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", f"{LIKE_ESCAPE}%")
    return f"%{escaped.replace('_', f'{LIKE_ESCAPE}_')}%"


def restaurant_identity_key(name: str, address: str) -> str:
    normalized_identity = f"{normalize_restaurant_text(name)}\0{normalize_restaurant_text(address)}"
    return sha256(normalized_identity.encode()).hexdigest()


def _load_cuisine_styles(
    connection: Connection, restaurant_ids: Sequence[UUID]
) -> dict[UUID, tuple[CuisineStyle, ...]]:
    grouped: dict[UUID, list[CuisineStyle]] = {
        restaurant_id: [] for restaurant_id in restaurant_ids
    }
    if not restaurant_ids:
        return {}

    rows = connection.execute(
        select(
            restaurant_cuisine_styles.c.restaurant_id,
            cuisine_styles.c.id,
            cuisine_styles.c.slug,
            cuisine_styles.c.name,
        )
        .select_from(
            restaurant_cuisine_styles.join(
                cuisine_styles,
                restaurant_cuisine_styles.c.cuisine_style_id == cuisine_styles.c.id,
            )
        )
        .where(restaurant_cuisine_styles.c.restaurant_id.in_(restaurant_ids))
        .order_by(restaurant_cuisine_styles.c.restaurant_id, cuisine_styles.c.slug)
    ).mappings()

    for row in rows:
        grouped[row["restaurant_id"]].append(
            CuisineStyle(id=row["id"], slug=row["slug"], name=row["name"])
        )
    return {restaurant_id: tuple(styles) for restaurant_id, styles in grouped.items()}


def _to_restaurants(connection: Connection, rows: Sequence[Mapping[str, Any]]) -> list[Restaurant]:
    restaurant_ids = [row["id"] for row in rows]
    styles_by_restaurant = _load_cuisine_styles(connection, restaurant_ids)
    return [
        Restaurant(
            id=row["id"],
            name=row["name"],
            address=row["address"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            cuisine_styles=styles_by_restaurant[row["id"]],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _get_restaurant(connection: Connection, restaurant_id: UUID) -> Restaurant:
    row = (
        connection.execute(select(restaurants).where(restaurants.c.id == restaurant_id))
        .mappings()
        .first()
    )
    if not row:
        raise RestaurantNotFoundError
    return _to_restaurants(connection, [row])[0]


def _resolve_cuisine_style_ids(connection: Connection, slugs: Sequence[str]) -> list[UUID]:
    rows = connection.execute(
        select(cuisine_styles.c.id, cuisine_styles.c.slug).where(cuisine_styles.c.slug.in_(slugs))
    ).mappings()
    ids_by_slug = {row["slug"]: row["id"] for row in rows}
    missing = set(slugs) - ids_by_slug.keys()
    if missing:
        raise UnknownCuisineStylesError(missing)
    return [ids_by_slug[slug] for slug in slugs]


def follow_restaurant(*, user_id: UUID, restaurant_id: UUID) -> None:
    """Start following a restaurant, with the shape épica 13 fixed for people."""

    def persist(connection: Connection) -> None:
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        already = connection.scalar(
            select(restaurant_follows.c.user_id).where(
                restaurant_follows.c.user_id == user_id,
                restaurant_follows.c.restaurant_id == restaurant_id,
            )
        )
        if already:
            return
        connection.execute(
            insert(restaurant_follows).values(user_id=user_id, restaurant_id=restaurant_id)
        )

    try:
        run_transaction_with_retry(engine, persist)
    except RestaurantNotFoundError:
        raise
    except IntegrityError:
        # Two simultaneous requests: the state asked for is the one written.
        return
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def unfollow_restaurant(*, user_id: UUID, restaurant_id: UUID) -> None:
    """Stop following it, whether or not one was following it."""

    def persist(connection: Connection) -> None:
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        connection.execute(
            delete(restaurant_follows).where(
                restaurant_follows.c.user_id == user_id,
                restaurant_follows.c.restaurant_id == restaurant_id,
            )
        )

    try:
        run_transaction_with_retry(engine, persist)
    except RestaurantNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def _find_by_identity_key(identity_key: str) -> Restaurant | None:
    """Recover the row that won a concurrent creation, best effort.

    The unique index reports a collision without saying against what, and the
    interface needs the existing restaurant to send the person to it.
    """
    try:
        with engine.connect() as connection:
            existing_id = connection.scalar(
                select(restaurants.c.id).where(restaurants.c.identity_key == identity_key)
            )
            return _get_restaurant(connection, existing_id) if existing_id else None
    except (RestaurantNotFoundError, SQLAlchemyError):
        return None


def _is_unique_violation(error: IntegrityError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
    return sqlstate == "23505"


def list_cuisine_styles() -> list[CuisineStyle]:
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(cuisine_styles).order_by(cuisine_styles.c.name, cuisine_styles.c.slug)
            ).mappings()
            return [CuisineStyle(id=row["id"], slug=row["slug"], name=row["name"]) for row in rows]
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def _map_bounds_condition(south: float, west: float, north: float, east: float):
    """Translate a rectangle into comparisons the coordinate index can serve.

    A rectangle whose west edge lies east of its east edge crosses the
    antimeridian, and its longitudes are two ranges rather than one. It is a
    rare case in Chile and a source of inexplicably empty results where it is
    not.
    """
    latitude_within = and_(
        restaurants.c.latitude >= south,
        restaurants.c.latitude <= north,
    )
    if west <= east:
        longitude_within = and_(
            restaurants.c.longitude >= west,
            restaurants.c.longitude <= east,
        )
    else:
        longitude_within = or_(
            restaurants.c.longitude >= west,
            restaurants.c.longitude <= east,
        )
    return and_(latitude_within, longitude_within)


def _validate_map_bounds(south: float, west: float, north: float, east: float) -> None:
    """Reject a rectangle here and not only in the schema.

    The rule is part of the use case, and a service that only holds it when
    HTTP validated first is a rule nobody can test without a request.
    """
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise InvalidMapBoundsError("latitude must be between -90 and 90 degrees")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise InvalidMapBoundsError("longitude must be between -180 and 180 degrees")
    if south > north:
        raise InvalidMapBoundsError("south must not be north of north")

    longitude_span = east - west if west <= east else (180 - west) + (east + 180)
    if (north - south) * longitude_span > MAXIMUM_MAP_AREA_SQUARE_DEGREES:
        raise InvalidMapBoundsError(
            "the rectangle covers more than "
            f"{MAXIMUM_MAP_AREA_SQUARE_DEGREES:g} square degrees; zoom in"
        )


def restaurants_in_bounds(
    *,
    south: float,
    west: float,
    north: float,
    east: float,
    limit: int,
) -> RestaurantMapResult:
    """Answer what restaurants a map rectangle contains.

    Ordered by coordinate, which is the order the index already produces. A
    truncated answer is therefore the southernmost part of the rectangle and
    not a representative sample, which is exactly why it is announced: the
    interface has to ask for a closer view rather than draw it.
    """
    _validate_map_bounds(south, west, north, east)
    statement = (
        select(restaurants)
        .where(_map_bounds_condition(south, west, north, east))
        .order_by(restaurants.c.latitude, restaurants.c.longitude, restaurants.c.id)
        .limit(limit + 1)
    )

    try:
        with engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
            truncated = len(rows) > limit
            items = _to_restaurants(connection, rows[:limit])
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error

    return RestaurantMapResult(items=tuple(items), truncated=truncated)


def haversine_metres(
    latitude: float,
    longitude: float,
    other_latitude: float,
    other_longitude: float,
) -> float:
    """Great-circle distance over a sphere of EARTH_RADIUS_METRES.

    Written with atan2 rather than asin: the asin form loses precision for
    nearly antipodal points, and this one costs the same.
    """
    latitude_difference = radians(other_latitude - latitude)
    longitude_difference = radians(other_longitude - longitude)
    chord = (
        sin(latitude_difference / 2) ** 2
        + cos(radians(latitude)) * cos(radians(other_latitude)) * sin(longitude_difference / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * atan2(sqrt(chord), sqrt(1 - chord))


def circumscribing_bounds(latitude: float, longitude: float, radius_metres: float) -> MapBounds:
    """The smallest rectangle that contains a circle, in degrees.

    It exists so the coordinate index can narrow the scan before any distance
    is computed. Two edges need care and are the reason this is a function of
    its own, testable without a database:

    - a circle that reaches a pole has no meridian bound at all, so the whole
      longitude range is returned; and
    - a circle near the antimeridian yields a west edge east of its east edge,
      which the bounds condition reads as two ranges.

    The rectangle is a superset of the circle, so the exact distance filter
    still has the last word.
    """
    angular_radius = radius_metres / EARTH_RADIUS_METRES
    latitude_delta = degrees(angular_radius)
    south = latitude - latitude_delta
    north = latitude + latitude_delta

    if south <= -90 or north >= 90:
        return MapBounds(south=max(south, -90.0), west=-180.0, north=min(north, 90.0), east=180.0)

    parallel_radius = cos(radians(latitude))
    sine_ratio = sin(angular_radius) / parallel_radius
    if sine_ratio >= 1:
        return MapBounds(south=south, west=-180.0, north=north, east=180.0)

    longitude_delta = degrees(asin(sine_ratio))
    west = longitude - longitude_delta
    east = longitude + longitude_delta
    if west < -180 or east > 180:
        # The circle crosses the antimeridian: both edges are wrapped and the
        # west edge ends up east of the east edge, which is how the bounds
        # condition recognises the case.
        return MapBounds(
            south=south,
            west=(west + 360) if west < -180 else west,
            north=north,
            east=(east - 360) if east > 180 else east,
        )
    return MapBounds(south=south, west=west, north=north, east=east)


def _validate_nearby_search(latitude: float, longitude: float, radius_metres: float) -> None:
    if not -90 <= latitude <= 90:
        raise InvalidNearbySearchError("latitude must be between -90 and 90 degrees")
    if not -180 <= longitude <= 180:
        raise InvalidNearbySearchError("longitude must be between -180 and 180 degrees")
    if radius_metres <= 0:
        raise InvalidNearbySearchError("radius must be greater than zero")
    if radius_metres > MAXIMUM_NEARBY_RADIUS_METRES:
        raise InvalidNearbySearchError(
            f"radius must not exceed {MAXIMUM_NEARBY_RADIUS_METRES:g} metres"
        )


def restaurants_nearby(
    *,
    latitude: float,
    longitude: float,
    radius_metres: float,
    cuisine_style_slugs: Sequence[str] = (),
    limit: int,
) -> RestaurantNearbyResult:
    """Answer what is within a radius, optionally of certain cuisine styles.

    The rectangle that circumscribes the circle narrows the scan through the
    coordinate index; the exact distance is then measured over those
    candidates, which is what decides membership and order. The distance is
    computed here and not in SQL so the query stays plain comparisons that
    PostgreSQL, Aurora DSQL and SQLite all serve the same way, without
    depending on trigonometric functions whose availability differs between
    engines. The maximum radius is what bounds how many candidates that costs.
    """
    _validate_nearby_search(latitude, longitude, radius_metres)
    bounds = circumscribing_bounds(latitude, longitude, radius_metres)
    statement = select(restaurants).where(
        _map_bounds_condition(bounds.south, bounds.west, bounds.north, bounds.east)
    )

    try:
        with engine.connect() as connection:
            if cuisine_style_slugs:
                # Resolved before querying, so an unknown slug is told apart
                # from a circle that simply has nothing in it.
                style_ids = _resolve_cuisine_style_ids(connection, cuisine_style_slugs)
                statement = statement.where(
                    restaurants.c.id.in_(
                        select(restaurant_cuisine_styles.c.restaurant_id).where(
                            restaurant_cuisine_styles.c.cuisine_style_id.in_(style_ids)
                        )
                    )
                )
            rows = connection.execute(statement).mappings().all()
            candidates = _to_restaurants(connection, rows)
    except UnknownCuisineStylesError:
        raise
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error

    within_radius = []
    for restaurant in candidates:
        distance = haversine_metres(
            latitude,
            longitude,
            float(restaurant.latitude),
            float(restaurant.longitude),
        )
        if distance <= radius_metres:
            within_radius.append(NearbyRestaurant.of(restaurant, round(distance)))

    # Distance first, identifier to break ties, so the order is total and the
    # same query always truncates at the same place.
    within_radius.sort(key=lambda nearby: (nearby.distance_m, str(nearby.id)))
    return RestaurantNearbyResult(
        items=tuple(within_radius[:limit]),
        truncated=len(within_radius) > limit,
    )


def list_restaurants(*, query: str | None, limit: int, cursor: str | None = None) -> RestaurantPage:
    """Page the collection, optionally narrowed by a term in the name.

    The order is alphabetical on the search form and not by relevance: a
    cursor has to resume from a stable position, and a ranking that depends on
    the term would move rows between pages.
    """
    statement = select(restaurants)
    if query is not None:
        term = normalize_restaurant_search_text(query)
        if len(term) < MINIMUM_SEARCH_LENGTH:
            raise SearchTermTooShortError
        statement = statement.where(
            restaurants.c.search_name.like(_contains_pattern(term), escape=LIKE_ESCAPE)
        )
    if cursor:
        search_name, restaurant_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                restaurants.c.search_name > search_name,
                and_(
                    restaurants.c.search_name == search_name,
                    restaurants.c.id > restaurant_id,
                ),
            )
        )

    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    statement.order_by(restaurants.c.search_name, restaurants.c.id).limit(limit + 1)
                )
                .mappings()
                .all()
            )
            has_next = len(rows) > limit
            rows = rows[:limit]
            items = _to_restaurants(connection, rows)
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error

    return RestaurantPage(
        items=tuple(items),
        next_cursor=(encode_cursor(rows[-1]["search_name"], rows[-1]["id"]) if has_next else None),
    )


def _evaluation_summary(connection: Connection, restaurant_id: UUID) -> RatingSummary:
    """The averages of the restaurant, filled by the evaluation service.

    It was identified as a single point from #39 precisely so that only this
    function would change when evaluations arrived, and neither the router nor
    the shape of the response did.
    """
    from app.services.evaluations import restaurant_rating_summary

    summary = restaurant_rating_summary(connection, restaurant_id)
    return RatingSummary(
        criteria=tuple(
            CriterionAverage(criterion=criterion, average=average)
            for criterion, average in summary["criteria"]
        ),
        average=summary["average"],
        total=summary["total"],
    )


def _restaurant_counters_statement(restaurant_id: UUID, viewer_id: UUID):
    # Correlated subqueries in a single round trip, rather than one query per
    # counter. The visibility rule is applied inside each count, so a counter
    # never promises rows the corresponding list would not produce.
    visible_photos = (
        select(func.count())
        .select_from(photos)
        .where(
            photos.c.restaurant_id == restaurant_id,
            # Not imported from the photo service: that one depends on this
            # module, and the rule itself lives where visibility does.
            visible_to(photos.c.visibility, photos.c.author_id, viewer_id),
        )
        .scalar_subquery()
    )
    visible_reviews = (
        select(func.count())
        .select_from(reviews)
        .where(
            reviews.c.restaurant_id == restaurant_id,
            or_(reviews.c.visibility == PUBLIC, reviews.c.author_id == viewer_id),
        )
        .scalar_subquery()
    )
    visible_visits = (
        select(func.count())
        .select_from(visits)
        .where(
            visits.c.restaurant_id == restaurant_id,
            or_(visits.c.visibility == PUBLIC, visits.c.author_id == viewer_id),
        )
        .scalar_subquery()
    )
    followers = (
        select(func.count())
        .select_from(restaurant_follows)
        .where(restaurant_follows.c.restaurant_id == restaurant_id)
        .scalar_subquery()
    )
    viewer_follows = (
        select(restaurant_follows.c.user_id)
        .where(
            restaurant_follows.c.user_id == viewer_id,
            restaurant_follows.c.restaurant_id == restaurant_id,
        )
        .exists()
    )
    return select(
        visible_photos.label("photos_count"),
        visible_reviews.label("reviews_count"),
        visible_visits.label("visits_count"),
        followers.label("followers_count"),
        viewer_follows.label("viewer_follows"),
    )


def get_restaurant_detail(restaurant_id: UUID, *, viewer_id: UUID) -> RestaurantDetail:
    """The restaurant page: everything it needs to present itself, minus the gallery.

    The gallery has its own endpoint because it grows without bound with the
    activity of the restaurant. What is here does not: every block below costs
    one bounded query, and none depends on the size of that history.
    """
    try:
        with engine.connect() as connection:
            restaurant = _get_restaurant(connection, restaurant_id)
            counters = (
                connection.execute(_restaurant_counters_statement(restaurant_id, viewer_id))
                .mappings()
                .one()
            )
            ratings = _evaluation_summary(connection, restaurant_id)
    except RestaurantNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error

    return RestaurantDetail(
        id=restaurant.id,
        name=restaurant.name,
        address=restaurant.address,
        latitude=restaurant.latitude,
        longitude=restaurant.longitude,
        cuisine_styles=restaurant.cuisine_styles,
        created_at=restaurant.created_at,
        updated_at=restaurant.updated_at,
        counters=RestaurantCounters(
            photos=counters["photos_count"],
            reviews=counters["reviews_count"],
            # Evaluations arrive with épica 11. The counter reports what the
            # summary aggregates, so both numbers agree on the same screen.
            evaluations=ratings.total,
            visits=counters["visits_count"],
            followers=counters["followers_count"],
        ),
        ratings=ratings,
        viewer=RestaurantViewerRelationship(following=bool(counters["viewer_follows"])),
    )


def get_restaurant(restaurant_id: UUID) -> Restaurant:
    try:
        with engine.connect() as connection:
            return _get_restaurant(connection, restaurant_id)
    except RestaurantNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def create_restaurant(
    *,
    name: str,
    address: str,
    latitude: float,
    longitude: float,
    cuisine_style_slugs: Sequence[str],
) -> Restaurant:
    restaurant_id = uuid4()
    timestamp = datetime.now(UTC)
    normalized_name = normalize_restaurant_text(name)
    search_name = normalize_restaurant_search_text(name)
    normalized_address = normalize_restaurant_text(address)
    identity_key = restaurant_identity_key(name, address)

    def create(connection: Connection) -> Restaurant:
        duplicate = connection.scalar(
            select(restaurants.c.id).where(restaurants.c.identity_key == identity_key)
        )
        if duplicate:
            raise DuplicateRestaurantError(_get_restaurant(connection, duplicate))

        style_ids = _resolve_cuisine_style_ids(connection, cuisine_style_slugs)
        connection.execute(
            insert(restaurants).values(
                id=restaurant_id,
                name=name,
                normalized_name=normalized_name,
                search_name=search_name,
                address=address,
                normalized_address=normalized_address,
                identity_key=identity_key,
                latitude=latitude,
                longitude=longitude,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        connection.execute(
            insert(restaurant_cuisine_styles),
            [
                {"restaurant_id": restaurant_id, "cuisine_style_id": style_id}
                for style_id in style_ids
            ],
        )
        return _get_restaurant(connection, restaurant_id)

    try:
        return run_transaction_with_retry(engine, create)
    except (DuplicateRestaurantError, UnknownCuisineStylesError):
        raise
    except IntegrityError as error:
        if _is_unique_violation(error):
            raise DuplicateRestaurantError(_find_by_identity_key(identity_key)) from error
        raise RestaurantStoreError from error
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def update_restaurant(restaurant_id: UUID, changes: Mapping[str, object]) -> Restaurant:
    timestamp = datetime.now(UTC)

    def modify(connection: Connection) -> Restaurant:
        current = (
            connection.execute(select(restaurants).where(restaurants.c.id == restaurant_id))
            .mappings()
            .first()
        )
        if not current:
            raise RestaurantNotFoundError

        values: dict[str, object] = {"updated_at": timestamp}
        for field in ("name", "address", "latitude", "longitude"):
            if field in changes:
                values[field] = changes[field]

        normalized_name = (
            normalize_restaurant_text(cast(str, changes["name"]))
            if "name" in changes
            else current["normalized_name"]
        )
        normalized_address = (
            normalize_restaurant_text(cast(str, changes["address"]))
            if "address" in changes
            else current["normalized_address"]
        )
        values["normalized_name"] = normalized_name
        values["search_name"] = normalize_restaurant_search_text(
            cast(str, changes.get("name", current["name"]))
        )
        values["normalized_address"] = normalized_address
        identity_key = restaurant_identity_key(
            cast(str, changes.get("name", current["name"])),
            cast(str, changes.get("address", current["address"])),
        )
        values["identity_key"] = identity_key

        duplicate = connection.scalar(
            select(restaurants.c.id).where(
                restaurants.c.identity_key == identity_key,
                restaurants.c.id != restaurant_id,
            )
        )
        if duplicate:
            raise DuplicateRestaurantError(_get_restaurant(connection, duplicate))

        style_ids = None
        if "cuisine_styles" in changes:
            style_ids = _resolve_cuisine_style_ids(
                connection, cast(Sequence[str], changes["cuisine_styles"])
            )

        connection.execute(
            update(restaurants).where(restaurants.c.id == restaurant_id).values(values)
        )
        if style_ids is not None:
            connection.execute(
                delete(restaurant_cuisine_styles).where(
                    restaurant_cuisine_styles.c.restaurant_id == restaurant_id
                )
            )
            connection.execute(
                insert(restaurant_cuisine_styles),
                [
                    {"restaurant_id": restaurant_id, "cuisine_style_id": style_id}
                    for style_id in style_ids
                ],
            )
        return _get_restaurant(connection, restaurant_id)

    try:
        return run_transaction_with_retry(engine, modify)
    except (DuplicateRestaurantError, RestaurantNotFoundError, UnknownCuisineStylesError):
        raise
    except IntegrityError as error:
        if _is_unique_violation(error):
            raise DuplicateRestaurantError() from error
        raise RestaurantStoreError from error
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


def delete_restaurant(restaurant_id: UUID) -> None:
    def remove(connection: Connection) -> None:
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        connection.execute(
            delete(restaurant_cuisine_styles).where(
                restaurant_cuisine_styles.c.restaurant_id == restaurant_id
            )
        )
        connection.execute(delete(restaurants).where(restaurants.c.id == restaurant_id))

    try:
        run_transaction_with_retry(engine, remove)
    except RestaurantNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error
