from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from jwt.exceptions import InvalidTokenError

from app.core.config import settings

password_hasher = PasswordHasher()
JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    issued_at: datetime
    expires_at: datetime


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def create_access_token(
    user_id: UUID,
    session_id: UUID,
    *,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    issued_at = issued_at or datetime.now(UTC)
    expires_at = expires_at or (issued_at + timedelta(minutes=settings.jwt_expiration_minutes))
    return jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(session_id),
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
    *,
    verify_expiration: bool = True,
) -> AccessTokenClaims:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={
            "require": ["sub", "jti", "iat", "exp"],
            "verify_exp": verify_expiration,
        },
    )

    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["jti"])
        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise InvalidTokenError("Invalid access token claims") from error

    if expires_at <= issued_at:
        raise InvalidTokenError("Access token expiration must follow issuance")

    return AccessTokenClaims(
        user_id=user_id,
        session_id=session_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
