from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.activity import UserSummary


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


class ProfileResponse(UserSummary):
    """The shared summary of a person, plus what only a profile shows."""

    model_config = ConfigDict(from_attributes=True)

    joined_at: datetime
    # These two depend on who is asking: the owner sees their whole activity
    # counted, anyone else only the public part.
    counters: ProfileCounters
    viewer: ViewerRelationship


class UserSearchResultResponse(UserSummary):
    """The same summary, with the one thing the results screen needs.

    The follow state travels alongside and not inside, because the author of
    every item of a feed page does not need it and resolving it there would be
    a lookup per row.
    """

    model_config = ConfigDict(from_attributes=True)

    following: bool


class UserSearchPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[UserSearchResultResponse]
    next_cursor: str | None
