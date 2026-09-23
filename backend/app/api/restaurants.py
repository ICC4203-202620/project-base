from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_current_session, require_trusted_origin
from app.schemas.restaurants import (
    CuisineStyleResponse,
    RestaurantCreate,
    RestaurantMapResponse,
    RestaurantNearbyResponse,
    RestaurantPage,
    RestaurantResponse,
    RestaurantUpdate,
)
from app.services import restaurants as restaurant_service
from app.services.cursors import InvalidCursorError

router = APIRouter(
    prefix="/restaurants",
    tags=["restaurants"],
    dependencies=[Depends(get_current_session)],
)
cuisine_styles_router = APIRouter(
    prefix="/cuisine-styles",
    tags=["cuisine styles"],
    dependencies=[Depends(get_current_session)],
)


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, restaurant_service.RestaurantNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    if isinstance(error, restaurant_service.DuplicateRestaurantError):
        detail: dict[str, object] = {
            "message": "A restaurant with the same name and address already exists"
        }
        if error.existing:
            # So the interface can take the person to the page that exists
            # instead of leaving them on an error.
            detail["restaurant"] = {"id": str(error.existing.id), "name": error.existing.name}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if isinstance(error, restaurant_service.SearchTermTooShortError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "q"],
                    "msg": (
                        "Search term must be at least "
                        f"{restaurant_service.MINIMUM_SEARCH_LENGTH} characters long"
                    ),
                    "input": None,
                }
            ],
        )
    if isinstance(error, InvalidCursorError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        )
    if isinstance(error, restaurant_service.InvalidNearbySearchError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "radius"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
        )
    if isinstance(error, restaurant_service.InvalidMapBoundsError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "bounds"],
                    "msg": error.reason,
                    "input": None,
                }
            ],
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


@router.get(
    "",
    response_model=RestaurantPage,
    summary="Restaurant collection, optionally narrowed by a term in the name",
    responses={
        200: {
            "description": (
                "Paged by opaque cursor and ordered by name, ignoring case and diacritics. "
                "It answers { items, next_cursor } and no longer a bare array."
            )
        },
        422: {"description": "Term shorter than two characters, or a foreign cursor"},
    },
)
def index(
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> restaurant_service.RestaurantPage:
    try:
        return restaurant_service.list_restaurants(query=q, limit=limit, cursor=cursor)
    except (
        restaurant_service.SearchTermTooShortError,
        restaurant_service.RestaurantStoreError,
        InvalidCursorError,
    ) as error:
        _raise_http_error(error)


@router.get(
    "/map",
    response_model=RestaurantMapResponse,
    summary="Restaurants inside the rectangle a map view reports",
    responses={
        200: {
            "description": (
                "Not paged: a rectangle is a map query, not a list to walk. "
                f"At most {restaurant_service.MAXIMUM_MAP_RESULTS} restaurants come back, and "
                "`truncated` says the rectangle held more, so the interface can ask for a "
                "closer view instead of drawing a partial map as if it were complete."
            )
        },
        422: {
            "description": (
                "Malformed rectangle, coordinates out of range, or an area over "
                f"{restaurant_service.MAXIMUM_MAP_AREA_SQUARE_DEGREES:g} square degrees"
            )
        },
    },
)
def map_bounds(
    south: Annotated[float, Query(ge=-90, le=90)],
    west: Annotated[float, Query(ge=-180, le=180)],
    north: Annotated[float, Query(ge=-90, le=90)],
    east: Annotated[float, Query(ge=-180, le=180)],
    limit: Annotated[int, Query(ge=1, le=restaurant_service.MAXIMUM_MAP_RESULTS)] = (
        restaurant_service.MAXIMUM_MAP_RESULTS
    ),
) -> restaurant_service.RestaurantMapResult:
    try:
        return restaurant_service.restaurants_in_bounds(
            south=south,
            west=west,
            north=north,
            east=east,
            limit=limit,
        )
    except (
        restaurant_service.InvalidMapBoundsError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)


@router.get(
    "/nearby",
    response_model=RestaurantNearbyResponse,
    summary="Restaurants within a radius of a position, by cuisine style",
    responses={
        200: {
            "description": (
                "Ordered by distance ascending, with `distance_m` in metres as measured by the "
                "server. Not paged: the order is a computed distance, and a cursor over it would "
                f"recompute it on every page. At most {restaurant_service.MAXIMUM_MAP_RESULTS} "
                "results come back and `truncated` says the circle held more, so the answer is "
                "to reduce the radius or narrow the style."
            )
        },
        422: {
            "description": (
                "Coordinates out of range, a radius that is not positive or over "
                f"{restaurant_service.MAXIMUM_NEARBY_RADIUS_METRES:g} metres, "
                "or an unknown cuisine style"
            )
        },
    },
)
def nearby(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    radius: Annotated[
        float,
        Query(gt=0, le=restaurant_service.MAXIMUM_NEARBY_RADIUS_METRES, description="In metres"),
    ],
    cuisine_style: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=restaurant_service.MAXIMUM_MAP_RESULTS)] = (
        restaurant_service.MAXIMUM_MAP_RESULTS
    ),
) -> restaurant_service.RestaurantNearbyResult:
    try:
        return restaurant_service.restaurants_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_metres=radius,
            cuisine_style_slugs=cuisine_style or (),
            limit=limit,
        )
    except (
        restaurant_service.InvalidNearbySearchError,
        restaurant_service.UnknownCuisineStylesError,
        restaurant_service.RestaurantStoreError,
    ) as error:
        _raise_http_error(error)


@cuisine_styles_router.get(
    "",
    response_model=list[CuisineStyleResponse],
    summary="Cuisine styles a restaurant may be created with",
)
def cuisine_styles() -> list[restaurant_service.CuisineStyle]:
    try:
        return restaurant_service.list_cuisine_styles()
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
