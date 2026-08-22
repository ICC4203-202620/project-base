from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

RestaurantName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
RestaurantAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
CuisineStyleSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class RestaurantCreate(BaseModel):
    name: RestaurantName
    address: RestaurantAddress
    latitude: Latitude
    longitude: Longitude
    cuisine_styles: Annotated[list[CuisineStyleSlug], Field(min_length=1, max_length=20)]

    @field_validator("cuisine_styles")
    @classmethod
    def require_distinct_cuisine_styles(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("cuisine styles must be unique")
        return value


class RestaurantUpdate(BaseModel):
    name: RestaurantName | None = None
    address: RestaurantAddress | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    cuisine_styles: Annotated[list[CuisineStyleSlug], Field(min_length=1, max_length=20)] | None = (
        None
    )

    @field_validator("cuisine_styles")
    @classmethod
    def require_distinct_cuisine_styles(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("cuisine styles must be unique")
        return value

    @model_validator(mode="after")
    def require_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("fields cannot be null")
        return self


class CuisineStyleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    cuisine_styles: list[CuisineStyleResponse]
    created_at: datetime
    updated_at: datetime
