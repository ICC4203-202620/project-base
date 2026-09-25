"""The activity envelope shared by the feed and by a user profile.

Every class of activity is published in the same shape: what it is, when it
happened, when it was published, and the object itself under a key named after
its type. A screen renders a list of activity without knowing which classes
exist, and a new class does not reinterpret the existing fields.

Two instants, not one. They coincide for a review, which is published when it
is written, but a visit carries a moment the user reports and which may lie in
the past. A profile is that person's chronology and orders by `occurred_at`;
the feed is what reaches their followers and orders by `published_at`, so
backdating something does not bury it where nobody looks, and nobody can date
an activity to push it to the top of someone else's feed.

## Adding a class of activity

An `ActivitySource` describes one table rather than holding a query: which
columns carry its author, its restaurant, its visibility and its two instants,
and how to turn a set of identifiers into envelopes. The feed and the profile
build their own questions from that description, so a new class is one more
entry in `ACTIVITY_SOURCES` and nothing else.

Reading happens in two steps on purpose. First the sort keys of every source
are unioned, ordered and cut in SQL, which is what makes a page cost one
bounded query however many classes exist. Only then are the rows of the
classes that made that page fetched, one query each. Reading full pages from
every source to sort them in Python would multiply the work of each page by
the number of classes.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Column, and_, distinct, func, literal, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Select

from app.db.schema import evaluations, photos, restaurants, reviews, users, visits
from app.services.cursors import utc_timestamp
from app.services.visibility import PUBLIC

REVIEW_TYPE = "review"
VISIT_TYPE = "visit"
PHOTO_TYPE = "photo"
EVALUATION_TYPE = "evaluation"


@dataclass(frozen=True)
class ActivitySource:
    """One class of activity, described so its readers can ask their own questions."""

    type: str
    author_id: Column
    restaurant_id: Column
    visibility: Column
    occurred_at: Column
    published_at: Column
    identifier: Column
    hydrate: Callable[[Connection, UUID, Sequence[UUID]], dict[UUID, dict]]
    # Some rows of a table are not activity on their own: a photograph that
    # already carries a review is published by that review.
    extra_condition: Callable[[], object] | None = None
    # When several rows are one act. Photographs published together share an
    # upload group, and the feed has to show them as one entry.
    grouped_by: Column | None = None

    def _sort_key(self, column: Column):
        """The value a page is ordered by, aggregated when rows form an act."""
        return func.min(column) if self.grouped_by is not None else column

    @property
    def _identity(self) -> Column:
        return self.grouped_by if self.grouped_by is not None else self.identifier

    def after(self, keys: Select, *, by: str, value, identifier: UUID) -> Select:
        """Restrict a page of keys to what comes after a cursor.

        A grouped source compares the aggregated instant, so the restriction
        has to be a HAVING: a WHERE would be applied to the rows before they
        become an act, and would cut the act in the middle.
        """
        column = self._sort_key(self.occurred_at if by == "occurred" else self.published_at)
        condition = or_(
            column < value,
            and_(column == value, self._identity < identifier),
        )
        return keys.having(condition) if self.grouped_by is not None else keys.where(condition)

    def count(self):
        """How many activities this source holds, which is acts and not rows.

        A counter that counted rows would promise more entries than the list
        produces as soon as one act carries several of them.
        """
        return (
            func.count(distinct(self.grouped_by)) if self.grouped_by is not None else func.count()
        )

    def visible(self, viewer_id: UUID):
        """Public, or written by whoever is looking."""
        return or_(self.visibility == PUBLIC, self.author_id == viewer_id)

    def keys(self, viewer_id: UUID) -> Select:
        """The sort keys of this source, already filtered by visibility.

        A grouped source yields one key per act rather than one per row, and
        dates it by its earliest row so the entry does not move in the feed
        while the rest of the group is still arriving.
        """
        if self.grouped_by is None:
            keys = select(
                literal(self.type).label("type"),
                self.occurred_at.label("occurred_at"),
                self.published_at.label("published_at"),
                self.identifier.label("id"),
            )
        else:
            keys = select(
                literal(self.type).label("type"),
                func.min(self.occurred_at).label("occurred_at"),
                func.min(self.published_at).label("published_at"),
                self.grouped_by.label("id"),
            ).group_by(self.grouped_by)
        keys = keys.where(self.visible(viewer_id))
        if self.extra_condition is not None:
            keys = keys.where(self.extra_condition())
        return keys


# --- Reviews -----------------------------------------------------------------


def review_activity_statement(viewer_id: UUID) -> Select:
    """Select reviews the viewer may see, with everything a card needs.

    The visibility rule lives here and not in the caller, so no query can
    forget it. Callers narrow the result further, by author or by follow.
    """
    author = users.alias("author")
    return (
        select(
            reviews.c.id,
            photos.c.dish_name,
            reviews.c.rating,
            reviews.c.text,
            reviews.c.visibility,
            reviews.c.created_at,
            reviews.c.updated_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            restaurants.c.id.label("restaurant_id"),
            restaurants.c.name.label("restaurant_name"),
            restaurants.c.address.label("restaurant_address"),
            photos.c.id.label("photo_id"),
            photos.c.content_type.label("photo_content_type"),
            photos.c.caption.label("photo_caption"),
        )
        .select_from(
            reviews.join(author, reviews.c.author_id == author.c.id)
            .join(restaurants, reviews.c.restaurant_id == restaurants.c.id)
            .join(photos, reviews.c.photo_id == photos.c.id)
        )
        .where(or_(reviews.c.visibility == PUBLIC, reviews.c.author_id == viewer_id))
    )


def review_object(row: Mapping) -> dict:
    created_at = utc_timestamp(row["created_at"])
    return {
        "id": row["id"],
        "dish_name": row["dish_name"],
        "rating": row["rating"],
        "text": row["text"],
        "visibility": row["visibility"],
        "created_at": created_at,
        "updated_at": utc_timestamp(row["updated_at"]),
        "author": {
            "id": row["author_id"],
            "handle": row["author_handle"],
            "name": row["author_name"],
        },
        "restaurant": {
            "id": row["restaurant_id"],
            "name": row["restaurant_name"],
            "address": row["restaurant_address"],
        },
        "photo": {
            "id": row["photo_id"],
            "content_type": row["photo_content_type"],
            "content_url": f"/api/v1/photos/{row['photo_id']}/content",
            "caption": row["photo_caption"],
        },
    }


def review_activity_item(row: Mapping) -> dict:
    review = review_object(row)
    # A review is published when it is written, so both instants coincide.
    return {
        "type": REVIEW_TYPE,
        "occurred_at": review["created_at"],
        "published_at": review["created_at"],
        REVIEW_TYPE: review,
    }


def _hydrate_reviews(
    connection: Connection, viewer_id: UUID, identifiers: Sequence[UUID]
) -> dict[UUID, dict]:
    rows = (
        connection.execute(
            review_activity_statement(viewer_id).where(reviews.c.id.in_(identifiers))
        )
        .mappings()
        .all()
    )
    return {row["id"]: review_activity_item(row) for row in rows}


# --- Visits ------------------------------------------------------------------


def visit_activity_statement(viewer_id: UUID) -> Select:
    author = users.alias("visit_author")
    return (
        select(
            visits.c.id,
            visits.c.occurred_at,
            visits.c.visibility,
            visits.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            restaurants.c.id.label("restaurant_id"),
            restaurants.c.name.label("restaurant_name"),
            restaurants.c.address.label("restaurant_address"),
        )
        .select_from(
            visits.join(author, visits.c.author_id == author.c.id).join(
                restaurants, visits.c.restaurant_id == restaurants.c.id
            )
        )
        .where(or_(visits.c.visibility == PUBLIC, visits.c.author_id == viewer_id))
    )


def visit_object(row: Mapping) -> dict:
    return {
        "id": row["id"],
        "occurred_at": utc_timestamp(row["occurred_at"]),
        "visibility": row["visibility"],
        "created_at": utc_timestamp(row["created_at"]),
        "author": {
            "id": row["author_id"],
            "handle": row["author_handle"],
            "name": row["author_name"],
        },
        "restaurant": {
            "id": row["restaurant_id"],
            "name": row["restaurant_name"],
            "address": row["restaurant_address"],
        },
    }


def visit_activity_item(row: Mapping) -> dict:
    visit = visit_object(row)
    # The moment reported by the person, and the instant it reached the feed.
    return {
        "type": VISIT_TYPE,
        "occurred_at": visit["occurred_at"],
        "published_at": visit["created_at"],
        VISIT_TYPE: visit,
    }


def _hydrate_visits(
    connection: Connection, viewer_id: UUID, identifiers: Sequence[UUID]
) -> dict[UUID, dict]:
    rows = (
        connection.execute(visit_activity_statement(viewer_id).where(visits.c.id.in_(identifiers)))
        .mappings()
        .all()
    )
    return {row["id"]: visit_activity_item(row) for row in rows}


# --- Photographs -------------------------------------------------------------


def photo_activity_statement(viewer_id: UUID) -> Select:
    author = users.alias("photo_activity_author")
    return (
        select(
            photos.c.id,
            photos.c.kind,
            photos.c.visibility,
            photos.c.dish_name,
            photos.c.caption,
            photos.c.content_type,
            photos.c.created_at,
            author.c.id.label("author_id"),
            author.c.handle.label("author_handle"),
            author.c.name.label("author_name"),
            restaurants.c.id.label("restaurant_id"),
            restaurants.c.name.label("restaurant_name"),
            restaurants.c.address.label("restaurant_address"),
        )
        .select_from(
            photos.join(author, photos.c.author_id == author.c.id).join(
                restaurants, photos.c.restaurant_id == restaurants.c.id
            )
        )
        .where(
            or_(photos.c.visibility == PUBLIC, photos.c.author_id == viewer_id),
            _photo_without_review(),
        )
    )


def _photo_without_review():
    """A photograph that already carries a review is not activity of its own.

    The review publishes it, so counting both would show the same photograph
    twice to the same follower.
    """
    return ~select(reviews.c.id).where(reviews.c.photo_id == photos.c.id).exists()


def photo_activity_item(rows: Sequence[Mapping]) -> dict:
    """One act of publishing, which may carry more than one photograph.

    It is a collection from the start even though this épica always publishes
    one: épica 9 publishes several in a single act and presents them as one
    activity, and defining the shape in the singular would force the client to
    change then.
    """
    first = rows[0]
    published_at = utc_timestamp(first["created_at"])
    return {
        "type": PHOTO_TYPE,
        "occurred_at": published_at,
        "published_at": published_at,
        PHOTO_TYPE: {
            "kind": first["kind"],
            "visibility": first["visibility"],
            "author": {
                "id": first["author_id"],
                "handle": first["author_handle"],
                "name": first["author_name"],
            },
            "restaurant": {
                "id": first["restaurant_id"],
                "name": first["restaurant_name"],
                "address": first["restaurant_address"],
            },
            "photos": [
                {
                    "id": row["id"],
                    "content_type": row["content_type"],
                    "content_url": f"/api/v1/photos/{row['id']}/content",
                    "dish_name": row["dish_name"],
                    "caption": row["caption"],
                }
                for row in rows
            ],
        },
    }


PHOTO_ACT = func.coalesce(photos.c.upload_group, photos.c.id)


def _hydrate_photos(
    connection: Connection, viewer_id: UUID, identifiers: Sequence[UUID]
) -> dict[UUID, dict]:
    """One query for every act in the page, not one per photograph."""
    rows = (
        connection.execute(
            photo_activity_statement(viewer_id)
            .add_columns(PHOTO_ACT.label("act"))
            .where(PHOTO_ACT.in_(identifiers))
            .order_by(photos.c.created_at, photos.c.id)
        )
        .mappings()
        .all()
    )
    grouped: dict[UUID, list] = {}
    for row in rows:
        grouped.setdefault(row["act"], []).append(row)
    return {act: photo_activity_item(act_rows) for act, act_rows in grouped.items()}


# --- Evaluations -------------------------------------------------------------


def evaluation_activity_item(row: Mapping, ratings, photo_ids) -> dict:
    from app.services.evaluations import evaluation_object

    evaluation = evaluation_object(row, ratings, photo_ids)
    published_at = utc_timestamp(row["created_at"])
    evaluation["created_at"] = published_at
    return {
        "type": EVALUATION_TYPE,
        "occurred_at": published_at,
        "published_at": published_at,
        EVALUATION_TYPE: evaluation,
    }


def _hydrate_evaluations(
    connection: Connection, viewer_id: UUID, identifiers: Sequence[UUID]
) -> dict[UUID, dict]:
    from app.services.evaluations import evaluation_statement, load_details

    rows = (
        connection.execute(
            evaluation_statement(viewer_id).where(evaluations.c.id.in_(identifiers))
        )
        .mappings()
        .all()
    )
    ratings, associated = load_details(connection, [row["id"] for row in rows])
    return {
        row["id"]: evaluation_activity_item(
            row, ratings.get(row["id"], []), associated.get(row["id"], [])
        )
        for row in rows
    }


# --- The registry ------------------------------------------------------------

ACTIVITY_SOURCES: tuple[ActivitySource, ...] = (
    ActivitySource(
        type=REVIEW_TYPE,
        author_id=reviews.c.author_id,
        restaurant_id=reviews.c.restaurant_id,
        visibility=reviews.c.visibility,
        occurred_at=reviews.c.created_at,
        published_at=reviews.c.created_at,
        identifier=reviews.c.id,
        hydrate=_hydrate_reviews,
    ),
    ActivitySource(
        type=VISIT_TYPE,
        author_id=visits.c.author_id,
        restaurant_id=visits.c.restaurant_id,
        visibility=visits.c.visibility,
        occurred_at=visits.c.occurred_at,
        published_at=visits.c.created_at,
        identifier=visits.c.id,
        hydrate=_hydrate_visits,
    ),
    ActivitySource(
        type=PHOTO_TYPE,
        author_id=photos.c.author_id,
        restaurant_id=photos.c.restaurant_id,
        visibility=photos.c.visibility,
        occurred_at=photos.c.created_at,
        published_at=photos.c.created_at,
        identifier=photos.c.id,
        hydrate=_hydrate_photos,
        extra_condition=_photo_without_review,
        grouped_by=PHOTO_ACT,
    ),
    ActivitySource(
        type=EVALUATION_TYPE,
        author_id=evaluations.c.author_id,
        restaurant_id=evaluations.c.restaurant_id,
        visibility=evaluations.c.visibility,
        occurred_at=evaluations.c.created_at,
        published_at=evaluations.c.created_at,
        identifier=evaluations.c.id,
        hydrate=_hydrate_evaluations,
    ),
)


def hydrate(
    connection: Connection,
    viewer_id: UUID,
    keys: Sequence[Mapping],
) -> list[dict]:
    """Turn a page of sort keys into envelopes, preserving their order.

    One query per class present in the page, never one per row.
    """
    identifiers_by_type: dict[str, list[UUID]] = {}
    for key in keys:
        identifiers_by_type.setdefault(key["type"], []).append(key["id"])

    items_by_type: dict[str, dict[UUID, dict]] = {}
    for source in ACTIVITY_SOURCES:
        identifiers = identifiers_by_type.get(source.type)
        if identifiers:
            items_by_type[source.type] = source.hydrate(connection, viewer_id, identifiers)

    return [
        item
        for key in keys
        if (item := items_by_type.get(key["type"], {}).get(key["id"])) is not None
    ]
