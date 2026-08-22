from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.core.security import hash_password
from app.db.fixtures import CUISINE_STYLES, RESTAURANTS
from app.db.schema import (
    cuisine_styles,
    restaurant_cuisine_styles,
    restaurants,
    users,
)
from app.db.session import engine
from app.services.restaurants import normalize_restaurant_text, restaurant_identity_key


def _seed_user(connection: Connection) -> bool:
    if connection.scalar(select(users.c.id).where(users.c.email == "demo@example.com")):
        return False
    connection.execute(
        insert(users).values(
            id=uuid4(),
            email="demo@example.com",
            handle="@demo",
            name="Demo Foodie",
            nationality="Chile",
            password_hash=hash_password("demo-password"),
        )
    )
    return True


def _seed_cuisine_styles(connection: Connection) -> tuple[dict[str, UUID], bool]:
    existing = connection.execute(select(cuisine_styles.c.id, cuisine_styles.c.slug)).mappings()
    by_id = {row["id"]: row for row in existing}
    by_slug = {row["slug"]: row for row in by_id.values()}
    ids_by_fixture_slug: dict[str, UUID] = {}
    changed = False

    for fixture in CUISINE_STYLES:
        row = by_slug.get(fixture.slug) or by_id.get(fixture.id)
        if row:
            ids_by_fixture_slug[fixture.slug] = row["id"]
            continue
        connection.execute(
            insert(cuisine_styles).values(id=fixture.id, slug=fixture.slug, name=fixture.name)
        )
        ids_by_fixture_slug[fixture.slug] = fixture.id
        changed = True

    return ids_by_fixture_slug, changed


def _seed_restaurants(connection: Connection, style_ids: dict[str, UUID]) -> bool:
    existing = connection.execute(
        select(
            restaurants.c.id,
            restaurants.c.identity_key,
        )
    ).mappings()
    existing_ids = set()
    existing_identity_keys = set()
    for row in existing:
        existing_ids.add(row["id"])
        existing_identity_keys.add(row["identity_key"])

    changed = False
    for fixture in RESTAURANTS:
        normalized_name = normalize_restaurant_text(fixture.name)
        normalized_address = normalize_restaurant_text(fixture.address)
        identity_key = restaurant_identity_key(fixture.name, fixture.address)
        if fixture.id in existing_ids or identity_key in existing_identity_keys:
            continue

        connection.execute(
            insert(restaurants).values(
                id=fixture.id,
                name=fixture.name,
                normalized_name=normalized_name,
                address=fixture.address,
                normalized_address=normalized_address,
                identity_key=identity_key,
                latitude=fixture.latitude,
                longitude=fixture.longitude,
            )
        )
        connection.execute(
            insert(restaurant_cuisine_styles),
            [
                {
                    "restaurant_id": fixture.id,
                    "cuisine_style_id": style_ids[style_slug],
                }
                for style_slug in fixture.cuisine_styles
            ],
        )
        changed = True
    return changed


def seed() -> bool:
    """Insert missing local fixtures without updating existing rows."""
    if not settings.seed_demo_data:
        return False

    with engine.begin() as connection:
        user_changed = _seed_user(connection)
        style_ids, styles_changed = _seed_cuisine_styles(connection)
        restaurants_changed = _seed_restaurants(connection, style_ids)
    return user_changed or styles_changed or restaurants_changed


if __name__ == "__main__":
    seed()
