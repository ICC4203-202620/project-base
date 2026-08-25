from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-change-me-change-me"


class DatabaseBackend(StrEnum):
    POSTGRESQL = "postgresql"
    AURORA_DSQL = "aurora-dsql"


class MediaStorageBackend(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = "development"
    database_backend: DatabaseBackend = DatabaseBackend.POSTGRESQL
    database_url: str = "postgresql+psycopg://foodie:foodie@localhost:5432/foodie"
    aurora_dsql_endpoint: str | None = None
    aurora_dsql_user: str | None = None
    aurora_dsql_database: str = "postgres"
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_recycle_seconds: int = Field(default=3300, ge=1, lt=3600)
    jwt_secret: str = DEVELOPMENT_JWT_SECRET
    jwt_expiration_minutes: int = Field(default=10080, ge=1)
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_demo_data: bool = False
    media_storage_backend: MediaStorageBackend = MediaStorageBackend.LOCAL
    media_local_path: Path = Path("var/media")
    media_max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    media_s3_bucket: str | None = None
    media_s3_region: str | None = None
    media_s3_prefix: str = "foodie"
    media_presigned_url_expiration_seconds: int = Field(default=300, ge=1, le=3600)
    model_config = SettingsConfigDict(extra="ignore")

    @field_validator("media_s3_bucket", "media_s3_region", mode="before")
    @classmethod
    def empty_media_setting_is_none(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_deployment_settings(self):
        if self.database_backend is DatabaseBackend.AURORA_DSQL and (
            not self.aurora_dsql_endpoint or not self.aurora_dsql_user
        ):
            raise ValueError(
                "AURORA_DSQL_ENDPOINT and AURORA_DSQL_USER are required "
                "when DATABASE_BACKEND=aurora-dsql"
            )

        if self.media_storage_backend is MediaStorageBackend.S3 and not self.media_s3_bucket:
            raise ValueError("MEDIA_S3_BUCKET is required when MEDIA_STORAGE_BACKEND=s3")

        normalized_prefix = self.media_s3_prefix.strip().strip("/")
        if any(part in {"", ".", ".."} for part in normalized_prefix.split("/")):
            raise ValueError("MEDIA_S3_PREFIX must contain safe path segments")
        self.media_s3_prefix = normalized_prefix

        if self.environment == "production":
            if self.jwt_secret == DEVELOPMENT_JWT_SECRET:
                raise ValueError("JWT_SECRET must be supplied by the production platform")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled in production")
            if self.seed_demo_data:
                raise ValueError("SEED_DEMO_DATA must be disabled in production")

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        ]


settings = Settings()
