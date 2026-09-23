from datetime import datetime
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.dependencies import get_current_session, require_trusted_origin
from app.schemas.activity import ActivityVisit
from app.services import visits as visit_service
from app.services.auth import AuthenticatedSession
from app.services.restaurants import RestaurantNotFoundError

router = APIRouter(prefix="/visits", tags=["visits"])


class VisitCreate(BaseModel):
    restaurant_id: UUID
    # Required on purpose: the default belongs to the form. A default here
    # would turn a forgotten field into an accidental publication.
    visibility: Literal["public", "private"]
    # Absent, the visit happened now.
    occurred_at: datetime | None = None


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, RestaurantNotFoundError | visit_service.VisitNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, visit_service.InvalidVisitError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "occurred_at"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Visit service unavailable",
    )


@router.post(
    "",
    response_model=ActivityVisit,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    summary="Record that the session was at a restaurant",
    responses={
        404: {"description": "No restaurant has this identifier"},
        422: {"description": "Unknown visibility, or a moment in the future or without a zone"},
    },
)
def create(
    payload: VisitCreate,
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> dict:
    try:
        visit = visit_service.create_visit(
            author_id=session.user_id,
            restaurant_id=payload.restaurant_id,
            visibility=payload.visibility,
            occurred_at=payload.occurred_at,
        )
    except (
        RestaurantNotFoundError,
        visit_service.InvalidVisitError,
        visit_service.VisitStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/visits/{visit.id}"
    return visit_service.get_visit(visit.id, viewer_id=session.user_id)


@router.get(
    "/{visit_id}",
    response_model=ActivityVisit,
    summary="One visit, addressable on its own",
    responses={
        404: {"description": "The visit does not exist or is not visible to this session"}
    },
)
def show(
    visit_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> dict:
    try:
        return visit_service.get_visit(visit_id, viewer_id=session.user_id)
    except (visit_service.VisitNotFoundError, visit_service.VisitStoreError) as error:
        _raise_http_error(error)
