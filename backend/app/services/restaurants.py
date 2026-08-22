from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from unicodedata import normalize
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.retry import run_transaction_with_retry
from app.db.schema import cuisine_styles, restaurant_cuisine_styles, restaurants
from app.db.session import engine


class RestaurantNotFoundError(Exception):
    """The requested restaurant does not exist."""


class DuplicateRestaurantError(Exception):
    """A restaurant already uses the normalized name and address."""


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
    """Return the stable comparison form used by the duplicate constraint."""
    return " ".join(normalize("NFKC", value).split()).casefold()


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


def _is_unique_violation(error: IntegrityError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
    return sqlstate == "23505"


def list_restaurants(*, limit: int, offset: int) -> list[Restaurant]:
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    select(restaurants)
                    .order_by(restaurants.c.normalized_name, restaurants.c.id)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
            return _to_restaurants(connection, rows)
    except SQLAlchemyError as error:
        raise RestaurantStoreError from error


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
    normalized_address = normalize_restaurant_text(address)
    identity_key = restaurant_identity_key(name, address)

    def create(connection: Connection) -> Restaurant:
        duplicate = connection.scalar(
            select(restaurants.c.id).where(restaurants.c.identity_key == identity_key)
        )
        if duplicate:
            raise DuplicateRestaurantError

        style_ids = _resolve_cuisine_style_ids(connection, cuisine_style_slugs)
        connection.execute(
            insert(restaurants).values(
                id=restaurant_id,
                name=name,
                normalized_name=normalized_name,
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
            raise DuplicateRestaurantError from error
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
            raise DuplicateRestaurantError

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
            raise DuplicateRestaurantError from error
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
