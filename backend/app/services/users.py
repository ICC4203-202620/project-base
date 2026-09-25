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

from sqlalchemy import and_, delete, desc, func, insert, or_, select, union_all
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.countries import country_name
from app.db.retry import run_transaction_with_retry
from app.db.schema import user_follows, users
from app.db.session import engine
from app.services.activity import ACTIVITY_SOURCES, ActivitySource, hydrate
from app.services.auth import normalize_handle
from app.services.cursors import (
    decode_cursor,
    decode_time_cursor,
    encode_cursor,
    encode_time_cursor,
    utc_timestamp,
)
from app.services.visibility import PUBLIC


class UserNotFoundError(Exception):
    """No account uses this handle."""


class UserStoreError(Exception):
    """The user store could not complete an operation."""


LIKE_ESCAPE = "\\"


def _escaped(term: str) -> str:
    """Escape what LIKE would otherwise read as a wildcard."""
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


class SearchTermTooShortError(Exception):
    """A one-character term would return the whole register of people."""


class SelfFollowError(Exception):
    """Nobody follows themself."""


# The same floor the restaurant search uses, so one search behaviour exists in
# the application rather than two.
MINIMUM_SEARCH_LENGTH = 2


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
            select(source.count())
            .select_from(source.identifier.table)
            .where(
                source.author_id == users.c.id,
                or_(source.visibility == PUBLIC, users.c.id == viewer_id),
                # The same restriction the keys apply, so the counter never
                # promises rows the list will not produce.
                *((source.extra_condition(),) if source.extra_condition else ()),
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


def _profile_keys(
    source: ActivitySource, author_id: UUID, viewer_id: UUID, cursor: str | None, limit: int
):
    keys = source.keys(viewer_id).where(source.author_id == author_id)
    if cursor:
        occurred_at, activity_id = decode_time_cursor(cursor)
        keys = source.after(keys, by="occurred", value=occurred_at, identifier=activity_id)
    # The same bound the feed applies, for the same reason: the union reads
    # every branch whole unless each one says where it stops.
    return source.newest(keys, by="occurred", limit=limit)


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
                    _profile_keys(source, author_id, viewer_id, cursor, limit + 1)
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


@dataclass(frozen=True)
class UserSearchResult:
    id: UUID
    handle: str
    name: str
    nationality: Nationality
    # Alongside the summary and not inside it: the search results and the
    # profile need it, the author of every item of a feed page does not, and
    # resolving it there would be a lookup per row.
    following: bool


@dataclass(frozen=True)
class UserSearchPage:
    items: tuple[UserSearchResult, ...]
    next_cursor: str | None


def search_users(
    *, query: str, viewer_id: UUID, limit: int, cursor: str | None = None
) -> UserSearchPage:
    """Find people by handle.

    By handle and not by name: it is what the épica asks, and searching real
    names would turn the application into a directory of people, which is a
    decision about privacy nobody took.

    The term is normalized the way a handle is when it is registered, so
    someone who types `@Demo` — which is how the interface shows handles —
    finds `demo`. No extra normalized column is needed: the handle is already
    stored in its comparison form, which is the benefit of that decision.
    """
    term = normalize_handle(query)
    if len(term) < MINIMUM_SEARCH_LENGTH:
        raise SearchTermTooShortError

    follows = (
        select(user_follows.c.follower_id)
        .where(
            user_follows.c.follower_id == viewer_id,
            user_follows.c.followed_id == users.c.id,
        )
        .exists()
    )
    statement = select(
        users.c.id,
        users.c.handle,
        users.c.name,
        users.c.nationality,
        follows.label("viewer_follows"),
    ).where(users.c.handle.like(f"%{_escaped(term)}%", escape=LIKE_ESCAPE))
    if cursor:
        handle, user_id = decode_cursor(cursor)
        statement = statement.where(
            or_(
                users.c.handle > handle,
                and_(users.c.handle == handle, users.c.id > user_id),
            )
        )

    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    statement.order_by(users.c.handle, users.c.id).limit(limit + 1)
                )
                .mappings()
                .all()
            )
    except SQLAlchemyError as error:
        raise UserStoreError from error

    has_next = len(rows) > limit
    rows = rows[:limit]
    return UserSearchPage(
        items=tuple(
            UserSearchResult(
                id=row["id"],
                handle=row["handle"],
                name=row["name"],
                nationality=Nationality(
                    code=row["nationality"], name=country_name(row["nationality"])
                ),
                # The viewer appears among their own results when the handle
                # matches; hiding them would be an absence nobody can explain.
                following=bool(row["viewer_follows"]),
            )
            for row in rows
        ),
        next_cursor=(encode_cursor(rows[-1]["handle"], rows[-1]["id"]) if has_next else None),
    )


def _resolve_handle(connection, handle: str) -> UUID:
    user_id = connection.scalar(select(users.c.id).where(users.c.handle == normalize_handle(handle)))
    if user_id is None:
        raise UserNotFoundError
    return user_id


def follow_user(*, follower_id: UUID, handle: str) -> None:
    """Start following a person.

    Idempotent on purpose: the button of the interface declares a state — "I
    want to follow this person" — rather than accumulating an event. Following
    someone already followed is not a conflict, and answering 409 would make
    the interface treat a repeated tap as an error, which on a phone with an
    intermittent connection is a frequent case.
    """

    def persist(connection: Connection) -> None:
        followed_id = _resolve_handle(connection, handle)
        if followed_id == follower_id:
            # The schema forbids it too; rejecting it here keeps the rule
            # testable without leaning on the database error.
            raise SelfFollowError
        already = connection.scalar(
            select(user_follows.c.follower_id).where(
                user_follows.c.follower_id == follower_id,
                user_follows.c.followed_id == followed_id,
            )
        )
        if already:
            return
        connection.execute(
            insert(user_follows).values(follower_id=follower_id, followed_id=followed_id)
        )

    try:
        run_transaction_with_retry(engine, persist)
    except (UserNotFoundError, SelfFollowError):
        raise
    except IntegrityError:
        # Two simultaneous requests: the state the caller asked for is the one
        # that ended up written, which is what idempotent means here.
        return
    except SQLAlchemyError as error:
        raise UserStoreError from error


def unfollow_user(*, follower_id: UUID, handle: str) -> None:
    """Stop following a person, whether or not one was following them."""

    def persist(connection: Connection) -> None:
        followed_id = _resolve_handle(connection, handle)
        connection.execute(
            delete(user_follows).where(
                user_follows.c.follower_id == follower_id,
                user_follows.c.followed_id == followed_id,
            )
        )

    try:
        run_transaction_with_retry(engine, persist)
    except UserNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise UserStoreError from error
