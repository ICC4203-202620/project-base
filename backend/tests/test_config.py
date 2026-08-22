import pytest
from pydantic import ValidationError

from app.core.config import DEVELOPMENT_JWT_SECRET, Settings


def test_aurora_dsql_requires_endpoint_and_database_user():
    with pytest.raises(ValidationError, match="AURORA_DSQL_ENDPOINT"):
        Settings(database_backend="aurora-dsql")


def test_production_rejects_development_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            environment="production",
            cookie_secure=True,
            jwt_secret=DEVELOPMENT_JWT_SECRET,
        )


def test_production_requires_secure_cookie():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(environment="production", jwt_secret="injected-production-secret")
