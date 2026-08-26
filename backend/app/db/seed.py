from pathlib import Path
from uuid import UUID

from sqlalchemy import insert, or_, select
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.core.security import hash_password
from app.db.fixtures import (
    CUISINE_STYLES,
    DEMO_USERS,
    RESTAURANT_FOLLOWS,
    RESTAURANTS,
    REVIEW_FIXTURES,
    USER_FOLLOWS,
)
from app.db.schema import (
    cuisine_styles,
    photos,
    restaurant_cuisine_styles,
    restaurant_follows,
    restaurants,
    reviews,
    user_follows,
    users,
)
from app.db.session import engine
from app.media.storage import MediaStorage, get_media_storage
from app.services.restaurants import normalize_restaurant_text, restaurant_identity_key


class FixtureIdentityConflictError(RuntimeError):
    """A fixture's stable and natural identities resolve to different rows."""


def _seed_users(connection: Connection) -> tuple[dict[UUID, UUID], bool]:
    """Insert missing users and map every fixture UUID to its persisted row."""
    existing = (
        connection.execute(
            select(users.c.id, users.c.email).where(
                or_(
                    users.c.id.in_(fixture.id for fixture in DEMO_USERS),
                    users.c.email.in_(fixture.email for fixture in DEMO_USERS),
                )
            )
        )
        .mappings()
        .all()
    )
    by_id = {row["id"]: row for row in existing}
    by_email = {row["email"]: row for row in existing}

    persisted_ids: dict[UUID, UUID] = {}
    changed = False
    for fixture in DEMO_USERS:
        id_match = by_id.get(fixture.id)
        email_match = by_email.get(fixture.email)
        if id_match and email_match and id_match["id"] != email_match["id"]:
            raise FixtureIdentityConflictError(
                f"Demo user {fixture.email} matches different rows by UUID and email"
            )
        existing_row = email_match or id_match
        if existing_row:
            persisted_ids[fixture.id] = existing_row["id"]
            continue
        connection.execute(
            insert(users).values(
                id=fixture.id,
                email=fixture.email,
                handle=fixture.handle,
                name=fixture.name,
                nationality=fixture.nationality,
                password_hash=hash_password(fixture.password),
            )
        )
        persisted_ids[fixture.id] = fixture.id
        changed = True
    if len(set(persisted_ids.values())) != len(persisted_ids):
        raise FixtureIdentityConflictError("Multiple demo users resolve to the same persisted row")
    return persisted_ids, changed


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


def _seed_restaurants(
    connection: Connection, style_ids: dict[str, UUID]
) -> tuple[dict[UUID, UUID], bool]:
    existing = connection.execute(
        select(
            restaurants.c.id,
            restaurants.c.identity_key,
        )
    ).mappings()
    by_id = {row["id"]: row for row in existing}
    by_identity_key = {row["identity_key"]: row for row in by_id.values()}

    persisted_ids: dict[UUID, UUID] = {}
    changed = False
    for fixture in RESTAURANTS:
        normalized_name = normalize_restaurant_text(fixture.name)
        normalized_address = normalize_restaurant_text(fixture.address)
        identity_key = restaurant_identity_key(fixture.name, fixture.address)
        id_match = by_id.get(fixture.id)
        identity_match = by_identity_key.get(identity_key)
        if id_match and identity_match and id_match["id"] != identity_match["id"]:
            raise FixtureIdentityConflictError(
                f"Restaurant {fixture.name} matches different rows by UUID and identity"
            )
        existing_row = identity_match or id_match
        if existing_row:
            persisted_ids[fixture.id] = existing_row["id"]
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
        persisted_ids[fixture.id] = fixture.id
        changed = True
    if len(set(persisted_ids.values())) != len(persisted_ids):
        raise FixtureIdentityConflictError(
            "Multiple restaurant fixtures resolve to the same persisted row"
        )
    return persisted_ids, changed


FIXTURE_ASSET_DIRECTORY = Path(__file__).parent / "assets" / "reviews"


def _seed_feed_fixtures(
    connection: Connection,
    storage: MediaStorage,
    stored_keys: list[str],
    user_ids: dict[UUID, UUID],
    restaurant_ids: dict[UUID, UUID],
) -> bool:
    changed = False
    existing_user_follows = set(
        connection.execute(select(user_follows.c.follower_id, user_follows.c.followed_id))
    )
    for follow in USER_FOLLOWS:
        persisted_follow = (user_ids[follow[0]], user_ids[follow[1]])
        if persisted_follow[0] == persisted_follow[1]:
            raise FixtureIdentityConflictError("User follow fixture resolves to a self-follow")
        if persisted_follow not in existing_user_follows:
            connection.execute(
                insert(user_follows).values(
                    follower_id=persisted_follow[0], followed_id=persisted_follow[1]
                )
            )
            changed = True
    existing_restaurant_follows = set(
        connection.execute(select(restaurant_follows.c.user_id, restaurant_follows.c.restaurant_id))
    )
    for follow in RESTAURANT_FOLLOWS:
        persisted_follow = (user_ids[follow[0]], restaurant_ids[follow[1]])
        if persisted_follow not in existing_restaurant_follows:
            connection.execute(
                insert(restaurant_follows).values(
                    user_id=persisted_follow[0], restaurant_id=persisted_follow[1]
                )
            )
            changed = True
    existing_review_ids = set(connection.scalars(select(reviews.c.id)))
    existing_photo_ids = set(connection.scalars(select(photos.c.id)))
    for fixture in REVIEW_FIXTURES:
        if fixture.id in existing_review_ids or fixture.photo_id in existing_photo_ids:
            continue
        author_id = user_ids[fixture.author_id]
        restaurant_id = restaurant_ids[fixture.restaurant_id]
        asset_path = FIXTURE_ASSET_DIRECTORY / fixture.asset_name
        with asset_path.open("rb") as stream:
            storage_key = storage.store(
                media_id=fixture.photo_id,
                stream=stream,
                content_type=fixture.content_type,
                extension=asset_path.suffix.removeprefix("."),
            )
        stored_keys.append(storage_key)
        connection.execute(
            insert(photos).values(
                id=fixture.photo_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                storage_key=storage_key,
                content_type=fixture.content_type,
                size_bytes=asset_path.stat().st_size,
                created_at=fixture.created_at,
            )
        )
        connection.execute(
            insert(reviews).values(
                id=fixture.id,
                photo_id=fixture.photo_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                dish_name=fixture.dish_name,
                text=fixture.text,
                visibility=fixture.visibility,
                created_at=fixture.created_at,
                updated_at=fixture.created_at,
            )
        )
        changed = True
    return changed


def seed(storage: MediaStorage | None = None) -> bool:
    """Insert missing local fixtures without updating existing rows."""
    if not settings.seed_demo_data:
        return False

    storage = storage or get_media_storage()
    stored_keys: list[str] = []
    try:
        with engine.begin() as connection:
            user_ids, users_changed = _seed_users(connection)
            style_ids, styles_changed = _seed_cuisine_styles(connection)
            restaurant_ids, restaurants_changed = _seed_restaurants(connection, style_ids)
            feed_changed = _seed_feed_fixtures(
                connection,
                storage,
                stored_keys,
                user_ids,
                restaurant_ids,
            )
    except Exception:
        for storage_key in stored_keys:
            storage.delete(storage_key)
        raise
    return users_changed or styles_changed or restaurants_changed or feed_changed


if __name__ == "__main__":
    seed()
