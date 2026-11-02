"""Invocación síncrona, fuera de la transacción y sin reintentos de envío."""

import json
import logging
from functools import lru_cache

import boto3
from botocore.config import Config

from app.core.config import settings
from app.services.notifications import ActivityNotification, set_notifier

logger = logging.getLogger(__name__)
MAX_RESULT_BYTES = 16 * 1024


@lru_cache
def _client():
    return boto3.client(
        "lambda",
        config=Config(
            connect_timeout=2,
            read_timeout=18,
            retries={"total_max_attempts": 1},
        ),
    )


def invoke_notifications(activity: ActivityNotification) -> None:
    if not settings.notifications_enabled:
        return
    payload = {
        "type": activity.type,
        "id": str(activity.id),
        "author_id": str(activity.author_id),
        "restaurant_id": str(activity.restaurant_id),
        "recipients": [str(identifier) for identifier in activity.recipients],
    }
    try:
        result = _client().invoke(
            FunctionName=settings.notifications_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        stream = result.get("Payload")
        try:
            # No registrar el cuerpo: un emisor del grupo puede incluir datos
            # de una suscripción o información sensible en un error.
            body = stream.read(MAX_RESULT_BYTES + 1) if stream is not None else b"{}"
        finally:
            if stream is not None:
                stream.close()
        if result.get("FunctionError") or result.get("StatusCode") != 200:
            logger.warning("Notification Lambda failed; activity remains saved")
            return
        if len(body) > MAX_RESULT_BYTES:
            logger.warning("Notification Lambda returned an oversized result")
            return
        outcome = json.loads(body)
        if not isinstance(outcome, dict) or outcome.get("status") not in {"ok", "disabled"}:
            logger.warning("Notification emitter did not report a successful delivery attempt")
    except Exception as error:
        # Únicamente el nombre de clase; nunca excepción completa ni payload.
        logger.warning(
            "Notification invocation failed (%s); activity remains saved", type(error).__name__
        )


def install_notifier() -> None:
    # Solo los productores necesitan un destino; el emisor también reutiliza
    # la configuración y el acceso DSQL, pero no invoca otra función emisora.
    if settings.notifications_enabled and not settings.notifications_function_name:
        raise ValueError(
            "NOTIFICATIONS_FUNCTION_NAME is required when notifications are enabled"
        )
    set_notifier(invoke_notifications if settings.notifications_enabled else None)
