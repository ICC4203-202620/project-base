"""The valuation a person makes of a restaurant as a whole.

Distinct from the review of a dish: that one talks about a preparation and
lives attached to a photograph; this one talks about the establishment and
produces the number its page shows to whoever looks at it for the first time.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, insert, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.rating_criteria import RATING_CRITERION_SLUGS
from app.db.retry import run_transaction_with_retry
from app.db.schema import (
    evaluation_photos,
    evaluation_ratings,
    evaluations,
    photos,
    restaurants,
    users,
)
from app.db.session import engine
from app.services.activity import user_summary
from app.services.cursors import decode_time_cursor, encode_time_cursor
from app.services.notifications import notify
from app.services.photos import DISH
from app.services.restaurants import RestaurantNotFoundError
from app.services.visibility import PRIVATE, PUBLIC, VISIBILITIES, visible_to

MINIMUM_RATING = 1
MAXIMUM_RATING = 5


class EvaluationNotFoundError(Exception):
    """No evaluation with this identifier is visible to the viewer."""


class InvalidEvaluationError(Exception):
    """The criteria, the comment, the visibility or the photographs cannot be accepted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class DuplicateEvaluationError(Exception):
    """This person already evaluated this restaurant."""

    def __init__(self, existing_id: UUID | None = None):
        self.existing_id = existing_id
        super().__init__(str(existing_id) if existing_id else "")


class EvaluationStoreError(Exception):
    """The evaluation store could not complete an operation."""


@dataclass(frozen=True)
class CriterionRating:
    criterion: str
    rating: int


@dataclass(frozen=True)
class Evaluation:
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    comment: str
    visibility: str
    ratings: tuple[CriterionRating, ...]
    photo_ids: tuple[UUID, ...]
    created_at: datetime


def _validated_ratings(ratings: Mapping[str, int]) -> tuple[CriterionRating, ...]:
    """Every criterion of the catalogue, exactly once.

    An average computed over a criterion some answered and others skipped
    mixes different populations and cannot be compared between restaurants.
    It is also what makes the overall average equal the average of the
    per-criterion averages.
    """
    missing = set(RATING_CRITERION_SLUGS) - set(ratings)
    unknown = set(ratings) - set(RATING_CRITERION_SLUGS)
    if missing:
        raise InvalidEvaluationError(f"missing criteria: {', '.join(sorted(missing))}")
    if unknown:
        raise InvalidEvaluationError(f"unknown criteria: {', '.join(sorted(unknown))}")
    for slug in RATING_CRITERION_SLUGS:
        rating = ratings[slug]
        if not isinstance(rating, int) or isinstance(rating, bool):
            raise InvalidEvaluationError(f"the rating of {slug} must be a whole number")
        if not MINIMUM_RATING <= rating <= MAXIMUM_RATING:
            raise InvalidEvaluationError(
                f"the rating of {slug} must be between {MINIMUM_RATING} and {MAXIMUM_RATING}"
            )
    return tuple(CriterionRating(slug, ratings[slug]) for slug in RATING_CRITERION_SLUGS)


def _validated_photos(
    connection: Connection,
    photo_ids: Sequence[UUID],
    *,
    author_id: UUID,
    restaurant_id: UUID,
    visibility: str,
) -> None:
    """The photographs have to be the author's own, of this restaurant, and of
    the menu or the premises.

    Associating someone else's photograph would turn an evaluation into a way
    of republishing other people's content. And an evaluation is never more
    visible than the least visible of its photographs, by the same rule that
    governs a review: a public evaluation showing a private photograph would
    exhibit what its author did not share.
    """
    if not photo_ids:
        return
    rows = (
        connection.execute(
            select(
                photos.c.id,
                photos.c.author_id,
                photos.c.restaurant_id,
                photos.c.kind,
                photos.c.visibility,
            ).where(photos.c.id.in_(photo_ids))
        )
        .mappings()
        .all()
    )
    found = {row["id"] for row in rows}
    if found != set(photo_ids):
        raise InvalidEvaluationError("some photographs do not exist")
    for row in rows:
        if row["author_id"] != author_id:
            raise InvalidEvaluationError("a photograph of the evaluation must be your own")
        if row["restaurant_id"] != restaurant_id:
            raise InvalidEvaluationError("a photograph must belong to the restaurant evaluated")
        if row["kind"] == DISH:
            raise InvalidEvaluationError("only menu or venue photographs can be associated")
        if visibility == PUBLIC and row["visibility"] == PRIVATE:
            raise InvalidEvaluationError(
                "an evaluation cannot be more visible than its photographs"
            )


def create_evaluation(
    *,
    author_id: UUID,
    restaurant_id: UUID,
    ratings: Mapping[str, int],
    comment: str,
    visibility: str,
    photo_ids: Sequence[UUID] = (),
) -> Evaluation:
    validated_ratings = _validated_ratings(ratings)
    if visibility not in VISIBILITIES:
        raise InvalidEvaluationError("visibility must be public or private")
    body = comment.strip()
    if not body:
        raise InvalidEvaluationError("an evaluation carries a general comment")
    if len(set(photo_ids)) != len(photo_ids):
        raise InvalidEvaluationError("a photograph cannot be associated twice")

    evaluation_id = uuid4()
    timestamp = datetime.now(UTC)

    def persist(connection: Connection) -> None:
        if not connection.scalar(select(restaurants.c.id).where(restaurants.c.id == restaurant_id)):
            raise RestaurantNotFoundError
        existing = connection.scalar(
            select(evaluations.c.id).where(
                evaluations.c.author_id == author_id,
                evaluations.c.restaurant_id == restaurant_id,
            )
        )
        if existing:
            raise DuplicateEvaluationError(existing)
        _validated_photos(
            connection,
            list(photo_ids),
            author_id=author_id,
            restaurant_id=restaurant_id,
            visibility=visibility,
        )
        connection.execute(
            insert(evaluations).values(
                id=evaluation_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                comment=body,
                visibility=visibility,
                created_at=timestamp,
            )
        )
        connection.execute(
            insert(evaluation_ratings),
            [
                {
                    "evaluation_id": evaluation_id,
                    "criterion": rating.criterion,
                    "rating": rating.rating,
                }
                for rating in validated_ratings
            ],
        )
        if photo_ids:
            connection.execute(
                insert(evaluation_photos),
                [
                    {"evaluation_id": evaluation_id, "photo_id": photo_id}
                    for photo_id in photo_ids
                ],
            )

    try:
        run_transaction_with_retry(engine, persist)
    except (RestaurantNotFoundError, InvalidEvaluationError, DuplicateEvaluationError):
        raise
    except IntegrityError as error:
        # A simultaneous evaluation by the same person won the race.
        raise DuplicateEvaluationError() from error
    except SQLAlchemyError as error:
        raise EvaluationStoreError from error

    notify(
        type="evaluation",
        id=evaluation_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        visibility=visibility,
    )
    return Evaluation(
        id=evaluation_id,
        author_id=author_id,
        restaurant_id=restaurant_id,
        comment=body,
        visibility=visibility,
        ratings=validated_ratings,
        photo_ids=tuple(photo_ids),
        created_at=timestamp,
    )


def restaurant_rating_summary(connection: Connection, restaurant_id: UUID) -> dict:
    """The averages the restaurant page shows.

    It aggregates **public evaluations only, for every observer**, including
    the author of a private one. An average that changed with who is looking
    would not be comparable between restaurants, and its author would see a
    number nobody else sees. Their private evaluation still appears in their
    own profile, which is where the statement places it.
    """
    rows = (
        connection.execute(
            select(
                evaluation_ratings.c.criterion,
                func.avg(evaluation_ratings.c.rating).label("average"),
            )
            .select_from(
                evaluation_ratings.join(
                    evaluations, evaluations.c.id == evaluation_ratings.c.evaluation_id
                )
            )
            .where(
                evaluations.c.restaurant_id == restaurant_id,
                evaluations.c.visibility == PUBLIC,
            )
            .group_by(evaluation_ratings.c.criterion)
        )
        .mappings()
        .all()
    )
    total = connection.scalar(
        select(func.count())
        .select_from(evaluations)
        .where(
            evaluations.c.restaurant_id == restaurant_id,
            evaluations.c.visibility == PUBLIC,
        )
    )
    averages = {row["criterion"]: round(float(row["average"]), 1) for row in rows}
    criteria = tuple(
        (slug, averages[slug]) for slug in RATING_CRITERION_SLUGS if slug in averages
    )
    # Every criterion is mandatory, so this is also the average of every
    # rating: the two definitions coincide, and that is a consequence of the
    # rule above rather than an extra assumption.
    overall = (
        round(sum(average for _, average in criteria) / len(criteria), 1) if criteria else None
    )
    return {"criteria": criteria, "average": overall, "total": total or 0}


def evaluation_statement(viewer_id: UUID):
    """Evaluations the viewer may see, with their author and their restaurant."""
    author = users.alias("evaluation_author")
    return (
        select(
            evaluations.c.id,
            evaluations.c.comment,
            evaluations.c.visibility,
            evaluations.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            author.c.nationality.label("author_nationality"),
            restaurants.c.id.label("restaurant_id"),
            restaurants.c.name.label("restaurant_name"),
            restaurants.c.address.label("restaurant_address"),
        )
        .select_from(
            evaluations.join(author, evaluations.c.author_id == author.c.id).join(
                restaurants, evaluations.c.restaurant_id == restaurants.c.id
            )
        )
        .where(visible_to(evaluations.c.visibility, evaluations.c.author_id, viewer_id))
    )


def load_details(connection: Connection, identifiers: Sequence[UUID]) -> tuple[dict, dict]:
    """Ratings and photographs of several evaluations, in two queries."""
    if not identifiers:
        return {}, {}
    ratings: dict[UUID, list[CriterionRating]] = {}
    for row in connection.execute(
        select(evaluation_ratings)
        .where(evaluation_ratings.c.evaluation_id.in_(identifiers))
        .order_by(evaluation_ratings.c.criterion)
    ).mappings():
        ratings.setdefault(row["evaluation_id"], []).append(
            CriterionRating(row["criterion"], row["rating"])
        )
    associated: dict[UUID, list[UUID]] = {}
    for row in connection.execute(
        select(evaluation_photos)
        .where(evaluation_photos.c.evaluation_id.in_(identifiers))
        .order_by(evaluation_photos.c.photo_id)
    ).mappings():
        associated.setdefault(row["evaluation_id"], []).append(row["photo_id"])
    return ratings, associated


def evaluation_object(row: Mapping, ratings, photo_ids) -> dict:
    return {
        "id": row["id"],
        "comment": row["comment"],
        "visibility": row["visibility"],
        "created_at": row["created_at"],
        "author": user_summary(row),
        "restaurant": {
            "id": row["restaurant_id"],
            "name": row["restaurant_name"],
            "address": row["restaurant_address"],
        },
        "ratings": [
            {"criterion": rating.criterion, "rating": rating.rating} for rating in ratings
        ],
        "photos": [
            {"id": photo_id, "content_url": f"/api/v1/photos/{photo_id}/content"}
            for photo_id in photo_ids
        ],
    }


def get_evaluation(evaluation_id: UUID, *, viewer_id: UUID) -> dict:
    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    evaluation_statement(viewer_id).where(evaluations.c.id == evaluation_id)
                )
                .mappings()
                .first()
            )
            if not row:
                raise EvaluationNotFoundError
            ratings, associated = load_details(connection, [evaluation_id])
    except EvaluationNotFoundError:
        raise
    except SQLAlchemyError as error:
        raise EvaluationStoreError from error
    return evaluation_object(
        row, ratings.get(evaluation_id, []), associated.get(evaluation_id, [])
    )


def list_restaurant_evaluations(
    restaurant_id: UUID, *, limit: int, cursor: str | None = None
) -> dict:
    """The evaluations the page shows, which are exactly the ones it averages.

    Public only, even for the author of a private one: showing them their own
    would leave a list one item longer than the counter on the same screen.
    They read it in their profile.
    """
    statement = evaluation_statement(uuid4()).where(
        evaluations.c.restaurant_id == restaurant_id,
        evaluations.c.visibility == PUBLIC,
    )
    if cursor:
        published_at, evaluation_id = decode_time_cursor(cursor)
        statement = statement.where(
            or_(
                evaluations.c.created_at < published_at,
                and_(
                    evaluations.c.created_at == published_at,
                    evaluations.c.id < evaluation_id,
                ),
            )
        )

    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    statement.order_by(
                        desc(evaluations.c.created_at), desc(evaluations.c.id)
                    ).limit(limit + 1)
                )
                .mappings()
                .all()
            )
            has_next = len(rows) > limit
            rows = rows[:limit]
            ratings, associated = load_details(connection, [row["id"] for row in rows])
    except SQLAlchemyError as error:
        raise EvaluationStoreError from error

    return {
        "items": [
            evaluation_object(row, ratings.get(row["id"], []), associated.get(row["id"], []))
            for row in rows
        ],
        "next_cursor": (
            encode_time_cursor(rows[-1]["created_at"], rows[-1]["id"]) if has_next else None
        ),
    }
