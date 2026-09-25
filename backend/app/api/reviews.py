from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_session, require_trusted_origin
from app.schemas.reviews import ReviewResponse
from app.services import reviews as review_service
from app.services.auth import AuthenticatedSession

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewCreate(BaseModel):
    # The photograph exists first: publishing it is one action and reviewing
    # it is another.
    photo_id: UUID
    rating: int = Field(ge=review_service.MINIMUM_RATING, le=review_service.MAXIMUM_RATING)
    text: str = Field(min_length=1, max_length=2000)
    # Required, with no default: the default belongs to the form.
    visibility: Literal["public", "private"]


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, review_service.ReviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, review_service.DuplicateReviewError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This photograph already carries a review",
                "review": {"id": str(error.existing_id)},
            },
        )
    if isinstance(error, review_service.InvalidReviewError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "photo_id"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Review service unavailable",
    )


@router.post(
    "",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    summary="Add a review to a photograph of a dish",
    responses={
        201: {
            "description": (
                "The review is written over a photograph that already exists, by whoever took "
                "it, and is never more visible than that photograph."
            )
        },
        404: {"description": "The photograph does not exist or is not visible to this session"},
        409: {
            "description": (
                "The photograph already carries a review. The body names the existing one."
            )
        },
        422: {
            "description": (
                "A photograph of somebody else or not of a dish, a rating outside one to five, "
                "an empty text, or a review more visible than its photograph"
            )
        },
    },
)
def create(
    payload: ReviewCreate,
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> review_service.Review:
    try:
        review = review_service.create_review(
            author_id=session.user_id,
            photo_id=payload.photo_id,
            rating=payload.rating,
            text=payload.text,
            visibility=payload.visibility,
        )
    except (
        review_service.ReviewNotFoundError,
        review_service.DuplicateReviewError,
        review_service.InvalidReviewError,
        review_service.ReviewStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/reviews/{review.id}"
    return review
