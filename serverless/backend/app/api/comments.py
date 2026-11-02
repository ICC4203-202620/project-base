from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_current_session, require_trusted_origin
from app.schemas.comments import CommentCreate, CommentPage, CommentResponse, ReplyPage
from app.services import comments as comment_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError

# The conversation of a photograph hangs off the photograph; the replies of a
# comment hang off the comment. Two prefixes, one module, because it is one
# decision about one thing.
router = APIRouter(prefix="/photos", tags=["comments"])
comments_router = APIRouter(prefix="/comments", tags=["comments"])

_THREAD_DESCRIPTION = (
    "The thread has two levels. A reply to a reply is accepted and hangs from the comment "
    "that reply belongs to, so the conversation never opens a third level. A comment is not "
    "activity: it reaches no feed, no profile and no notification."
)


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, comment_service.CommentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, InvalidCursorError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "cursor"],
                    "msg": "cursor was not issued by this API",
                    "input": None,
                }
            ],
        )
    if isinstance(error, comment_service.InvalidCommentError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "text"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Comment service unavailable",
    )


@router.post(
    "/{photo_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    summary="Write on a photograph, or answer somebody",
    responses={
        201: {
            "description": (
                f"At most {comment_service.MAXIMUM_COMMENT_LENGTH} characters, once trimmed. "
                "The author of the photograph may comment on their own: they are part of the "
                f"conversation, not an exception. {_THREAD_DESCRIPTION}"
            )
        },
        404: {"description": "The photograph does not exist or is not visible to this session"},
        422: {
            "description": (
                "A private photograph of this session — a private one of somebody else already "
                "answered 404 — a blank or oversized text, a parent comment that does not "
                "exist, or one belonging to another photograph"
            )
        },
    },
)
def create(
    photo_id: UUID,
    payload: CommentCreate,
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> comment_service.Comment:
    try:
        comment = comment_service.create_comment(
            author_id=session.user_id,
            photo_id=photo_id,
            text=payload.text,
            parent_id=payload.parent_id,
        )
    except (
        comment_service.CommentNotFoundError,
        comment_service.InvalidCommentError,
        comment_service.CommentStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/comments/{comment.id}"
    return comment


@router.get(
    "/{photo_id}/comments",
    response_model=CommentPage,
    summary="The conversation of a photograph",
    responses={
        200: {
            "description": (
                "First-level comments from newest to oldest, paged by opaque cursor. Each one "
                f"carries its first {comment_service.REPLY_PREVIEW} replies, oldest first, and "
                "the total, so the screen draws the conversation without a request per "
                f"comment. The rest are asked for at /comments/{{id}}/replies. {_THREAD_DESCRIPTION}"
            )
        },
        404: {"description": "The photograph does not exist or is not visible to this session"},
        422: {"description": "A private photograph, or a cursor this API did not issue"},
    },
)
def index(
    photo_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> comment_service.CommentPage:
    try:
        return comment_service.list_comments(
            photo_id, viewer_id=session.user_id, limit=limit, cursor=cursor
        )
    except (
        comment_service.CommentNotFoundError,
        comment_service.InvalidCommentError,
        comment_service.CommentStoreError,
        InvalidCursorError,
    ) as error:
        _raise_http_error(error)


@comments_router.get(
    "/{comment_id}/replies",
    response_model=ReplyPage,
    summary="The replies of one comment",
    responses={
        200: {
            "description": (
                "Oldest first, because a conversation is read forwards, paged by opaque cursor."
            )
        },
        404: {
            "description": (
                "The comment does not exist, or its photograph is not visible to this session"
            )
        },
        422: {"description": "A cursor this API did not issue"},
    },
)
def replies(
    comment_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> comment_service.ReplyPage:
    try:
        return comment_service.list_replies(
            comment_id, viewer_id=session.user_id, limit=limit, cursor=cursor
        )
    except (
        comment_service.CommentNotFoundError,
        comment_service.CommentStoreError,
        InvalidCursorError,
    ) as error:
        _raise_http_error(error)
