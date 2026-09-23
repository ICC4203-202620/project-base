from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app.core.countries import COUNTRIES, Country

router = APIRouter(tags=["countries"])
CACHE_SECONDS = 24 * 60 * 60


class CountryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


@router.get(
    "/countries",
    response_model=list[CountryResponse],
    summary="ISO 3166-1 alpha-2 nationalities, ordered by name",
)
def index(response: Response) -> tuple[Country, ...]:
    # Public: the registration form needs it before there is a session, and the
    # catalogue is the same for everyone and stable between deployments.
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return COUNTRIES
