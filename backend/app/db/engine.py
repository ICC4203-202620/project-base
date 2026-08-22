from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from app.core.config import DatabaseBackend, Settings


def database_url(config: Settings) -> str | URL:
    """Return a driver URL suitable for Alembic's offline mode."""
    if config.database_backend is DatabaseBackend.AURORA_DSQL:
        return URL.create(
            "auroradsql+psycopg",
            username=config.aurora_dsql_user,
            host=config.aurora_dsql_endpoint,
            database=config.aurora_dsql_database,
        )
    return config.database_url


def create_database_engine(
    config: Settings,
    *,
    application_name: str = "foodie-api",
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> Engine:
    """Create the configured engine without leaking DSQL details into API code."""
    engine_options = {
        "pool_pre_ping": True,
        "pool_recycle": config.database_pool_recycle_seconds,
        "pool_size": pool_size if pool_size is not None else config.database_pool_size,
        "max_overflow": (
            max_overflow if max_overflow is not None else config.database_max_overflow
        ),
    }

    if config.database_backend is DatabaseBackend.POSTGRESQL:
        return create_engine(
            config.database_url,
            connect_args={"application_name": application_name},
            **engine_options,
        )

    try:
        from aurora_dsql_sqlalchemy import create_dsql_engine
    except ImportError as error:
        raise RuntimeError(
            "Aurora DSQL support is optional; install the backend with the 'aws' extra"
        ) from error

    return create_dsql_engine(
        host=config.aurora_dsql_endpoint,
        user=config.aurora_dsql_user,
        dbname=config.aurora_dsql_database,
        driver="psycopg",
        application_name=application_name,
        **engine_options,
    )
