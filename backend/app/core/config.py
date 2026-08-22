from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-change-me-change-me"


class DatabaseBackend(StrEnum):
    POSTGRESQL = "postgresql"
    AURORA_DSQL = "aurora-dsql"


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
    seed_demo_user: bool = False
    model_config = SettingsConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_deployment_settings(self):
        if self.database_backend is DatabaseBackend.AURORA_DSQL and (
            not self.aurora_dsql_endpoint or not self.aurora_dsql_user
        ):
            raise ValueError(
                "AURORA_DSQL_ENDPOINT and AURORA_DSQL_USER are required "
                "when DATABASE_BACKEND=aurora-dsql"
            )

        if self.environment == "production":
            if self.jwt_secret == DEVELOPMENT_JWT_SECRET:
                raise ValueError("JWT_SECRET must be supplied by the production platform")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled in production")

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        ]


settings = Settings()
