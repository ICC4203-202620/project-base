from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr

from app.api.dependencies import get_current_session, require_trusted_origin
from app.core.config import settings
from app.services.auth import (
    AuthenticatedSession,
    AuthenticationStoreError,
    InvalidCredentialsError,
    revoke_session,
    start_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE_NAME = "session"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    handle: str
    name: str


class SessionResponse(BaseModel):
    user: SessionUserResponse
    expires_at: datetime


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=max_age,
        expires=expires_at,
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post(
    "/login",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_trusted_origin)],
)
def login(payload: LoginRequest, response: Response) -> None:
    try:
        issued_session = start_session(str(payload.email), payload.password)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from error
    except AuthenticationStoreError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from error

    _set_session_cookie(
        response,
        issued_session.token,
        issued_session.session.expires_at,
    )


@router.get("/session", response_model=SessionResponse)
def current_session(
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> SessionResponse:
    return SessionResponse(
        user=SessionUserResponse(
            id=session.user_id,
            email=session.email,
            handle=session.handle,
            name=session.name,
        ),
        expires_at=session.expires_at,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_trusted_origin)],
)
def logout(request: Request, response: Response) -> None:
    try:
        revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    except AuthenticationStoreError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from error

    _delete_session_cookie(response)
