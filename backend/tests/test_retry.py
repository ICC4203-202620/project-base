from contextlib import nullcontext

import pytest
from sqlalchemy.exc import DBAPIError

from app.db.retry import run_transaction_with_retry


class SerializationFailure(Exception):
    sqlstate = "40001"


class OtherDatabaseFailure(Exception):
    sqlstate = "08006"


class FakeEngine:
    def begin(self):
        return nullcontext(object())


def database_error(original_error):
    return DBAPIError("statement", {}, original_error, False)


def test_transaction_retries_serialization_failure_until_success():
    attempts = 0

    def operation(connection):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise database_error(SerializationFailure())
        return "committed"

    result = run_transaction_with_retry(
        FakeEngine(),
        operation,
        max_attempts=3,
        base_delay_seconds=0,
    )

    assert result == "committed"
    assert attempts == 3


def test_transaction_does_not_retry_other_database_failures():
    attempts = 0

    def operation(connection):
        nonlocal attempts
        attempts += 1
        raise database_error(OtherDatabaseFailure())

    with pytest.raises(DBAPIError):
        run_transaction_with_retry(
            FakeEngine(),
            operation,
            base_delay_seconds=0,
        )

    assert attempts == 1
