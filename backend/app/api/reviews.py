from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from app.api.dependencies import get_current_session, require_trusted_origin
from app.media.storage import (
    LocalMediaLocation,
    MediaStorage,
    RemoteMediaLocation,
    get_media_storage,
)
from app.schemas.reviews import ReviewResponse
from app.services import reviews as review_service
from app.services.auth import AuthenticatedSession

reviews_router = APIRouter(prefix="/reviews", tags=["reviews"])
photos_router = APIRouter(prefix="/photos", tags=["photos"])


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, review_service.ReviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, review_service.ReviewPhotoTooLargeError):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Photo exceeds the configured upload limit",
        )
    if isinstance(error, review_service.InvalidReviewPhotoError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Photo must be a valid JPEG, PNG, or WebP image",
        )
    if isinstance(error, review_service.ReviewMediaError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media service unavailable",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Review service unavailable",
    )


@reviews_router.post(
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
        review_service.InvalidReviewPhotoError,
        review_service.ReviewMediaError,
        review_service.ReviewNotFoundError,
        review_service.ReviewStoreError,
    ) as error:
        _raise_http_error(error)
    response.headers["Location"] = f"/api/v1/reviews/{review.id}"
    return review


@photos_router.get("/{photo_id}/content")
def content(
    photo_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
):
    try:
        photo, location = review_service.resolve_photo(
            photo_id,
            viewer_id=session.user_id,
            storage=storage,
        )
    except (
        review_service.ReviewMediaError,
        review_service.ReviewNotFoundError,
        review_service.ReviewStoreError,
    ) as error:
        _raise_http_error(error)

    headers = {"Cache-Control": "private, max-age=300"}
    if isinstance(location, LocalMediaLocation):
        return FileResponse(
            location.path,
            media_type=photo.content_type,
            headers=headers,
        )
    if isinstance(location, RemoteMediaLocation):
        return RedirectResponse(
            location.url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Cache-Control": "private, no-store"},
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Media service unavailable",
    )
