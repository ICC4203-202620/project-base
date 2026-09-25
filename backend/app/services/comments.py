"""The conversation around a photograph.

This is the only place where somebody writes over somebody else's content.
Everything else the application publishes — visits, photographs, reviews,
evaluations — is one's own record of an experience at a restaurant.

That difference has a consequence worth stating here, because it explains
what this module does not do: **a comment is not activity**. It does not
reach a feed, it does not appear on the profile of whoever wrote it, and it
produces no recipients of a notification. The general statement lists the
four classes of activity and defines the conversation apart from them, and
the classification holds up on its own: a feed tells what people recorded of
their experience, and a thread of twenty messages would flood the feed of
everybody who follows any of the people talking.

The thread has two levels, comments and replies. A reply to a reply hangs
from the same first-level comment instead of opening a third level: unbounded
nesting needs a recursive query, whose support on Aurora DSQL is not
something to take for granted, and an interface that runs out of width on a
phone by the third level.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, func, insert, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.countries import country_name
from app.db.retry import run_transaction_with_retry
from app.db.schema import comments, photos, users
from app.db.session import engine
from app.services.cursors import decode_time_cursor, encode_time_cursor, utc_timestamp
from app.services.users import Nationality
from app.services.visibility import PUBLIC, visible_to

# Long enough for a paragraph, short enough that the thread stays a
# conversation and not a second review.
MAXIMUM_COMMENT_LENGTH = 1000
# How many replies travel inside each comment of a page. Enough to show that
# the conversation continued; the rest are asked for by their own endpoint.
REPLY_PREVIEW = 3


class CommentNotFoundError(Exception):
    """No comment or photograph with this identifier is visible to the viewer."""


class InvalidCommentError(Exception):
    """The text, the photograph or the parent comment cannot be accepted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class CommentStoreError(Exception):
    """The comment store could not complete an operation."""


@dataclass(frozen=True)
class CommentAuthor:
    """The one shape a person has, the same a profile and the search return."""

    id: UUID
    handle: str
    name: str
    nationality: Nationality


@dataclass(frozen=True)
class Comment:
    id: UUID
    photo_id: UUID
    # Null on a comment of the conversation, set on a reply.
    parent_id: UUID | None
    author: CommentAuthor
    text: str
    created_at: datetime


@dataclass(frozen=True)
class CommentThread:
    """A first-level comment with the beginning of its replies."""

    comment: Comment
    # Every reply it has, which may be more than `replies` carries.
    reply_count: int
    replies: tuple[Comment, ...]


@dataclass(frozen=True)
class CommentPage:
    items: tuple[CommentThread, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class ReplyPage:
    items: tuple[Comment, ...]
    next_cursor: str | None


def _comment_columns(author):
    return (
        comments.c.id,
        comments.c.photo_id,
        comments.c.parent_id,
        comments.c.text,
        comments.c.created_at,
        author.c.id.label("author_id"),
        author.c.handle.label("author_handle"),
        author.c.name.label("author_name"),
        author.c.nationality.label("author_nationality"),
    )


def _comment(row) -> Comment:
    return Comment(
        id=row["id"],
        photo_id=row["photo_id"],
        parent_id=row["parent_id"],
        author=CommentAuthor(
            id=row["author_id"],
            handle=row["author_handle"],
            name=row["author_name"],
            nationality=Nationality(
                code=row["author_nationality"],
                name=country_name(row["author_nationality"]),
            ),
        ),
        text=row["text"],
        created_at=utc_timestamp(row["created_at"]),
    )


def _validated_text(text: str) -> str:
    """What is left after trimming has to be something somebody wrote."""
    trimmed = text.strip()
    if not trimmed:
        raise InvalidCommentError("comment text cannot be blank")
    if len(trimmed) > MAXIMUM_COMMENT_LENGTH:
        raise InvalidCommentError(f"comment text cannot exceed {MAXIMUM_COMMENT_LENGTH} characters")
    return trimmed


def _open_photo(connection: Connection, photo_id: UUID, viewer_id: UUID) -> None:
    """Only a public photograph has a conversation.

    A photograph that is not visible answers 404, which is the same answer as
    one that does not exist. A private photograph of the viewer's own is
    visible, so it answers 422: it exists, and the reason it admits no
    comment is not about permission but about there being no audience to
    converse with.
    """
    row = (
        connection.execute(
            select(photos.c.visibility).where(
                photos.c.id == photo_id,
                visible_to(photos.c.visibility, photos.c.author_id, viewer_id),
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise CommentNotFoundError
    if row["visibility"] != PUBLIC:
        raise InvalidCommentError("a private photograph has no conversation")


def create_comment(
    *, author_id: UUID, photo_id: UUID, text: str, parent_id: UUID | None = None
) -> Comment:
    """Write on a public photograph, optionally answering somebody.

    The author of the photograph may comment on their own: they are part of
    the conversation, not an exception to it.
    """
    trimmed = _validated_text(text)
    comment_id = uuid4()
    created_at = datetime.now(UTC)

    def persist(connection: Connection) -> Comment:
        _open_photo(connection, photo_id, author_id)
        resolved_parent = None
        if parent_id is not None:
            parent = (
                connection.execute(
                    select(comments.c.photo_id, comments.c.parent_id).where(
                        comments.c.id == parent_id
                    )
                )
                .mappings()
                .first()
            )
            # A parent that does not exist and a parent of another photograph
            # are both a malformed request and not a missing resource: the
            # resource of this request is the photograph, and it was found.
            if not parent:
                raise InvalidCommentError("the comment being replied to does not exist")
            if parent["photo_id"] != photo_id:
                raise InvalidCommentError(
                    "the comment being replied to belongs to another photograph"
                )
            # Answering a reply is answering the comment it belongs to. The
            # request is accepted, and the thread stays at two levels.
            resolved_parent = parent["parent_id"] or parent_id

        connection.execute(
            insert(comments).values(
                id=comment_id,
                photo_id=photo_id,
                author_id=author_id,
                parent_id=resolved_parent,
                text=trimmed,
                created_at=created_at,
            )
        )
        author = users.alias("comment_author")
        row = (
            connection.execute(
                select(*_comment_columns(author))
                .select_from(comments.join(author, comments.c.author_id == author.c.id))
                .where(comments.c.id == comment_id)
            )
            .mappings()
            .one()
        )
        return _comment(row)

    try:
        return run_transaction_with_retry(engine, persist)
    except (CommentNotFoundError, InvalidCommentError):
        raise
    except SQLAlchemyError as error:
        raise CommentStoreError from error


def _replies_of_page(connection: Connection, parent_ids: tuple[UUID, ...]):
    """Every reply the page shows, and every count, in one query.

    One query per comment is the N+1 the rest of this API avoids. The window
    numbers the replies of each parent and counts them at the same time, and
    the outer select keeps the first few of each.
    """
    if not parent_ids:
        return {}, {}
    author = users.alias("reply_author")
    numbered = (
        select(
            *_comment_columns(author),
            func.row_number()
            .over(
                partition_by=comments.c.parent_id,
                order_by=(asc(comments.c.created_at), asc(comments.c.id)),
            )
            .label("position"),
            func.count().over(partition_by=comments.c.parent_id).label("reply_count"),
        )
        .select_from(comments.join(author, comments.c.author_id == author.c.id))
        .where(comments.c.parent_id.in_(parent_ids))
        .subquery()
    )
    rows = (
        connection.execute(
            select(numbered)
            .where(numbered.c.position <= REPLY_PREVIEW)
            .order_by(numbered.c.parent_id, numbered.c.position)
        )
        .mappings()
        .all()
    )
    replies: dict[UUID, list[Comment]] = {}
    counts: dict[UUID, int] = {}
    for row in rows:
        replies.setdefault(row["parent_id"], []).append(_comment(row))
        counts[row["parent_id"]] = row["reply_count"]
    return replies, counts


def list_comments(
    photo_id: UUID, *, viewer_id: UUID, limit: int, cursor: str | None = None
) -> CommentPage:
    """The conversation of a photograph, newest first.

    The list walks backwards, like every collection of this API, because what
    a screen opens on is the last thing that was said. The replies inside each
    comment walk forwards, because a conversation is read in the order it
    happened.
    """
    author = users.alias("comment_author")
    statement = (
        select(*_comment_columns(author))
        .select_from(comments.join(author, comments.c.author_id == author.c.id))
        .where(comments.c.photo_id == photo_id, comments.c.parent_id.is_(None))
    )
    if cursor:
        created_at, comment_id = decode_time_cursor(cursor)
        statement = statement.where(
            or_(
                comments.c.created_at < created_at,
                and_(comments.c.created_at == created_at, comments.c.id < comment_id),
            )
        )

    try:
        with engine.connect() as connection:
            _open_photo(connection, photo_id, viewer_id)
            rows = (
                connection.execute(
                    statement.order_by(desc(comments.c.created_at), desc(comments.c.id)).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
            has_next = len(rows) > limit
            rows = rows[:limit]
            replies, counts = _replies_of_page(connection, tuple(row["id"] for row in rows))
    except (CommentNotFoundError, InvalidCommentError):
        raise
    except SQLAlchemyError as error:
        raise CommentStoreError from error

    return CommentPage(
        items=tuple(
            CommentThread(
                comment=_comment(row),
                reply_count=counts.get(row["id"], 0),
                replies=tuple(replies.get(row["id"], ())),
            )
            for row in rows
        ),
        next_cursor=(
            encode_time_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None
        ),
    )


def list_replies(
    comment_id: UUID, *, viewer_id: UUID, limit: int, cursor: str | None = None
) -> ReplyPage:
    """The replies of one comment, oldest first."""
    author = users.alias("reply_author")
    statement = (
        select(*_comment_columns(author))
        .select_from(comments.join(author, comments.c.author_id == author.c.id))
        .where(comments.c.parent_id == comment_id)
    )
    if cursor:
        created_at, reply_id = decode_time_cursor(cursor)
        statement = statement.where(
            or_(
                comments.c.created_at > created_at,
                and_(comments.c.created_at == created_at, comments.c.id > reply_id),
            )
        )

    try:
        with engine.connect() as connection:
            parent = (
                connection.execute(select(comments.c.photo_id).where(comments.c.id == comment_id))
                .mappings()
                .first()
            )
            if not parent:
                raise CommentNotFoundError
            # The conversation is only readable where the photograph is, and
            # a photograph that turned private takes its thread with it.
            try:
                _open_photo(connection, parent["photo_id"], viewer_id)
            except InvalidCommentError as error:
                raise CommentNotFoundError from error
            rows = (
                connection.execute(
                    statement.order_by(asc(comments.c.created_at), asc(comments.c.id)).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
    except CommentNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise CommentStoreError from error

    has_next = len(rows) > limit
    rows = rows[:limit]
    return ReplyPage(
        items=tuple(_comment(row) for row in rows),
        next_cursor=(
            encode_time_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None
        ),
    )


def comment_count_column():
    """How many comments a photograph carries, for the row that selects it.

    A correlated subquery and not a query per photograph: the gallery asks for
    it once, inside the statement it was already running.

    It counts the whole conversation, replies included, because that is the
    number a screen shows next to the photograph.
    """
    return (
        select(func.count())
        .select_from(comments)
        .where(comments.c.photo_id == photos.c.id)
        .scalar_subquery()
    )
