from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_session, require_trusted_origin
from app.core.rating_criteria import RATING_CRITERIA, RatingCriterion
from app.schemas.evaluations import EvaluationCreate, EvaluationResponse, RatingCriterionResponse
from app.services import evaluations as evaluation_service
from app.services.auth import AuthenticatedSession
from app.services.restaurants import RestaurantNotFoundError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
criteria_router = APIRouter(
    prefix="/rating-criteria",
    tags=["evaluations"],
    dependencies=[Depends(get_current_session)],
)


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(
        error, RestaurantNotFoundError | evaluation_service.EvaluationNotFoundError
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(error, evaluation_service.DuplicateEvaluationError):
        detail: dict[str, object] = {"message": "You already evaluated this restaurant"}
        if error.existing_id:
            detail["evaluation"] = {"id": str(error.existing_id)}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if isinstance(error, evaluation_service.InvalidEvaluationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "ratings"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Evaluation service unavailable",
    )


@criteria_router.get(
    "",
    response_model=list[RatingCriterionResponse],
    summary="Criteria a restaurant is evaluated on",
)
def criteria() -> tuple[RatingCriterion, ...]:
    return RATING_CRITERIA


@router.post(
    "",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    summary="Evaluate a restaurant as a whole",
    responses={
        404: {"description": "No restaurant has this identifier"},
        409: {
            "description": (
                "This person already evaluated this restaurant. The body names the existing "
                "evaluation."
            )
        },
        422: {
            "description": (
                "A missing, repeated or unknown criterion, a rating outside one to five, a "
                "blank comment, or a photograph that is not yours, not of this restaurant, "
                "of a dish, or less visible than the evaluation"
            )
        },
    },
)
def create(
    payload: EvaluationCreate,
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> dict:
    try:
        evaluation = evaluation_service.create_evaluation(
            author_id=session.user_id,
            restaurant_id=payload.restaurant_id,
            ratings=payload.ratings,
            comment=payload.comment,
            visibility=payload.visibility,
            photo_ids=payload.photo_ids,
        )
    except (
        RestaurantNotFoundError,
        evaluation_service.DuplicateEvaluationError,
        evaluation_service.InvalidEvaluationError,
        evaluation_service.EvaluationStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/evaluations/{evaluation.id}"
    return evaluation_service.get_evaluation(evaluation.id, viewer_id=session.user_id)


@router.get(
    "/{evaluation_id}",
    response_model=EvaluationResponse,
    summary="One evaluation, addressable on its own",
    responses={
        404: {"description": "It does not exist or is not visible to this session"}
    },
)
def show(
    evaluation_id: UUID,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> dict:
    try:
        return evaluation_service.get_evaluation(evaluation_id, viewer_id=session.user_id)
    except (
        evaluation_service.EvaluationNotFoundError,
        evaluation_service.EvaluationStoreError,
    ) as error:
        _raise_http_error(error)
