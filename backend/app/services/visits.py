"""Check-ins: the record that a person was at a restaurant.

A visit is a row of its own and not a review without text. It carries its own
moment, its own visibility and its own life cycle, and it is the first class of
activity whose moment does not coincide with the instant it was published.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app.db.retry import run_transaction_with_retry
from app.db.schema import restaurants, visits
from app.db.session import engine
from app.services.activity import visit_activity_statement, visit_object
from app.services.restaurants import RestaurantNotFoundError
from app.services.visibility import VISIBILITIES

# A phone with a slightly fast clock should not be told its check-in is in the
# future. Anything beyond this is a reservation, which the project does not do.
FUTURE_TOLERANCE = timedelta(minutes=5)


class VisitNotFoundError(Exception):
    """No visit with this identifier is visible to the viewer."""


class InvalidVisitError(Exception):
    """The moment or the visibility of the visit cannot be accepted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class VisitStoreError(Exception):
    """The visit store could not complete an operation."""


@dataclass(frozen=True)
class Visit:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    occurred_at: datetime
    visibility: str
    created_at: datetime


def _validated_moment(occurred_at: datetime | None, published_at: datetime) -> datetime:
    """When the person says they were there.

    Absent, it is the instant of the request: the usual case is checking in on
    the spot. The past is not restricted, because the statement admits "is or
    was there" and no decision of the system depends on how long ago it was.
    """
    if occurred_at is None:
        return published_at
    if occurred_at.tzinfo is None:
        raise InvalidVisitError("occurred_at must carry a time zone")
    moment = occurred_at.astimezone(UTC)
    if moment > published_at + FUTURE_TOLERANCE:
        raise InvalidVisitError("occurred_at must not be in the future")
    return moment


def create_visit(
    *,
    author_id: UUID,
    restaurant_id: UUID,
    visibility: str,
    occurred_at: datetime | None = None,
) -> Visit:
    # Validated here and not only in the schema, so the rule can be tested
    # without a request.
    if visibility not in VISIBILITIES:
        raise InvalidVisitError("visibility must be public or private")

    published_at = datetime.now(UTC)
    moment = _validated_moment(occurred_at, published_at)
    visit_id = uuid4()

    def persist(connection: Connection) -> None:
        # Checked inside the transaction that writes the row, because there
        # are no foreign keys to lean on: Aurora DSQL does not support them.
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        connection.execute(
            insert(visits).values(
                id=visit_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                occurred_at=moment,
                visibility=visibility,
                created_at=published_at,
            )
        )

    try:
        run_transaction_with_retry(engine, persist)
    except RestaurantNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise VisitStoreError from error

    # No uniqueness constraint: a person visits the same restaurant many times,
    # and that is the normal case rather than a mistake.
    return Visit(
        id=visit_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        occurred_at=moment,
        visibility=visibility,
        created_at=published_at,
    )


def get_visit(visit_id: UUID, *, viewer_id: UUID) -> dict:
    """One visit, in the same shape it has inside the activity envelope.

    Addressable on its own because `notificationclick` and a reloaded deep
    link have to open the view of what was notified.
    """
    statement = visit_activity_statement(viewer_id).where(visits.c.id == visit_id)
    try:
        with engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise VisitStoreError from error
    # Absence and lack of permission are both a 404, as with a review.
    if not row:
        raise VisitNotFoundError
    return visit_object(row)
