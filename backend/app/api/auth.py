from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.api.dependencies import get_current_session, require_trusted_origin
from app.core.config import settings
from app.core.countries import is_known_country, normalize_country_code
from app.services.auth import (
    MAXIMUM_PASSWORD_LENGTH,
    MINIMUM_PASSWORD_LENGTH,
    AuthenticatedSession,
    AuthenticationStoreError,
    EmailAlreadyRegisteredError,
    HandleAlreadyTakenError,
    InvalidCredentialsError,
    is_valid_handle,
    normalize_email,
    normalize_handle,
    register_user,
    revoke_session,
    start_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE_NAME = "session"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    handle: str = Field(min_length=1, max_length=64)
    nationality: str = Field(min_length=1, max_length=80)
    password: str = Field(
        min_length=MINIMUM_PASSWORD_LENGTH,
        max_length=MAXIMUM_PASSWORD_LENGTH,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Name cannot be blank")
        return name

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(str(value))

    @field_validator("handle")
    @classmethod
    def validate_handle(cls, value: str) -> str:
        handle = normalize_handle(value)
        if not is_valid_handle(handle):
            raise ValueError(
                "Handle must be 3 to 30 characters long "
                "and use only lower case letters, digits or underscores"
            )
        return handle

    @field_validator("nationality")
    @classmethod
    def validate_nationality(cls, value: str) -> str:
        code = normalize_country_code(value)
        if not is_known_country(code):
            raise ValueError("Nationality must be an ISO 3166-1 alpha-2 country code")
        return code


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


def _session_response(session: AuthenticatedSession) -> SessionResponse:
    return SessionResponse(
        user=SessionUserResponse(
            id=session.user_id,
            email=session.email,
            handle=session.handle,
            name=session.name,
        ),
        expires_at=session.expires_at,
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


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
    responses={
        409: {
            "description": (
                "The email or the handle already belongs to an account. "
                "The body names the conflicting field so the form can mark it."
            )
        },
        422: {"description": "Malformed field, weak password or unknown country code"},
    },
)
def register(payload: RegisterRequest, response: Response) -> SessionResponse:
    try:
        issued_session = register_user(
            name=payload.name,
            email=str(payload.email),
            handle=payload.handle,
            nationality=payload.nationality,
            password=payload.password,
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "email", "message": "Email already registered"},
        ) from error
    except HandleAlreadyTakenError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "handle", "message": "Handle already taken"},
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
    return _session_response(issued_session.session)


@router.get("/session", response_model=SessionResponse)
def current_session(
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> SessionResponse:
    return _session_response(session)


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
