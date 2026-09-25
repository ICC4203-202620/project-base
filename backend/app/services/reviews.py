"""Reviews: the opinion a person adds on top of a photograph they published.

The photograph is what gets published, so it exists first and this module
never uploads anything. `create_review` remains the single place where a
review is persisted: that is where each group hooks its Web Push sender.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.db.retry import run_transaction_with_retry
from app.db.schema import photos, reviews
from app.db.session import engine
from app.services.photos import DISH
from app.services.visibility import PRIVATE, PUBLIC, VISIBILITIES, visible_to

MINIMUM_RATING = 1
MAXIMUM_RATING = 5


class ReviewNotFoundError(Exception):
    """The review, or the photograph it would be about, is not reachable."""


class InvalidReviewError(Exception):
    """The rating, the text, the visibility or the photograph cannot be accepted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class DuplicateReviewError(Exception):
    """The photograph already carries a review.

    It carries the existing one so the interface can take the person to it
    instead of leaving them on an error.
    """

    def __init__(self, existing_id: UUID):
        self.existing_id = existing_id
        super().__init__(str(existing_id))


class ReviewStoreError(Exception):
    """Review metadata could not be persisted or queried."""


@dataclass(frozen=True)
class Review:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    photo_id: UUID
    dish_name: str
    rating: int
    text: str
    visibility: str
    created_at: datetime
    updated_at: datetime


def _validated_request(rating: int, text: str, visibility: str) -> str:
    if not isinstance(rating, int) or isinstance(rating, bool):
        raise InvalidReviewError("rating must be a whole number")
    if not MINIMUM_RATING <= rating <= MAXIMUM_RATING:
        raise InvalidReviewError(
            f"rating must be between {MINIMUM_RATING} and {MAXIMUM_RATING}"
        )
    if visibility not in VISIBILITIES:
        raise InvalidReviewError("visibility must be public or private")
    body = text.strip()
    if not body:
        raise InvalidReviewError("a review cannot be empty")
    return body


def _validated_photo(photo, *, author_id: UUID, visibility: str) -> None:
    """Who may review this photograph, and how visible that review may be.

    The review is written by whoever took the photograph. There is a reason of
    domain — one reviews the dish one ate and photographed — and a structural
    one: each photograph admits a single review, so letting anyone write it
    would leave a stranger occupying the only slot its owner has.
    """
    if photo["author_id"] != author_id:
        raise InvalidReviewError("a review is written by whoever took the photograph")
    if photo["kind"] != DISH:
        raise InvalidReviewError("only a photograph of a dish can be reviewed")
    # Never more visible than the photograph it talks about. Private over
    # public is coherent — I share the photograph and keep the opinion — but
    # public over private would show everyone the text of something nobody
    # can see.
    if visibility == PUBLIC and photo["visibility"] == PRIVATE:
        raise InvalidReviewError("a review cannot be more visible than its photograph")


def create_review(
    *,
    author_id: UUID,
    photo_id: UUID,
    rating: int,
    text: str,
    visibility: str,
) -> Review:
    """Add a review to a photograph that already exists."""
    body = _validated_request(rating, text, visibility)
    review_id = uuid4()
    timestamp = datetime.now(UTC)

    def persist(connection: Connection) -> Review:
        photo = (
            connection.execute(
                select(
                    photos.c.id,
                    photos.c.author_id,
                    photos.c.restaurant_id,
                    photos.c.kind,
                    photos.c.visibility,
                    photos.c.dish_name,
                ).where(
                    photos.c.id == photo_id,
                    visible_to(photos.c.visibility, photos.c.author_id, author_id),
                )
            )
            .mappings()
            .first()
        )
        # Absence and lack of permission are both a 404, as everywhere else.
        if not photo:
            raise ReviewNotFoundError
        _validated_photo(photo, author_id=author_id, visibility=visibility)

        existing = connection.scalar(
            select(reviews.c.id).where(reviews.c.photo_id == photo_id)
        )
        if existing:
            raise DuplicateReviewError(existing)

        connection.execute(
            insert(reviews).values(
                id=review_id,
                author_id=author_id,
                restaurant_id=photo["restaurant_id"],
                photo_id=photo_id,
                rating=rating,
                text=body,
                visibility=visibility,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        return Review(
            id=review_id,
            author_id=author_id,
            restaurant_id=photo["restaurant_id"],
            photo_id=photo_id,
            dish_name=photo["dish_name"] or "",
            rating=rating,
            text=body,
            visibility=visibility,
            created_at=timestamp,
            updated_at=timestamp,
        )

    try:
        return run_transaction_with_retry(engine, persist)
    except (ReviewNotFoundError, InvalidReviewError, DuplicateReviewError):
        raise
    except SQLAlchemyError as error:
        raise ReviewStoreError from error
