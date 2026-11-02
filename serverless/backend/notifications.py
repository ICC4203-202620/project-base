"""Punto de integración del emisor Web Push, deliberadamente sin envíos.

El grupo reemplaza este cuerpo por su emisor y consulta sus propias tablas de
suscripciones. No importar FastAPI/Mangum ni registrar una ruta pública.
VAPID_PRIVATE_KEY pertenece exclusivamente a esta función. Todos los envíos
deben concluir antes de retornar, con errores tratados por suscripción.
"""

import logging
import os

from app.notification_event import NotificationEvent

logger = logging.getLogger(__name__)


def handler(event, context):
    del context
    activity = NotificationEvent.from_payload(event)
    enabled = os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() == "true"
    if enabled:
        logger.warning("Web Push emitter is not implemented; no messages were sent")
    return {
        "status": "not_implemented" if enabled else "disabled",
        "recipients": len(activity.recipients),
        "sent": 0,
    }
