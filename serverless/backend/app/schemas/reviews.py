from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID
    restaurant_id: UUID
    photo_id: UUID
    # Taken from the photograph, which is where the dish lives.
    dish_name: str
    rating: int
    text: str
    visibility: Literal["public", "private"]
    created_at: datetime
    updated_at: datetime
