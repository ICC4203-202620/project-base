"""Reviews: the opinion a person adds on top of a photograph they published.

The photograph is the object that gets published, so validation, storage and
compensation live in `app.services.photos`. What stays here is the review, and
`create_review` remains the single place where one is persisted: that is where
each group hooks its Web Push sender.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.db.schema import reviews
from app.media.storage import MediaStorage
from app.services.photos import DISH, Photo, PhotoStoreError, store_photo
from app.services.restaurants import RestaurantNotFoundError
from app.services.visibility import PUBLIC


class ReviewNotFoundError(Exception):
    """A related restaurant or review could not be found."""


class ReviewStoreError(Exception):
    """Review metadata could not be persisted or queried."""


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
    """Publish a photograph of a dish together with the review of it.

    The HTTP contract has not changed, but the upload no longer lives here:
    the photo service validates, stores and writes the photograph, and the
    review is written inside that same transaction. Épica 10 turns this into a
    review over a photograph that already exists.
    """
    review_id = uuid4()

    def persist_review(connection: Connection, photo_id: UUID, timestamp: datetime) -> None:
        connection.execute(
            insert(reviews).values(
                id=review_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                photo_id=photo_id,
                text=text,
                visibility=PUBLIC,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    try:
        photo = store_photo(
            author_id=author_id,
            restaurant_id=restaurant_id,
            kind=DISH,
            dish_name=dish_name,
            caption=None,
            # The review is public until épica 10 brings the choice to the
            # form, and its photograph carries the same visibility.
            visibility=PUBLIC,
            photo_stream=photo_stream,
            declared_content_type=declared_content_type,
            storage=storage,
            persist_with=persist_review,
        )
    except RestaurantNotFoundError as error:
        raise ReviewNotFoundError from error
    except PhotoStoreError as error:
        raise ReviewStoreError from error

    return Review(
        id=review_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        dish_name=photo.dish_name or "",
        text=text,
        visibility=PUBLIC,
        photo=photo,
        created_at=photo.created_at,
        updated_at=photo.created_at,
    )
