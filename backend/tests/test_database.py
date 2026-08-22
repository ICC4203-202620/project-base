import sys
from types import SimpleNamespace

from app.core.config import Settings
from app.db.engine import create_database_engine, database_url


def test_postgresql_engine_uses_bounded_recycled_pool():
    config = Settings(
        database_url="postgresql+psycopg://user:password@localhost:5432/database",
        database_pool_size=2,
        database_max_overflow=1,
        database_pool_recycle_seconds=120,
    )

    engine = create_database_engine(config)

    assert engine.pool.size() == 2
    assert engine.pool._max_overflow == 1
    assert engine.pool._recycle == 120
    engine.dispose()


def test_dsql_engine_uses_official_adapter_and_iam_configuration(monkeypatch):
    captured = {}
    expected_engine = object()

    def fake_create_dsql_engine(**kwargs):
        captured.update(kwargs)
        return expected_engine

    monkeypatch.setitem(
        sys.modules,
        "aurora_dsql_sqlalchemy",
        SimpleNamespace(create_dsql_engine=fake_create_dsql_engine),
    )
    config = Settings(
        database_backend="aurora-dsql",
        aurora_dsql_endpoint="example.dsql.us-east-1.on.aws",
        aurora_dsql_user="foodie_app",
        database_pool_size=1,
        database_max_overflow=0,
    )

    engine = create_database_engine(config)

    assert engine is expected_engine
    assert captured == {
        "host": "example.dsql.us-east-1.on.aws",
        "user": "foodie_app",
        "dbname": "postgres",
        "driver": "psycopg",
        "application_name": "foodie-api",
        "pool_pre_ping": True,
        "pool_recycle": 3300,
        "pool_size": 1,
        "max_overflow": 0,
    }
    assert str(database_url(config)) == (
        "auroradsql+psycopg://foodie_app@example.dsql.us-east-1.on.aws/postgres"
    )
