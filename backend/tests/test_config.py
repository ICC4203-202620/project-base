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


def test_session_expiration_must_be_positive():
    with pytest.raises(ValidationError, match="jwt_expiration_minutes"):
        Settings(jwt_expiration_minutes=0)


def test_production_rejects_demo_seed():
    with pytest.raises(ValidationError, match="SEED_DEMO_DATA"):
        Settings(
            environment="production",
            jwt_secret="injected-production-secret",
            cookie_secure=True,
            seed_demo_data=True,
        )


def test_s3_media_storage_requires_bucket_and_valid_expiration():
    with pytest.raises(ValidationError, match="MEDIA_S3_BUCKET"):
        Settings(media_storage_backend="s3")

    with pytest.raises(ValidationError, match="media_presigned_url_expiration_seconds"):
        Settings(media_presigned_url_expiration_seconds=0)


def test_blank_optional_s3_settings_are_normalized():
    config = Settings(media_s3_bucket="", media_s3_region="")

    assert config.media_s3_bucket is None
    assert config.media_s3_region is None
