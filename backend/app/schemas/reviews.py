from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_type: str
    size_bytes: int
    content_url: str


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID
    restaurant_id: UUID
    dish_name: str
    text: str
    visibility: Literal["public", "private"]
    photo: PhotoResponse
    created_at: datetime
    updated_at: datetime
