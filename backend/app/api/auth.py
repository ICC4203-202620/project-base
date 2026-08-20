from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.schema import users
from app.db.session import engine

router = APIRouter(prefix="/auth", tags=["authentication"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response):
    with engine.connect() as connection:
        user = connection.execute(select(users).where(users.c.email == str(payload.email))).mappings().first()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    response.set_cookie(
        key="session",
        value=create_access_token(user["id"]),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expiration_minutes * 60,
    )
    return response
