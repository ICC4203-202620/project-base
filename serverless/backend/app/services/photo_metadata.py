"""Consultas de fotografías sin procesamiento de archivos ni dependencia de Pillow."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.photo_kinds import PHOTO_KINDS
from app.db.schema import photos, reviews, users
from app.db.session import engine
from app.services.comments import comment_count_column
from app.services.cursors import decode_time_cursor, encode_time_cursor, utc_timestamp
from app.services.visibility import visible_to


class PhotoNotFoundError(Exception):
    """No photograph with this identifier is visible to the viewer."""


class UnknownPhotoKindError(Exception):
    """A filter asked for a kind of photograph that does not exist."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class PhotoStoreError(Exception):
    """The photo store could not complete an operation."""


@dataclass(frozen=True)
class PhotoAuthor:
    id: UUID
    handle: str
    name: str


@dataclass(frozen=True)
class GalleryPhoto:
    id: UUID
    author: PhotoAuthor
    kind: str
    visibility: str
    dish_name: str | None
    caption: str | None
    created_at: datetime
    content_url: str
    # Absent when the photograph was published on its own, which is what this
    # épica makes possible.
    review_id: UUID | None
    # The whole conversation, replies included. Without it the interface
    # cannot decide whether to offer the way into the thread.
    comments_count: int


@dataclass(frozen=True)
class GalleryPage:
    items: tuple[GalleryPhoto, ...]
    next_cursor: str | None


def visible_photo_condition(viewer_id: UUID):
    """A photograph is visible when it is public or when the viewer took it."""
    return visible_to(photos.c.visibility, photos.c.author_id, viewer_id)


def _gallery_item(row) -> GalleryPhoto:
    return GalleryPhoto(
        id=row["id"],
        author=PhotoAuthor(
            id=row["author_id"],
            handle=row["author_handle"],
            name=row["author_name"],
        ),
        kind=row["kind"],
        visibility=row["visibility"],
        dish_name=row["dish_name"],
        caption=row["caption"],
        created_at=utc_timestamp(row["created_at"]),
        content_url=f"/api/v1/photos/{row['id']}/content",
        review_id=row["review_id"],
        comments_count=row["comments_count"],
    )


def list_restaurant_photos(
    restaurant_id: UUID,
    *,
    viewer_id: UUID,
    limit: int,
    cursor: str | None = None,
    kind: str | None = None,
) -> GalleryPage:
    """The gallery of a restaurant, optionally narrowed to one kind.

    The statement asks that the community learn the offer, the prices and the
    premises of a restaurant, and those are three different walks over the
    same gallery.
    """
    if kind is not None and kind not in PHOTO_KINDS:
        raise UnknownPhotoKindError(f"kind must be one of {', '.join(PHOTO_KINDS)}")

    author = users.alias("author")
    statement = (
        select(
            photos.c.id,
            photos.c.kind,
            photos.c.visibility,
            photos.c.dish_name,
            photos.c.caption,
            photos.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            reviews.c.id.label("review_id"),
            comment_count_column().label("comments_count"),
        )
        .select_from(
            photos.join(author, photos.c.author_id == author.c.id).outerjoin(
                reviews, reviews.c.photo_id == photos.c.id
            )
        )
        .where(photos.c.restaurant_id == restaurant_id, visible_photo_condition(viewer_id))
    )
    if kind is not None:
        statement = statement.where(photos.c.kind == kind)
    if cursor:
        published_at, photo_id = decode_time_cursor(cursor)
        statement = statement.where(
            or_(
                photos.c.created_at < published_at,
                and_(photos.c.created_at == published_at, photos.c.id < photo_id),
            )
        )

    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    statement.order_by(desc(photos.c.created_at), desc(photos.c.id)).limit(
                        limit + 1
                    )
                )
                .mappings()
                .all()
            )
    except SQLAlchemyError as error:
        raise PhotoStoreError from error

    has_next = len(rows) > limit
    rows = rows[:limit]
    return GalleryPage(
        items=tuple(_gallery_item(row) for row in rows),
        next_cursor=(
            encode_time_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None
        ),
    )


def get_photo(photo_id: UUID, *, viewer_id: UUID) -> GalleryPhoto:
    """The metadata of one photograph, with its author and its review if any."""
    author = users.alias("photo_author")
    statement = (
        select(
            photos.c.id,
            photos.c.kind,
            photos.c.visibility,
            photos.c.dish_name,
            photos.c.caption,
            photos.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            reviews.c.id.label("review_id"),
            comment_count_column().label("comments_count"),
        )
        .select_from(
            photos.join(author, photos.c.author_id == author.c.id).outerjoin(
                reviews, reviews.c.photo_id == photos.c.id
            )
        )
        .where(photos.c.id == photo_id, visible_photo_condition(viewer_id))
    )
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise PhotoStoreError from error
    # Absence and lack of permission are both a 404.
    if not row:
        raise PhotoNotFoundError
    return _gallery_item(row)
