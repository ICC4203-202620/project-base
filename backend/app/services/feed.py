"""The chronological view of what the people and restaurants you follow publish."""

from uuid import UUID

from sqlalchemy import desc, or_, select, union_all
from sqlalchemy.exc import SQLAlchemyError

from app.db.schema import restaurant_follows, reviews, user_follows
from app.db.session import engine
from app.services.activity import (
    ACTIVITY_SOURCES,
    ActivitySource,
    hydrate,
    review_activity_statement,
    review_object,
)
from app.services.cursors import decode_time_cursor, encode_time_cursor
from app.services.reviews import ReviewNotFoundError, ReviewStoreError
from app.services.visibility import PUBLIC


def _followed_condition(source: ActivitySource, viewer_id: UUID):
    """Written by someone the viewer follows, or at a restaurant they follow.

    One logical union and not two concatenated lists, so an activity that
    matches both appears once.
    """
    return or_(
        source.author_id.in_(
            select(user_follows.c.followed_id).where(user_follows.c.follower_id == viewer_id)
        ),
        source.restaurant_id.in_(
            select(restaurant_follows.c.restaurant_id).where(
                restaurant_follows.c.user_id == viewer_id
            )
        ),
    )


def _source_keys(source: ActivitySource, viewer_id: UUID, cursor: str | None):
    keys = source.keys(viewer_id).where(
        # Only public activity reaches a feed, including the viewer's own.
        source.visibility == PUBLIC,
        _followed_condition(source, viewer_id),
    )
    if cursor:
        published_at, activity_id = decode_time_cursor(cursor)
        keys = source.after(keys, by="published", value=published_at, identifier=activity_id)
    return keys


def get_feed(viewer_id: UUID, *, limit: int, cursor: str | None = None) -> dict:
    """One page of the feed, ordered by the instant each activity was published.

    The sort keys of every source are unioned, ordered and cut in SQL, so the
    page costs one bounded query however many classes of activity exist. Only
    the rows that made the page are then read.
    """
    key_sets = [_source_keys(source, viewer_id, cursor) for source in ACTIVITY_SOURCES]
    combined = union_all(*key_sets).subquery("activity")
    page = (
        select(combined)
        .order_by(desc(combined.c.published_at), desc(combined.c.id))
        .limit(limit + 1)
    )

    try:
        with engine.connect() as connection:
            keys = connection.execute(page).mappings().all()
            has_next = len(keys) > limit
            keys = keys[:limit]
            items = hydrate(connection, viewer_id, keys)
    except SQLAlchemyError as error:
        raise ReviewStoreError from error

    return {
        "items": items,
        "next_cursor": (
            encode_time_cursor(keys[-1]["published_at"], keys[-1]["id"]) if has_next else None
        ),
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
