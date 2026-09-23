from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Nationality(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    # Null when the stored code is not in the catalogue, which a row written
    # before the catalogue existed may be.
    name: str | None


class ProfileCounters(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity: int
    followers: int
    following: int


class ViewerRelationship(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_self: bool
    following: bool
    followed_by: bool


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    handle: str
    name: str
    nationality: Nationality
    joined_at: datetime
    # These three depend on who is asking: the owner sees their whole activity
    # counted, anyone else only the public part.
    counters: ProfileCounters
    viewer: ViewerRelationship
