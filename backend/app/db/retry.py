from collections.abc import Callable
from time import sleep

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

SERIALIZATION_FAILURE_SQLSTATE = "40001"


def is_serialization_failure(error: DBAPIError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
    return sqlstate == SERIALIZATION_FAILURE_SQLSTATE


def run_transaction_with_retry[T](
    engine: Engine,
    operation: Callable[[Connection], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.01,
) -> T:
    """Retry a short, idempotent transaction after SQLSTATE 40001."""
    for attempt in range(max_attempts):
        try:
            with engine.begin() as connection:
                return operation(connection)
        except DBAPIError as error:
            if not is_serialization_failure(error) or attempt == max_attempts - 1:
                raise
            sleep(base_delay_seconds * (2**attempt))

    raise RuntimeError("transaction retry loop ended unexpectedly")
