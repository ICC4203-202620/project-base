"""Reading the photographs published at a restaurant.

The gallery lives in its own module because a photograph is on its way to
being the object that gets published, rather than a side effect of writing a
review: épica 8 adds publishing here, and épica 9 the other two kinds. What
this issue contributes is the read that the restaurant page needs, already
resolving visibility against the photograph itself.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.schema import photos, reviews, users
from app.db.session import engine
from app.services.cursors import decode_time_cursor, encode_time_cursor, utc_timestamp
from app.services.visibility import PUBLIC

DISH = "dish"
MENU = "menu"
VENUE = "venue"
PHOTO_KINDS = (DISH, MENU, VENUE)


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
    created_at: datetime
    content_url: str
    # Present when the photograph carries a review. Épica 8 publishes
    # photographs that do not.
    review_id: UUID | None


@dataclass(frozen=True)
class GalleryPage:
    items: tuple[GalleryPhoto, ...]
    next_cursor: str | None


def visible_photo_condition(viewer_id: UUID):
    """A photograph is visible when it is public or when the viewer took it.

    Kept here so no query has to remember it, the same way the review
    statement carries its own.
    """
    return or_(photos.c.visibility == PUBLIC, photos.c.author_id == viewer_id)


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
        created_at=utc_timestamp(row["created_at"]),
        content_url=f"/api/v1/photos/{row['id']}/content",
        review_id=row["review_id"],
    )


def list_restaurant_photos(
    restaurant_id: UUID,
    *,
    viewer_id: UUID,
    limit: int,
    cursor: str | None = None,
) -> GalleryPage:
    author = users.alias("author")
    statement = (
        select(
            photos.c.id,
            photos.c.kind,
            photos.c.visibility,
            photos.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            reviews.c.id.label("review_id"),
        )
        .select_from(
            photos.join(author, photos.c.author_id == author.c.id).outerjoin(
                reviews, reviews.c.photo_id == photos.c.id
            )
        )
        .where(photos.c.restaurant_id == restaurant_id, visible_photo_condition(viewer_id))
    )
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
