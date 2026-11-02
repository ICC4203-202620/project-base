from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activity import ActivityEvaluation


class RatingCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str


class EvaluationCreate(BaseModel):
    restaurant_id: UUID
    # Every criterion of the catalogue, exactly once. A partial evaluation
    # would produce averages computed over different populations.
    ratings: dict[str, int]
    comment: str = Field(min_length=1, max_length=2000)
    # Required, with no default: the default belongs to the form.
    visibility: Literal["public", "private"]
    # Optional, and only menu or venue photographs of the same restaurant
    # taken by the same person.
    photo_ids: list[UUID] = Field(default_factory=list, max_length=20)


# The same shape the activity envelope carries, so an evaluation read from a
# page and one read from the feed are the same object.
EvaluationResponse = ActivityEvaluation


class EvaluationPage(BaseModel):
    items: list[EvaluationResponse]
    next_cursor: str | None
