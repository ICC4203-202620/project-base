"""Contrato interno de actividad; no define tablas ni endpoints de suscripciones."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class NotificationEvent:
    type: str
    id: str
    author_id: str
    restaurant_id: str
    recipients: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict) -> NotificationEvent:
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            raise ValueError("Invalid notification event")
        activity_type = payload["type"]
        if not activity_type or len(activity_type) > 64:
            raise ValueError("Invalid activity type")
        recipients = payload.get("recipients")
        if not isinstance(recipients, list):
            raise ValueError("recipients must be a list of user identifiers")
        try:
            activity_id = str(UUID(payload["id"]))
            author_id = str(UUID(payload["author_id"]))
            restaurant_id = str(UUID(payload["restaurant_id"]))
            user_ids = tuple(dict.fromkeys(str(UUID(item)) for item in recipients))
        except KeyError, TypeError, ValueError, AttributeError:
            raise ValueError("Notification identifiers must be UUID strings") from None
        return cls(
            activity_type,
            activity_id,
            author_id,
            restaurant_id,
            tuple(identifier for identifier in user_ids if identifier != author_id),
        )
