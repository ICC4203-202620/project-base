"""Lambda de cuentas; incorporar aquí los routers de suscripciones del grupo."""

from mangum import Mangum

from app.api.auth import router as auth_router
from app.api.countries import router as countries_router
from app.api.users import router as users_router
from app.http import create_app

app = create_app("accounts")
for router in (auth_router, countries_router, users_router):
    app.include_router(router, prefix="/api/v1")
# Extensión del grupo: registrar sus endpoints autenticados de suscripciones
# y declarar exactamente las mismas rutas en API Gateway.
handler = Mangum(app, lifespan="off")
