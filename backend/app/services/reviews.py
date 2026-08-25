import logging
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import insert, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.retry import run_transaction_with_retry
from app.db.schema import photos, restaurants, reviews
from app.db.session import engine
from app.media.storage import MediaLocation, MediaStorage, MediaStorageError

logger = logging.getLogger(__name__)

PUBLIC_VISIBILITY = "public"
IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
CONTENT_TYPE_ALIASES = {"image/jpg": "image/jpeg"}


class ReviewNotFoundError(Exception):
    """A related restaurant or review could not be found."""


class InvalidReviewPhotoError(Exception):
    """The uploaded file is not an accepted, valid image."""


class ReviewPhotoTooLargeError(InvalidReviewPhotoError):
    """The uploaded image exceeds the configured size limit."""


class ReviewStoreError(Exception):
    """Review metadata could not be persisted or queried."""


class ReviewMediaError(Exception):
    """The media provider could not store or resolve a photograph."""


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
    created_at: datetime

    @property
    def content_url(self) -> str:
        return f"/api/v1/photos/{self.id}/content"


@dataclass(frozen=True)
class Review:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    dish_name: str
    text: str
    visibility: str
    photo: Photo
    created_at: datetime
    updated_at: datetime


def _validated_image(stream: BinaryIO, declared_content_type: str | None) -> ValidatedImage:
    try:
        stream.seek(0, 2)
        size_bytes = stream.tell()
        stream.seek(0)
    except (OSError, ValueError) as error:
        raise InvalidReviewPhotoError from error

    if size_bytes == 0:
        raise InvalidReviewPhotoError
    if size_bytes > settings.media_max_upload_bytes:
        raise ReviewPhotoTooLargeError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                image_format = image.format
                image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError):
        raise InvalidReviewPhotoError from None
    except (OSError, SyntaxError, ValueError) as error:
        raise InvalidReviewPhotoError from error
    finally:
        stream.seek(0)

    if image_format not in IMAGE_FORMATS:
        raise InvalidReviewPhotoError
    content_type, extension = IMAGE_FORMATS[image_format]
    normalized_declared_type = CONTENT_TYPE_ALIASES.get(
        declared_content_type or "", declared_content_type
    )
    if normalized_declared_type != content_type:
        raise InvalidReviewPhotoError
    return ValidatedImage(
        content_type=content_type,
        extension=extension,
        size_bytes=size_bytes,
    )


def _compensate_storage(storage: MediaStorage, storage_key: str) -> None:
    try:
        storage.delete(storage_key)
    except MediaStorageError:
        logger.exception("Could not remove media object after review persistence failure")


def create_review(
    *,
    author_id: UUID,
    restaurant_id: UUID,
    dish_name: str,
    text: str,
    photo_stream: BinaryIO,
    declared_content_type: str | None,
    storage: MediaStorage,
) -> Review:
    validated_image = _validated_image(photo_stream, declared_content_type)
    review_id = uuid4()
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
        raise ReviewMediaError from error

    def persist(connection):
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise ReviewNotFoundError
        connection.execute(
            insert(photos).values(
                id=photo_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                storage_key=storage_key,
                content_type=validated_image.content_type,
                size_bytes=validated_image.size_bytes,
                created_at=timestamp,
            )
        )
        connection.execute(
            insert(reviews).values(
                id=review_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                photo_id=photo_id,
                dish_name=dish_name,
                text=text,
                visibility=PUBLIC_VISIBILITY,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    try:
        run_transaction_with_retry(engine, persist)
    except ReviewNotFoundError:
        _compensate_storage(storage, storage_key)
        raise
    except SQLAlchemyError as error:
        _compensate_storage(storage, storage_key)
        raise ReviewStoreError from error

    photo = Photo(
        id=photo_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        storage_key=storage_key,
        content_type=validated_image.content_type,
        size_bytes=validated_image.size_bytes,
        created_at=timestamp,
    )
    return Review(
        id=review_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        dish_name=dish_name,
        text=text,
        visibility=PUBLIC_VISIBILITY,
        photo=photo,
        created_at=timestamp,
        updated_at=timestamp,
    )


def resolve_photo(
    photo_id: UUID,
    *,
    viewer_id: UUID,
    storage: MediaStorage,
) -> tuple[Photo, MediaLocation]:
    statement = (
        select(photos)
        .select_from(photos.join(reviews, reviews.c.photo_id == photos.c.id))
        .where(
            photos.c.id == photo_id,
            or_(reviews.c.visibility == PUBLIC_VISIBILITY, reviews.c.author_id == viewer_id),
        )
    )
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise ReviewStoreError from error
    if not row:
        raise ReviewNotFoundError

    photo = Photo(
        id=row["id"],
        author_id=row["author_id"],
        restaurant_id=row["restaurant_id"],
        storage_key=row["storage_key"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
    )
    try:
        return photo, storage.resolve(photo.storage_key)
    except MediaStorageError as error:
        raise ReviewMediaError from error
