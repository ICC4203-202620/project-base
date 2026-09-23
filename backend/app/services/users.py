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
from functools import reduce
from operator import add
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, union_all
from sqlalchemy.exc import SQLAlchemyError

from app.core.countries import country_name
from app.db.schema import user_follows, users
from app.db.session import engine
from app.services.activity import ACTIVITY_SOURCES, ActivitySource, hydrate
from app.services.auth import normalize_handle
from app.services.cursors import decode_time_cursor, encode_time_cursor, utc_timestamp
from app.services.visibility import PUBLIC


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
    # One count per class of activity, added together, so a class that arrives
    # later is one more entry in the registry and nothing else here.
    activity_count = reduce(
        add,
        (
            select(func.count())
            .select_from(source.identifier.table)
            .where(
                source.author_id == users.c.id,
                or_(source.visibility == PUBLIC, users.c.id == viewer_id),
            )
            .correlate(users)
            .scalar_subquery()
            for source in ACTIVITY_SOURCES
        ),
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


def _profile_keys(source: ActivitySource, author_id: UUID, viewer_id: UUID, cursor: str | None):
    keys = source.keys(viewer_id).where(source.author_id == author_id)
    if cursor:
        occurred_at, activity_id = decode_time_cursor(cursor)
        keys = keys.where(
            or_(
                source.occurred_at < occurred_at,
                and_(source.occurred_at == occurred_at, source.identifier < activity_id),
            )
        )
    return keys


def get_activity(handle: str, *, viewer_id: UUID, limit: int, cursor: str | None = None) -> dict:
    """Page the activity of one profile, newest first.

    A profile is the chronology of that person, so it orders by when the
    activity happened. The feed orders by when it was published, which is a
    different question, and both read the same sources.
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

            combined = union_all(
                *(
                    _profile_keys(source, author_id, viewer_id, cursor)
                    for source in ACTIVITY_SOURCES
                )
            ).subquery("activity")
            keys = (
                connection.execute(
                    select(combined)
                    .order_by(desc(combined.c.occurred_at), desc(combined.c.id))
                    .limit(limit + 1)
                )
                .mappings()
                .all()
            )
            has_next = len(keys) > limit
            keys = keys[:limit]
            items = hydrate(connection, viewer_id, keys)
    except UserNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise UserStoreError from error

    return {
        "items": items,
        "next_cursor": encode_time_cursor(keys[-1]["occurred_at"], keys[-1]["id"])
        if has_next
        else None,
    }
