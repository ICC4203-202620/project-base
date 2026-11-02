"""Whether a piece of activity is shared with the community or kept private.

The constant lives here and not next to one class of activity because several
share it: reviews, photographs, visits and, as their épicas arrive,
publications and evaluations. A copy per service is a copy that can drift from
the value already written in the database.

`visible_to` is the rule itself, written once. Every table that carries
activity has a visibility and an author, so the rule only needs to be told
which columns those are.
"""

from uuid import UUID

from sqlalchemy import Column, or_

PUBLIC = "public"
PRIVATE = "private"
VISIBILITIES = (PUBLIC, PRIVATE)


def visible_to(visibility: Column, author_id: Column, viewer_id: UUID):
    """Public, or written by whoever is looking."""
    return or_(visibility == PUBLIC, author_id == viewer_id)
