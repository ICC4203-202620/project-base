"""Lambda de fotografías: procesamiento de imágenes y objetos privados de S3."""

from mangum import Mangum

from app.api.photos import router
from app.http import create_app
from app.services.lambda_notifications import install_notifier

app = create_app("photos")
app.include_router(router, prefix="/api/v1")
install_notifier()
handler = Mangum(app, lifespan="off")
