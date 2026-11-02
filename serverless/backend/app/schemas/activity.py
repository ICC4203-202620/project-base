"""Response models for the activity envelope, shared by the feed and profiles."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Nationality(BaseModel):
    code: str
    # Null when the stored code is not in the catalogue, which a row written
    # before the catalogue existed may be.
    name: str | None


class UserSummary(BaseModel):
    """How a person is shown anywhere in the API.

    Defined once: the author of an activity, the header of a profile and a
    result of the user search are the same card, and three shapes of it would
    force the client to normalize them before drawing.
    """

    id: UUID
    handle: str
    name: str
    nationality: Nationality


class ActivityRestaurant(BaseModel):
    """Only what an activity card shows.

    Deliberately thinner than the RestaurantSummary of the collections: the
    feed does not draw a marker, and loading cuisine styles here would add a
    query per page for something nobody reads.
    """

    id: UUID
    name: str
    address: str


class ActivityPhoto(BaseModel):
    id: UUID
    content_type: str
    content_url: str
    caption: str | None


class ActivityReview(BaseModel):
    id: UUID
    dish_name: str
    rating: int
    text: str
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: ActivityRestaurant
    photo: ActivityPhoto
    created_at: datetime
    updated_at: datetime


class ActivityVisit(BaseModel):
    id: UUID
    occurred_at: datetime
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: ActivityRestaurant
    created_at: datetime


class ActivityPhotograph(BaseModel):
    id: UUID
    content_type: str
    content_url: str
    dish_name: str | None
    caption: str | None


class ActivityPhotos(BaseModel):
    """One act of publishing, which may carry more than one photograph.

    A collection from the start: épica 9 publishes several in a single act and
    presents them as one activity.
    """

    kind: str
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: ActivityRestaurant
    photos: list[ActivityPhotograph]


class CriterionRating(BaseModel):
    criterion: str
    rating: int


class EvaluationPhoto(BaseModel):
    id: UUID
    content_url: str


class ActivityEvaluation(BaseModel):
    id: UUID
    comment: str
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: ActivityRestaurant
    ratings: list[CriterionRating]
    photos: list[EvaluationPhoto]
    created_at: datetime


class Activity(BaseModel):
    type: Literal["review", "visit", "photo", "evaluation"]
    occurred_at: datetime
    published_at: datetime
    # Exactly one of these carries the activity, named after its type.
    review: ActivityReview | None = None
    visit: ActivityVisit | None = None
    photo: ActivityPhotos | None = None
    evaluation: ActivityEvaluation | None = None


class ActivityPage(BaseModel):
    items: list[Activity]
    next_cursor: str | None
