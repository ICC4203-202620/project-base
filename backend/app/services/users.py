"""Profiles and the activity a viewer is allowed to see on them.

This is where the visibility rule of the project lives. The endpoint receives
the identity of whoever is looking, from the session, and returns only what
that person may see. The client never filters: a client that filters has
already received what it was meant to hide.

The rule applies before paginating and before counting, so a page never comes
back short and a counter never promises rows the list will not produce.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.countries import country_name
from app.db.schema import reviews, user_follows, users
from app.db.session import engine
from app.services.activity import review_activity_item, review_activity_statement
from app.services.auth import normalize_handle
from app.services.cursors import decode_cursor, encode_cursor, utc_timestamp
from app.services.reviews import PUBLIC_VISIBILITY


class UserNotFoundError(Exception):
    """No account uses this handle."""


class UserStoreError(Exception):
    """The user store could not complete an operation."""


@dataclass(frozen=True)
class Nationality:
    code: str
    name: str | None


@dataclass(frozen=True)
class ProfileCounters:
    """What the viewer can see, not what exists.

    A counter that includes activity the viewer may not list would announce
    the existence of what the visibility rule hides.
    """

    activity: int
    followers: int
    following: int


@dataclass(frozen=True)
class ViewerRelationship:
    is_self: bool
    following: bool
    followed_by: bool


@dataclass(frozen=True)
class Profile:
    id: UUID
    handle: str
    name: str
    nationality: Nationality
    joined_at: datetime
    counters: ProfileCounters
    viewer: ViewerRelationship


def _profile_statement(handle: str, viewer_id: UUID):
    # Correlated on users, so the whole profile is one round trip instead of
    # one query per counter.
    visible_activity = or_(reviews.c.visibility == PUBLIC_VISIBILITY, users.c.id == viewer_id)
    activity_count = (
        select(func.count())
        .select_from(reviews)
        .where(reviews.c.author_id == users.c.id, visible_activity)
        .correlate(users)
        .scalar_subquery()
    )
    followers_count = (
        select(func.count())
        .select_from(user_follows)
        .where(user_follows.c.followed_id == users.c.id)
        .correlate(users)
        .scalar_subquery()
    )
    following_count = (
        select(func.count())
        .select_from(user_follows)
        .where(user_follows.c.follower_id == users.c.id)
        .correlate(users)
        .scalar_subquery()
    )
    viewer_follows = (
        select(user_follows.c.follower_id)
        .where(
            user_follows.c.follower_id == viewer_id,
            user_follows.c.followed_id == users.c.id,
        )
        .correlate(users)
        .exists()
    )
    followed_by_viewer = (
        select(user_follows.c.follower_id)
        .where(
            user_follows.c.follower_id == users.c.id,
            user_follows.c.followed_id == viewer_id,
        )
        .correlate(users)
        .exists()
    )
    return select(
        users.c.id,
        users.c.handle,
        users.c.name,
        users.c.nationality,
        users.c.created_at,
        activity_count.label("activity_count"),
        followers_count.label("followers_count"),
        following_count.label("following_count"),
        viewer_follows.label("viewer_follows"),
        followed_by_viewer.label("followed_by_viewer"),
    ).where(users.c.handle == handle)


def get_profile(handle: str, *, viewer_id: UUID) -> Profile:
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(_profile_statement(normalize_handle(handle), viewer_id))
                .mappings()
                .first()
            )
    except SQLAlchemyError as error:
        raise UserStoreError from error

    if not row:
        raise UserNotFoundError

    return Profile(
        id=row["id"],
        handle=row["handle"],
        name=row["name"],
        nationality=Nationality(
            code=row["nationality"],
            name=country_name(row["nationality"]),
        ),
        joined_at=utc_timestamp(row["created_at"]),
        counters=ProfileCounters(
            activity=row["activity_count"],
            followers=row["followers_count"],
            following=row["following_count"],
        ),
        viewer=ViewerRelationship(
            is_self=row["id"] == viewer_id,
            following=bool(row["viewer_follows"]),
            followed_by=bool(row["followed_by_viewer"]),
        ),
    )


def get_activity(handle: str, *, viewer_id: UUID, limit: int, cursor: str | None = None) -> dict:
    """Page the activity of one profile, newest first.

    A profile is the chronology of that person, so it orders by when the
    activity happened. The feed orders by when it was published, which is a
    different question.
    """
    normalized_handle = normalize_handle(handle)
    try:
        with engine.connect() as connection:
            author_id = connection.scalar(
                select(users.c.id).where(users.c.handle == normalized_handle)
            )
            # Resolved first so an unknown handle answers 404 instead of an
            # empty page, which would not be the same answer.
            if author_id is None:
                raise UserNotFoundError

            statement = review_activity_statement(viewer_id).where(reviews.c.author_id == author_id)
            if cursor:
                occurred_at, activity_id = decode_cursor(cursor)
                statement = statement.where(
                    or_(
                        reviews.c.created_at < occurred_at,
                        and_(reviews.c.created_at == occurred_at, reviews.c.id < activity_id),
                    )
                )
            rows = (
                connection.execute(
                    statement.order_by(desc(reviews.c.created_at), desc(reviews.c.id)).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
    except UserNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise UserStoreError from error

    has_next = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [review_activity_item(row) for row in rows],
        "next_cursor": encode_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None,
    }
