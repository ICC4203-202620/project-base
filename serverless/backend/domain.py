"""Lambda de dominio: consultas y escrituras, sin procesar archivos."""

from mangum import Mangum

from app.api.comments import comments_router
from app.api.comments import router as photo_comments_router
from app.api.evaluations import criteria_router
from app.api.evaluations import router as evaluations_router
from app.api.feed import router as feed_router
from app.api.restaurants import cuisine_styles_router
from app.api.restaurants import router as restaurants_router
from app.api.reviews import router as reviews_router
from app.api.visits import router as visits_router
from app.http import create_app
from app.services.lambda_notifications import install_notifier

app = create_app("domain")
for router in (
    photo_comments_router,
    comments_router,
    criteria_router,
    evaluations_router,
    feed_router,
    cuisine_styles_router,
    restaurants_router,
    reviews_router,
    visits_router,
):
    app.include_router(router, prefix="/api/v1")
install_notifier()
handler = Mangum(app, lifespan="off")
