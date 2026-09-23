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

from sqlalchemy import Column, literal, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.sql import Select

from app.db.schema import photos, restaurants, reviews, users, visits
from app.services.cursors import utc_timestamp
from app.services.visibility import PUBLIC

REVIEW_TYPE = "review"
VISIT_TYPE = "visit"


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

    def visible(self, viewer_id: UUID):
        """Public, or written by whoever is looking."""
        return or_(self.visibility == PUBLIC, self.author_id == viewer_id)

    def keys(self, viewer_id: UUID) -> Select:
        """The sort keys of this source, already filtered by visibility."""
        return select(
            literal(self.type).label("type"),
            self.occurred_at.label("occurred_at"),
            self.published_at.label("published_at"),
            self.identifier.label("id"),
        ).where(self.visible(viewer_id))


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
            reviews.c.dish_name,
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
