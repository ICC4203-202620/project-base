from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_session
from app.schemas.activity import ActivityPage
from app.schemas.users import ProfileResponse
from app.services import users as user_service
from app.services.auth import AuthenticatedSession
from app.services.cursors import InvalidCursorError

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_session)],
)


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, user_service.UserNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if isinstance(error, InvalidCursorError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="User service unavailable",
    )


@router.get(
    "/{handle}",
    response_model=ProfileResponse,
    summary="Profile of one person, as the session may see it",
    responses={
        200: {
            "description": (
                "The counters and the activity reflect what the viewer may see: "
                "the owner sees their private activity counted, anyone else does not."
            )
        },
        404: {"description": "No account uses this handle"},
    },
)
def show(
    handle: str,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> user_service.Profile:
    try:
        return user_service.get_profile(handle, viewer_id=session.user_id)
    except (user_service.UserNotFoundError, user_service.UserStoreError) as error:
        _raise_http_error(error)


@router.get(
    "/{handle}/activity",
    response_model=ActivityPage,
    summary="Activity of one person, newest first",
    responses={
        200: {
            "description": (
                "Private activity appears only when the viewer is the owner of the profile. "
                "Items are ordered by when the activity happened, not by when it was published."
            )
        },
        404: {"description": "No account uses this handle"},
        422: {"description": "The cursor was not produced by this API"},
    },
)
def activity(
    handle: str,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
) -> dict:
    try:
        return user_service.get_activity(
            handle,
            viewer_id=session.user_id,
            limit=limit,
            cursor=cursor,
        )
    except (
        user_service.UserNotFoundError,
        user_service.UserStoreError,
        InvalidCursorError,
    ) as error:
        _raise_http_error(error)
