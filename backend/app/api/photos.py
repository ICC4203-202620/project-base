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
from app.schemas.photos import PhotoResponse
from app.services import photos as photo_service
from app.services.auth import AuthenticatedSession
from app.services.restaurants import RestaurantNotFoundError

router = APIRouter(prefix="/photos", tags=["photos"])


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, RestaurantNotFoundError | photo_service.PhotoNotFoundError):
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
    if isinstance(error, photo_service.InvalidPhotoPublicationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "dish_name"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    if isinstance(error, photo_service.UnknownPhotoKindError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "kind"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    if isinstance(error, photo_service.PhotoMediaError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media service unavailable",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Photo service unavailable",
    )


@router.post(
    "",
    response_model=PhotoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    summary="Publish the photograph of a dish, a menu or the premises",
    responses={
        201: {
            "description": (
                "One photograph per request, so the interface can show the progress of each "
                "file and retry only the one that failed. Repeating `upload_group` across the "
                "requests of one act makes those photographs a single entry in the feed, up to "
                f"{photo_service.MAXIMUM_PHOTOS_PER_GROUP} of them."
            )
        },
        404: {"description": "No restaurant has this identifier"},
        413: {"description": "The file exceeds MEDIA_MAX_UPLOAD_BYTES"},
        422: {
            "description": (
                "Not a valid JPEG, PNG or WebP, a declared MIME that does not match the "
                "content, an unknown kind or visibility, a dish name missing on a photograph "
                "of a dish or present on any other, or a group whose photographs disagree"
            )
        },
        503: {"description": "The media provider could not store the object"},
    },
)
def publish(
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
    restaurant_id: Annotated[UUID, Form()],
    visibility: Annotated[str, Form()],
    photo: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = photo_service.DISH,
    dish_name: Annotated[str | None, Form(max_length=120)] = None,
    caption: Annotated[str | None, Form(max_length=500)] = None,
    upload_group: Annotated[UUID | None, Form()] = None,
) -> photo_service.GalleryPhoto:
    try:
        stored = photo_service.store_photo(
            author_id=session.user_id,
            restaurant_id=restaurant_id,
            kind=kind,
            dish_name=dish_name,
            caption=caption,
            visibility=visibility,
            photo_stream=photo.file,
            declared_content_type=photo.content_type,
            storage=storage,
            upload_group=upload_group,
        )
    except (
        RestaurantNotFoundError,
        photo_service.InvalidPhotoError,
        photo_service.InvalidPhotoPublicationError,
        photo_service.PhotoMediaError,
        photo_service.PhotoStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/photos/{stored.id}"
    return photo_service.get_photo(stored.id, viewer_id=session.user_id)


@router.get(
    "/{photo_id}",
    response_model=PhotoResponse,
    summary="Metadata of one photograph",
    responses={
        404: {"description": "The photograph does not exist or is not visible to this session"}
    },
)
def show(
    photo_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> photo_service.GalleryPhoto:
    try:
        return photo_service.get_photo(photo_id, viewer_id=session.user_id)
    except (photo_service.PhotoNotFoundError, photo_service.PhotoStoreError) as error:
        _raise_http_error(error)


@router.get("/{photo_id}/content", summary="The bytes of one photograph")
def content(
    photo_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
):
    try:
        photo, location = photo_service.resolve_photo(
            photo_id,
            viewer_id=session.user_id,
            storage=storage,
        )
    except (
        photo_service.PhotoMediaError,
        photo_service.PhotoNotFoundError,
        photo_service.PhotoStoreError,
    ) as error:
        _raise_http_error(error)

    headers = {"Cache-Control": "private, max-age=300"}
    if isinstance(location, LocalMediaLocation):
        return FileResponse(location.path, media_type=photo.content_type, headers=headers)
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
