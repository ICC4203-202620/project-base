import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.schema import photos, restaurant_follows, restaurants, reviews, user_follows, users
from app.db.session import engine
from app.services.reviews import PUBLIC_VISIBILITY, ReviewNotFoundError, ReviewStoreError


class InvalidFeedCursorError(Exception):
    pass


def _utc_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _encode_cursor(created_at: datetime, review_id: UUID) -> str:
    value = json.dumps(
        {"created_at": _utc_timestamp(created_at).isoformat(), "id": str(review_id)}
    ).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(decoded)
        created_at = datetime.fromisoformat(value["created_at"])
        review_id = UUID(value["id"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at.astimezone(UTC), review_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise InvalidFeedCursorError from error


def _statement(viewer_id: UUID, *, detail: bool = False):
    author = users.alias("author")
    return (
        select(
            reviews.c.id,
            reviews.c.dish_name,
            reviews.c.text,
            reviews.c.visibility,
            reviews.c.created_at,
            reviews.c.updated_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            restaurants.c.id.label("restaurant_id"),
            restaurants.c.name.label("restaurant_name"),
            restaurants.c.address.label("restaurant_address"),
            photos.c.id.label("photo_id"),
            photos.c.content_type.label("photo_content_type"),
        )
        .select_from(
            reviews.join(author, reviews.c.author_id == author.c.id)
            .join(restaurants, reviews.c.restaurant_id == restaurants.c.id)
            .join(photos, reviews.c.photo_id == photos.c.id)
        )
        .where(
            or_(reviews.c.visibility == PUBLIC_VISIBILITY, reviews.c.author_id == viewer_id),
            *(
                ()
                if detail
                else (
                    or_(
                        reviews.c.author_id.in_(
                            select(user_follows.c.followed_id).where(
                                user_follows.c.follower_id == viewer_id
                            )
                        ),
                        reviews.c.restaurant_id.in_(
                            select(restaurant_follows.c.restaurant_id).where(
                                restaurant_follows.c.user_id == viewer_id
                            )
                        ),
                    ),
                )
            ),
        )
    )


def _item(row):
    created_at = _utc_timestamp(row["created_at"])
    updated_at = _utc_timestamp(row["updated_at"])
    return {
        "type": "review",
        "occurred_at": created_at,
        "review": {
            "id": row["id"],
            "dish_name": row["dish_name"],
            "text": row["text"],
            "visibility": row["visibility"],
            "created_at": created_at,
            "updated_at": updated_at,
            "author": {
                "id": row["author_id"],
                "handle": row["author_handle"],
                "name": row["author_name"],
            },
            "restaurant": {
                "id": row["restaurant_id"],
                "name": row["restaurant_name"],
                "address": row["restaurant_address"],
            },
            "photo": {
                "id": row["photo_id"],
                "content_type": row["photo_content_type"],
                "content_url": f"/api/v1/photos/{row['photo_id']}/content",
            },
        },
    }


def get_feed(viewer_id: UUID, *, limit: int, cursor: str | None = None) -> dict:
    statement = _statement(viewer_id).where(reviews.c.visibility == PUBLIC_VISIBILITY)
    if cursor:
        created_at, review_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                reviews.c.created_at < created_at,
                and_(reviews.c.created_at == created_at, reviews.c.id < review_id),
            )
        )
    statement = statement.order_by(desc(reviews.c.created_at), desc(reviews.c.id)).limit(limit + 1)
    try:
        with engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
    except SQLAlchemyError as error:
        raise ReviewStoreError from error
    has_next = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [_item(row) for row in rows],
        "next_cursor": _encode_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None,
    }


def get_review(review_id: UUID, *, viewer_id: UUID) -> dict:
    statement = _statement(viewer_id, detail=True).where(reviews.c.id == review_id)
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise ReviewStoreError from error
    if not row:
        raise ReviewNotFoundError
    return _item(row)["review"]
