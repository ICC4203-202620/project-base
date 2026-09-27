from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_session
from app.schemas.activity import ActivityPage, ActivityReview
from app.services import feed as feed_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError
from app.services.reviews import ReviewNotFoundError, ReviewStoreError

router = APIRouter(tags=["feed"])


def _error(error: Exception) -> None:
    if isinstance(error, InvalidCursorError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        )
    if isinstance(error, ReviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Feed service unavailable"
    )


@router.get(
    "/feed",
    response_model=ActivityPage,
    summary="The activity of what this session follows, newest published first",
    responses={
        200: {
            "description": (
                "Only public activity, never the viewer's own, and an activity that matches "
                "both follow criteria appears once. Ordered by the instant of publication, "
                "which is not the instant it happened. A feed with nothing to show is a 200 "
                "with an empty list and no cursor, which is not an error."
            )
        },
        422: {"description": "A cursor this API did not issue"},
        503: {"description": "The feed store did not answer"},
    },
)
def get_feed(
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
):
    try:
        return feed_service.get_feed(session.user_id, limit=limit, cursor=cursor)
    except (InvalidCursorError, ReviewStoreError) as error:
        _error(error)


@router.get(
    "/reviews/{review_id}",
    response_model=ActivityReview,
    summary="One review, addressable on its own",
    responses={
        200: {"description": "The same object the feed carries under its `review` key."},
        404: {"description": "It does not exist or is not visible to this session"},
        503: {"description": "The review store did not answer"},
    },
)
def get_review(
    review_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
):
    try:
        return feed_service.get_review(review_id, viewer_id=session.user_id)
    except (ReviewNotFoundError, ReviewStoreError) as error:
        _error(error)
