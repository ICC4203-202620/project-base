"""Opaque cursors for keyset pagination.

A cursor carries the sort key of the last row a client received, so the next
page resumes from it instead of counting rows. Offset pagination repeats and
skips rows while other people write, and every collection of this API is
written to while it is read.

The value is opaque on purpose: clients must not build one or read one,
because its contents belong to the query that issued it. Base64url keeps it
usable inside a query string.

The key travels as text, which is what every sort key can be written as.
Activity sorts by an instant and uses the `time` pair, which writes that text
as ISO 8601; the restaurant collection sorts by a name and uses the text pair
directly. Both share one envelope, so there is one thing to get right.
"""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID


class InvalidCursorError(Exception):
    """The supplied cursor was not produced by this API."""


def utc_timestamp(value: datetime) -> datetime:
    """Read a timestamp as UTC whether or not the driver kept its zone."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def encode_cursor(sort_key: str, identifier: UUID) -> str:
    value = json.dumps({"k": sort_key, "id": str(identifier)}).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(decoded)
        sort_key = value["k"]
        if not isinstance(sort_key, str):
            raise TypeError
        return sort_key, UUID(value["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise InvalidCursorError from error


def encode_time_cursor(timestamp: datetime, identifier: UUID) -> str:
    return encode_cursor(utc_timestamp(timestamp).isoformat(), identifier)


def decode_time_cursor(cursor: str) -> tuple[datetime, UUID]:
    sort_key, identifier = decode_cursor(cursor)
    try:
        timestamp = datetime.fromisoformat(sort_key)
        if timestamp.tzinfo is None:
            raise ValueError
    except ValueError as error:
        raise InvalidCursorError from error
    return timestamp.astimezone(UTC), identifier
