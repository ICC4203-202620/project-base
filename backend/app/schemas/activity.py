"""Response models for the activity envelope, shared by the feed and profiles."""

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


class ActivityPhoto(BaseModel):
    id: UUID
    content_type: str
    content_url: str


class ActivityReview(BaseModel):
    id: UUID
    dish_name: str
    text: str
    visibility: Literal["public", "private"]
    author: UserSummary
    restaurant: RestaurantSummary
    photo: ActivityPhoto
    created_at: datetime
    updated_at: datetime


class Activity(BaseModel):
    type: Literal["review"]
    occurred_at: datetime
    published_at: datetime
    review: ActivityReview


class ActivityPage(BaseModel):
    items: list[Activity]
    next_cursor: str | None
