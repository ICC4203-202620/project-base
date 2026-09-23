from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.auth import router as auth_router
from app.api.countries import router as countries_router
from app.api.feed import router as feed_router
from app.api.restaurants import router as restaurants_router
from app.api.reviews import photos_router, reviews_router
from app.api.users import router as users_router
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
app.include_router(restaurants_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")
app.include_router(photos_router, prefix="/api/v1")
app.include_router(feed_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
