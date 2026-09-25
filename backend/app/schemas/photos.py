from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PhotoAuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    handle: str
    name: str


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author: PhotoAuthorResponse
    kind: str
    visibility: str
    # Present for a photograph of a dish, which is the only kind this épica
    # publishes.
    dish_name: str | None
    caption: str | None
    created_at: datetime
    content_url: str
    # Absent when the photograph was published on its own.
    review_id: UUID | None
    # The whole conversation of the photograph, replies included.
    comments_count: int
