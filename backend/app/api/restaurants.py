from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_current_session, require_trusted_origin
from app.schemas.restaurants import RestaurantCreate, RestaurantResponse, RestaurantUpdate
from app.services import restaurants as restaurant_service

router = APIRouter(
    prefix="/restaurants",
    tags=["restaurants"],
    dependencies=[Depends(get_current_session)],
)


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, restaurant_service.RestaurantNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    if isinstance(error, restaurant_service.DuplicateRestaurantError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A restaurant with the same name and address already exists",
        )
    if isinstance(error, restaurant_service.UnknownCuisineStylesError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "cuisine_styles"],
                    "msg": f"Unknown cuisine styles: {', '.join(error.slugs)}",
                    "input": list(error.slugs),
                }
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Restaurant service unavailable",
    )


@router.get("", response_model=list[RestaurantResponse])
def index(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[restaurant_service.Restaurant]:
    try:
        return restaurant_service.list_restaurants(limit=limit, offset=offset)
    except restaurant_service.RestaurantStoreError as error:
        _raise_http_error(error)


@router.post(
    "",
    response_model=RestaurantResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
)
def create(payload: RestaurantCreate, response: Response) -> restaurant_service.Restaurant:
    try:
        restaurant = restaurant_service.create_restaurant(
            name=payload.name,
            address=payload.address,
            latitude=payload.latitude,
            longitude=payload.longitude,
            cuisine_style_slugs=payload.cuisine_styles,
        )
    except (
        restaurant_service.DuplicateRestaurantError,
        restaurant_service.UnknownCuisineStylesError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)

    response.headers["Location"] = f"/api/v1/restaurants/{restaurant.id}"
    return restaurant


@router.get("/{restaurant_id}", response_model=RestaurantResponse, name="get_restaurant")
def show(restaurant_id: UUID) -> restaurant_service.Restaurant:
    try:
        return restaurant_service.get_restaurant(restaurant_id)
    except (
        restaurant_service.RestaurantNotFoundError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)


@router.patch(
    "/{restaurant_id}",
    response_model=RestaurantResponse,
    dependencies=[Depends(require_trusted_origin)],
)
def update(restaurant_id: UUID, payload: RestaurantUpdate) -> restaurant_service.Restaurant:
    try:
        return restaurant_service.update_restaurant(
            restaurant_id,
            payload.model_dump(exclude_unset=True),
        )
    except (
        restaurant_service.DuplicateRestaurantError,
        restaurant_service.RestaurantNotFoundError,
        restaurant_service.UnknownCuisineStylesError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)


@router.delete(
    "/{restaurant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_trusted_origin)],
)
def destroy(restaurant_id: UUID) -> None:
    try:
        restaurant_service.delete_restaurant(restaurant_id)
    except (
        restaurant_service.RestaurantNotFoundError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)
