from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.schema import restaurant_follows, reviews, user_follows
from app.db.session import engine
from app.services.activity import (
    review_activity_item,
    review_activity_statement,
    review_object,
)
from app.services.cursors import decode_cursor, encode_cursor
from app.services.reviews import PUBLIC_VISIBILITY, ReviewNotFoundError, ReviewStoreError


def _followed_statement(viewer_id: UUID):
    """Activity of the people and the restaurants the viewer follows.

    The two conditions are one logical union and not two concatenated lists,
    so an activity that matches both appears once.
    """
    return review_activity_statement(viewer_id).where(
        or_(
            reviews.c.author_id.in_(
                select(user_follows.c.followed_id).where(user_follows.c.follower_id == viewer_id)
            ),
            reviews.c.restaurant_id.in_(
                select(restaurant_follows.c.restaurant_id).where(
                    restaurant_follows.c.user_id == viewer_id
                )
            ),
        )
    )


def get_feed(viewer_id: UUID, *, limit: int, cursor: str | None = None) -> dict:
    # The feed orders by the instant of publication, which for a review is the
    # instant it was written.
    statement = _followed_statement(viewer_id).where(reviews.c.visibility == PUBLIC_VISIBILITY)
    if cursor:
        published_at, review_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                reviews.c.created_at < published_at,
                and_(reviews.c.created_at == published_at, reviews.c.id < review_id),
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
        "items": [review_activity_item(row) for row in rows],
        "next_cursor": encode_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None,
    }


def get_review(review_id: UUID, *, viewer_id: UUID) -> dict:
    statement = review_activity_statement(viewer_id).where(reviews.c.id == review_id)
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise ReviewStoreError from error
    if not row:
        raise ReviewNotFoundError
    return review_object(row)
