"""Publishing and reading photographs.

A photograph is the object that gets published: it has an author, a
restaurant, a visibility of its own and, when it shows a dish, the name of
that dish. A review is an opinion added on top of one, which is why the dish
lives here and not there.

This module owns the whole upload path — validation, storage and the
compensation that follows a failure — so there is one place where an image
enters the system, whoever asked for it.
"""

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_, desc, insert, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.retry import run_transaction_with_retry
from app.db.schema import photos, restaurants, reviews, users
from app.db.session import engine
from app.media.storage import MediaLocation, MediaStorage, MediaStorageError
from app.services.cursors import decode_time_cursor, encode_time_cursor, utc_timestamp
from app.services.notifications import notify
from app.services.restaurants import (
    RestaurantNotFoundError,
    normalize_restaurant_search_text,
)
from app.services.visibility import VISIBILITIES, visible_to

logger = logging.getLogger(__name__)

DISH = "dish"
MENU = "menu"
VENUE = "venue"
PHOTO_KINDS = (DISH, MENU, VENUE)
# A group without a limit turns one entry of the feed into a whole gallery.
MAXIMUM_PHOTOS_PER_GROUP = 10

IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
CONTENT_TYPE_ALIASES = {"image/jpg": "image/jpeg"}


class PhotoNotFoundError(Exception):
    """No photograph with this identifier is visible to the viewer."""


class InvalidPhotoError(Exception):
    """The file is not an accepted, valid image."""


class PhotoTooLargeError(InvalidPhotoError):
    """The image exceeds the configured size limit."""


class InvalidPhotoPublicationError(Exception):
    """The kind, the dish, the visibility or the group cannot be accepted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class UnknownPhotoKindError(Exception):
    """A filter asked for a kind of photograph that does not exist."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class PhotoMediaError(Exception):
    """The media provider could not store or resolve a photograph."""


class PhotoStoreError(Exception):
    """The photo store could not complete an operation."""


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    extension: str
    size_bytes: int


@dataclass(frozen=True)
class Photo:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    storage_key: str
    content_type: str
    size_bytes: int
    visibility: str
    kind: str
    dish_name: str | None
    caption: str | None
    created_at: datetime

    @property
    def content_url(self) -> str:
        return f"/api/v1/photos/{self.id}/content"


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


def _validated_image(stream: BinaryIO, declared_content_type: str | None) -> ValidatedImage:
    """Measure and verify the file before anything is written.

    The declared MIME has to match what the bytes actually are: a client that
    renames a file must not be able to decide what the server stores.
    """
    try:
        stream.seek(0, 2)
        size_bytes = stream.tell()
        stream.seek(0)
    except (OSError, ValueError) as error:
        raise InvalidPhotoError from error

    if size_bytes == 0:
        raise InvalidPhotoError
    if size_bytes > settings.media_max_upload_bytes:
        raise PhotoTooLargeError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                image_format = image.format
                image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError):
        raise InvalidPhotoError from None
    except (OSError, SyntaxError, ValueError) as error:
        raise InvalidPhotoError from error
    finally:
        stream.seek(0)

    if image_format not in IMAGE_FORMATS:
        raise InvalidPhotoError
    content_type, extension = IMAGE_FORMATS[image_format]
    normalized_declared_type = CONTENT_TYPE_ALIASES.get(
        declared_content_type or "", declared_content_type
    )
    if normalized_declared_type != content_type:
        raise InvalidPhotoError
    return ValidatedImage(
        content_type=content_type,
        extension=extension,
        size_bytes=size_bytes,
    )


def compensate_storage(storage: MediaStorage, storage_key: str) -> None:
    """Remove an object whose row could not be written.

    The filesystem and SQL do not share a transaction, so the object is stored
    first and undone if the transaction fails. A failure of the compensation
    itself is logged rather than hidden behind the original error.
    """
    try:
        storage.delete(storage_key)
    except MediaStorageError:
        logger.exception("Could not remove media object after photo persistence failure")


def _validated_publication(kind: str, dish_name: str | None, visibility: str) -> str | None:
    """The dish is required for a dish and refused for the other two kinds.

    A photograph of a menu is of no dish, and accepting the field in silence
    produces data that later groups badly.
    """
    if kind not in PHOTO_KINDS:
        raise InvalidPhotoPublicationError(f"kind must be one of {', '.join(PHOTO_KINDS)}")
    if visibility not in VISIBILITIES:
        raise InvalidPhotoPublicationError("visibility must be public or private")
    dish = (dish_name or "").strip()
    if kind == DISH and not dish:
        raise InvalidPhotoPublicationError("a photograph of a dish must name the dish")
    if kind != DISH and dish:
        raise InvalidPhotoPublicationError(f"a photograph of a {kind} is of no dish")
    return dish or None


def _check_group(
    connection: Connection,
    upload_group: UUID,
    *,
    author_id: UUID,
    restaurant_id: UUID,
    kind: str,
    visibility: str,
    dish: str | None,
) -> None:
    """A group is one act, so everything in it has to agree.

    Checked inside the transaction that writes the row, so two simultaneous
    requests of the same act cannot leave it inconsistent. Without this the
    activity item would have no single author or restaurant to show.
    """
    rows = (
        connection.execute(
            select(
                photos.c.author_id,
                photos.c.restaurant_id,
                photos.c.kind,
                photos.c.visibility,
                photos.c.dish_name,
            ).where(photos.c.upload_group == upload_group)
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    if len(rows) >= MAXIMUM_PHOTOS_PER_GROUP:
        raise InvalidPhotoPublicationError(
            f"a group holds at most {MAXIMUM_PHOTOS_PER_GROUP} photographs"
        )
    first = rows[0]
    if (
        first["author_id"] != author_id
        or first["restaurant_id"] != restaurant_id
        or first["kind"] != kind
        or first["visibility"] != visibility
        or first["dish_name"] != dish
    ):
        raise InvalidPhotoPublicationError(
            "every photograph of a group shares its author, restaurant, kind, "
            "visibility and dish"
        )


def store_photo(
    *,
    author_id: UUID,
    restaurant_id: UUID,
    kind: str,
    dish_name: str | None,
    caption: str | None,
    visibility: str,
    photo_stream: BinaryIO,
    declared_content_type: str | None,
    storage: MediaStorage,
    upload_group: UUID | None = None,
    persist_with: Callable[[Connection, UUID, datetime], None] | None = None,
) -> Photo:
    """Validate, store and persist one photograph.

    `persist_with` runs inside the same transaction that writes the row, and
    receives the identifier and the instant of the photograph, which is how a
    review is written together with its photograph without a second upload
    path existing.

    The order is deliberate: validate, store the object, then open the SQL
    transaction. If SQL fails, the object is removed; if validation fails, no
    transaction is ever opened.
    """
    dish = _validated_publication(kind, dish_name, visibility)
    validated_image = _validated_image(photo_stream, declared_content_type)
    photo_id = uuid4()
    timestamp = datetime.now(UTC)

    try:
        storage_key = storage.store(
            media_id=photo_id,
            stream=photo_stream,
            content_type=validated_image.content_type,
            extension=validated_image.extension,
        )
    except MediaStorageError as error:
        raise PhotoMediaError from error

    normalized_caption = (caption or "").strip() or None
    # Only the first photograph of an act announces it. With one request per
    # file the backend cannot know the group is complete, and waiting for it
    # would introduce deferred work this backend does not have and entrega 4
    # migrates to Lambda. By the time the recipient opens the notification the
    # group is complete anyway.
    opens_the_act = True

    def persist(connection: Connection) -> None:
        nonlocal opens_the_act
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        if upload_group is not None:
            opens_the_act = not connection.scalar(
                select(photos.c.id).where(photos.c.upload_group == upload_group).limit(1)
            )
            _check_group(
                connection,
                upload_group,
                author_id=author_id,
                restaurant_id=restaurant_id,
                kind=kind,
                visibility=visibility,
                dish=dish,
            )
        connection.execute(
            insert(photos).values(
                id=photo_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                storage_key=storage_key,
                content_type=validated_image.content_type,
                size_bytes=validated_image.size_bytes,
                visibility=visibility,
                kind=kind,
                dish_name=dish,
                search_dish_name=normalize_restaurant_search_text(dish) if dish else None,
                caption=normalized_caption,
                upload_group=upload_group,
                created_at=timestamp,
            )
        )
        if persist_with is not None:
            persist_with(connection, photo_id, timestamp)

    try:
        run_transaction_with_retry(engine, persist)
    except (RestaurantNotFoundError, InvalidPhotoPublicationError):
        compensate_storage(storage, storage_key)
        raise
    except SQLAlchemyError as error:
        compensate_storage(storage, storage_key)
        raise PhotoStoreError from error

    if opens_the_act:
        notify(
            type="photo",
            id=upload_group or photo_id,
            author_id=author_id,
            restaurant_id=restaurant_id,
            visibility=visibility,
        )
    return Photo(
        id=photo_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        storage_key=storage_key,
        content_type=validated_image.content_type,
        size_bytes=validated_image.size_bytes,
        visibility=visibility,
        kind=kind,
        dish_name=dish,
        caption=normalized_caption,
        created_at=timestamp,
    )


def _photo_from_row(row) -> Photo:
    return Photo(
        id=row["id"],
        author_id=row["author_id"],
        restaurant_id=row["restaurant_id"],
        storage_key=row["storage_key"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        visibility=row["visibility"],
        kind=row["kind"],
        dish_name=row["dish_name"],
        caption=row["caption"],
        created_at=utc_timestamp(row["created_at"]),
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


def resolve_photo(
    photo_id: UUID,
    *,
    viewer_id: UUID,
    storage: MediaStorage,
) -> tuple[Photo, MediaLocation]:
    """The bytes of a photograph, authorized against the photograph itself."""
    statement = select(photos).where(
        photos.c.id == photo_id,
        visible_photo_condition(viewer_id),
    )
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise PhotoStoreError from error
    if not row:
        raise PhotoNotFoundError

    photo = _photo_from_row(row)
    try:
        return photo, storage.resolve(photo.storage_key)
    except MediaStorageError as error:
        raise PhotoMediaError from error
