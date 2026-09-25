from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.auth import router as auth_router
from app.api.comments import comments_router
from app.api.comments import router as photo_comments_router
from app.api.countries import router as countries_router
from app.api.evaluations import criteria_router
from app.api.evaluations import router as evaluations_router
from app.api.feed import router as feed_router
from app.api.photos import router as photos_router
from app.api.restaurants import cuisine_styles_router
from app.api.restaurants import router as restaurants_router
from app.api.reviews import router as reviews_router
from app.api.users import router as users_router
from app.api.visits import router as visits_router
from app.core.config import settings

app = FastAPI(title="Foodie API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(countries_router, prefix="/api/v1")
app.include_router(evaluations_router, prefix="/api/v1")
app.include_router(criteria_router, prefix="/api/v1")
app.include_router(restaurants_router, prefix="/api/v1")
app.include_router(cuisine_styles_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")
app.include_router(photos_router, prefix="/api/v1")
app.include_router(photo_comments_router, prefix="/api/v1")
app.include_router(comments_router, prefix="/api/v1")
app.include_router(feed_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(visits_router, prefix="/api/v1")


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
