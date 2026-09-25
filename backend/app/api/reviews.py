from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.dependencies import get_current_session, require_trusted_origin
from app.media.storage import MediaStorage, get_media_storage
from app.schemas.reviews import ReviewResponse
from app.services import photos as photo_service
from app.services import reviews as review_service
from app.services.auth import AuthenticatedSession

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, review_service.ReviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, photo_service.PhotoTooLargeError):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Photo exceeds the configured upload limit",
        )
    if isinstance(error, photo_service.InvalidPhotoError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Photo must be a valid JPEG, PNG, or WebP image",
        )
    if isinstance(error, photo_service.PhotoMediaError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media service unavailable",
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
)
def create(
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
    restaurant_id: Annotated[UUID, Form()],
    dish_name: Annotated[str, Form(min_length=1, max_length=120)],
    text: Annotated[str, Form(min_length=1, max_length=2000)],
    photo: Annotated[UploadFile, File()],
) -> review_service.Review:
    normalized_dish_name = dish_name.strip()
    normalized_text = text.strip()
    if not normalized_dish_name or not normalized_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dish name and text cannot be blank",
        )
    try:
        review = review_service.create_review(
            author_id=session.user_id,
            restaurant_id=restaurant_id,
            dish_name=normalized_dish_name,
            text=normalized_text,
            photo_stream=photo.file,
            declared_content_type=photo.content_type,
            storage=storage,
        )
    except (
        photo_service.InvalidPhotoError,
        photo_service.InvalidPhotoPublicationError,
        photo_service.PhotoMediaError,
        review_service.ReviewNotFoundError,
        review_service.ReviewStoreError,
    ) as error:
        _raise_http_error(error)
    response.headers["Location"] = f"/api/v1/reviews/{review.id}"
    return review
