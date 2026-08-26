from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_session
from app.schemas.feed import FeedPage, FeedReview
from app.services import feed as feed_service
from app.services.auth import AuthenticatedSession
from app.services.reviews import ReviewNotFoundError, ReviewStoreError

router = APIRouter(tags=["feed"])


def _error(error: Exception) -> None:
    if isinstance(error, feed_service.InvalidFeedCursorError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        )
    if isinstance(error, ReviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Feed service unavailable"
    )


@router.get("/feed", response_model=FeedPage)
def get_feed(
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
):
    try:
        return feed_service.get_feed(session.user_id, limit=limit, cursor=cursor)
    except (feed_service.InvalidFeedCursorError, ReviewStoreError) as error:
        _error(error)


@router.get("/reviews/{review_id}", response_model=FeedReview)
def get_review(
    review_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
):
    try:
        return feed_service.get_review(review_id, viewer_id=session.user_id)
    except (ReviewNotFoundError, ReviewStoreError) as error:
        _error(error)
