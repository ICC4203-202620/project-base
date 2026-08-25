from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class UserSummary(BaseModel):
    id: UUID
    handle: str
    name: str


class RestaurantSummary(BaseModel):
    id: UUID
    name: str
    address: str


class FeedPhoto(BaseModel):
    id: UUID
    content_type: str
    content_url: str


class FeedReview(BaseModel):
    id: UUID
    dish_name: str
    text: str
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: RestaurantSummary
    photo: FeedPhoto
    created_at: datetime
    updated_at: datetime


class FeedActivity(BaseModel):
    type: Literal["review"]
    occurred_at: datetime
    review: FeedReview


class FeedPage(BaseModel):
    items: list[FeedActivity]
    next_cursor: str | None
