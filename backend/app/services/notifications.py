"""Who should hear about an activity, and where each group plugs its sender.

The base code answers the question and stops there. Sending is each group's
Web Push emitter, built in entrega 2, and it lives in the same process, which
is why this is a function and not an endpoint: an endpoint answering "who
should hear about this" would publish the follower graph to anyone with a
session.

The rule of the statement: a public activity notifies whoever follows its
author and whoever follows the restaurant it happened at, excluding the
author; a private one notifies nobody. Somebody who follows both the author
and the restaurant is one recipient, not two.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select

from app.db.schema import restaurant_follows, user_follows, users
from app.db.session import engine
from app.services.visibility import PUBLIC

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivityNotification:
    """One activity worth telling somebody about."""

    type: str
    id: UUID
    author_id: UUID
    restaurant_id: UUID
    # Identifiers of the people to tell, without repetition and without the
    # author. Mapping them to subscriptions is the group's emitter: this
    # module does not know their subscription table and must not.
    recipients: tuple[UUID, ...]


ActivityNotifier = Callable[[ActivityNotification], None]
_notifier: ActivityNotifier | None = None


def set_notifier(notifier: ActivityNotifier | None) -> None:
    """Install the emitter of a group, or remove it.

    This is the single hook. Before épica 14 it lived inside the creation of a
    review, which was fine while a review was the only class of activity;
    with five of them it would have forced every group to repeat their call
    five times and to discover the four new ones on their own.
    """
    global _notifier
    _notifier = notifier


def resolve_recipients(
    *, author_id: UUID, restaurant_id: UUID, visibility: str
) -> tuple[UUID, ...]:
    """Who should hear about an activity with these three properties.

    Author, restaurant and visibility are what every class of activity has, so
    adding a class later changes nothing here.

    The deduplication happens in the query, as one logical union of both
    follow conditions rather than two lists concatenated afterwards, which is
    the same decision the feed already takes for the same reason.
    """
    # Evaluated before asking the store anything: a private activity has no
    # recipients to filter.
    if visibility != PUBLIC:
        return ()

    statement = (
        select(users.c.id)
        .where(
            users.c.id != author_id,
            or_(
                users.c.id.in_(
                    select(user_follows.c.follower_id).where(
                        user_follows.c.followed_id == author_id
                    )
                ),
                users.c.id.in_(
                    select(restaurant_follows.c.user_id).where(
                        restaurant_follows.c.restaurant_id == restaurant_id
                    )
                ),
            ),
        )
        .order_by(users.c.id)
    )
    with engine.connect() as connection:
        return tuple(connection.scalars(statement).all())


def notify(
    *,
    type: str,
    id: UUID,
    author_id: UUID,
    restaurant_id: UUID,
    visibility: str,
) -> None:
    """Tell the installed emitter about an activity that was just published.

    Called after the transaction of the activity commits and never inside it:
    notifying about a write that later rolls back produces warnings about
    content that does not exist, and a transaction retried under Aurora DSQL
    may run its body more than once.

    A failing emitter must not undo an activity that is already written, so
    its failure is logged rather than propagated.
    """
    if _notifier is None:
        return
    try:
        recipients = resolve_recipients(
            author_id=author_id, restaurant_id=restaurant_id, visibility=visibility
        )
        if not recipients:
            return
        _notifier(
            ActivityNotification(
                type=type,
                id=id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                recipients=recipients,
            )
        )
    except Exception:
        # A failing emitter must not undo an activity that is already written.
        logger.exception("Could not notify about %s %s", type, id)
