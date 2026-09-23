from fastapi.testclient import TestClient

from app.core.countries import COUNTRIES, is_known_country, normalize_country_code
from app.main import app


def test_catalogue_covers_the_officially_assigned_codes():
    codes = [country.code for country in COUNTRIES]

    assert len(codes) == 249
    assert len(set(codes)) == len(codes)
    assert all(len(code) == 2 and code.isupper() for code in codes)
    assert {"CL", "AR", "PE", "ES", "US"} <= set(codes)
    # Not officially assigned by ISO 3166-1, so the selector must not offer them.
    assert not {"XK", "EU", "UK", "ZZ", "AN"} & set(codes)


def test_catalogue_is_ordered_by_name_ignoring_diacritics():
    names = [country.name for country in COUNTRIES]
    assert names.index("Alemania") < names.index("Andorra") < names.index("Argentina")
    assert names.index("Pakistán") < names.index("Perú") < names.index("Polonia")


def test_country_code_is_recognised_however_it_is_typed():
    assert normalize_country_code(" cl ") == "CL"
    assert is_known_country("cl")
    assert not is_known_country("ZZ")


def test_catalogue_is_public_and_cacheable():
    response = TestClient(app).get("/api/v1/countries")

    assert response.status_code == 200
    assert "max-age=" in response.headers["cache-control"]
    payload = response.json()
    assert len(payload) == len(COUNTRIES)
    assert {"code": "CL", "name": "Chile"} in payload
