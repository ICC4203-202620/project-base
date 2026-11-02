from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activity import UserSummary
from app.services.comments import MAXIMUM_COMMENT_LENGTH


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=MAXIMUM_COMMENT_LENGTH)
    # Absent for a comment of the conversation. Answering a reply is accepted
    # and lands on the comment that reply belongs to.
    parent_id: UUID | None = None


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    photo_id: UUID
    # Null on a comment, set on a reply.
    parent_id: UUID | None
    author: UserSummary
    text: str
    created_at: datetime


class CommentThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comment: CommentResponse
    # Every reply the comment has, which may be more than `replies` carries.
    reply_count: int
    # The first ones, oldest first.
    replies: list[CommentResponse]


class CommentPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CommentThreadResponse]
    next_cursor: str | None


class ReplyPage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CommentResponse]
    next_cursor: str | None
