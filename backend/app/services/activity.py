"""The activity envelope shared by the feed and by a user profile.

Every class of activity is published in the same shape: what it is, when it
happened, when it was published, and the object itself under a key named after
its type. A screen renders a list of activity without knowing which classes
exist, and a new class does not reinterpret the existing fields.

Two instants, not one. They coincide for a review, which is published when it
is written, but épica 7 adds the visit, whose moment the user reports and may
lie in the past. A profile is that person's chronology and orders by
`occurred_at`; the feed is what reaches their followers and orders by
`published_at`, so backdating something does not bury it where nobody looks.

This module holds the query and the mapping for reviews, the only class that
exists so far. Each épica that adds a class adds its source here.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import or_, select

from app.db.schema import photos, restaurants, reviews, users
from app.services.cursors import utc_timestamp
from app.services.visibility import PUBLIC

REVIEW_TYPE = "review"


def review_activity_statement(viewer_id):
    """Select reviews the viewer may see, with everything a card needs.

    The visibility rule lives here and not in the caller, so no query can
    forget it: a review is visible when it is public or when the viewer wrote
    it. Callers narrow the result further, by author or by follow.
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


def review_object(row: Mapping[str, Any]) -> dict:
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


def review_activity_item(row: Mapping[str, Any]) -> dict:
    review = review_object(row)
    # A review is published when it is written, so both instants coincide.
    return {
        "type": REVIEW_TYPE,
        "occurred_at": review["created_at"],
        "published_at": review["created_at"],
        REVIEW_TYPE: review,
    }
