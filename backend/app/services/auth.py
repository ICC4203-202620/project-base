from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jwt.exceptions import InvalidTokenError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.retry import run_transaction_with_retry
from app.db.schema import auth_sessions, users
from app.db.session import engine


class InvalidCredentialsError(Exception):
    """The supplied login credentials do not identify a user."""


class InvalidSessionError(Exception):
    """The access token does not identify an active session."""


class AuthenticationStoreError(Exception):
    """The session store could not complete an authentication operation."""


@dataclass(frozen=True)
class AuthenticatedSession:
    id: UUID
    user_id: UUID
    email: str
    handle: str
    name: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: AuthenticatedSession


def start_session(email: str, password: str) -> IssuedSession:
    try:
        with engine.connect() as connection:
            user = (
                connection.execute(select(users).where(users.c.email == email)).mappings().first()
            )
    except SQLAlchemyError as error:
        raise AuthenticationStoreError from error

    if not user or not verify_password(password, user["password_hash"]):
        raise InvalidCredentialsError

    issued_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expiration_minutes)
    session_id = uuid4()

    def insert_session(connection):
        connection.execute(
            auth_sessions.insert().values(
                id=session_id,
                user_id=user["id"],
                created_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
            )
        )

    try:
        run_transaction_with_retry(engine, insert_session)
    except SQLAlchemyError as error:
        raise AuthenticationStoreError from error

    session = AuthenticatedSession(
        id=session_id,
        user_id=user["id"],
        email=user["email"],
        handle=user["handle"],
        name=user["name"],
        expires_at=expires_at,
    )
    return IssuedSession(
        token=create_access_token(
            user["id"],
            session_id,
            issued_at=issued_at,
            expires_at=expires_at,
        ),
        session=session,
    )


def authenticate_session(token: str) -> AuthenticatedSession:
    try:
        claims = decode_access_token(token)
    except InvalidTokenError as error:
        raise InvalidSessionError from error

    now = datetime.now(UTC)
    statement = (
        select(
            auth_sessions.c.id,
            auth_sessions.c.user_id,
            auth_sessions.c.expires_at,
            users.c.email,
            users.c.handle,
            users.c.name,
        )
        .select_from(auth_sessions.join(users, auth_sessions.c.user_id == users.c.id))
        .where(
            auth_sessions.c.id == claims.session_id,
            auth_sessions.c.user_id == claims.user_id,
            auth_sessions.c.revoked_at.is_(None),
            auth_sessions.c.expires_at > now,
        )
    )

    try:
        with engine.connect() as connection:
            session = connection.execute(statement).mappings().first()
    except SQLAlchemyError as error:
        raise AuthenticationStoreError from error

    if not session:
        raise InvalidSessionError

    database_expiration = session["expires_at"]
    if database_expiration.tzinfo is None:
        database_expiration = database_expiration.replace(tzinfo=UTC)
    # A signed token may shorten a session but never extend its database lifetime.
    database_expiration = min(database_expiration, claims.expires_at)

    return AuthenticatedSession(
        id=session["id"],
        user_id=session["user_id"],
        email=session["email"],
        handle=session["handle"],
        name=session["name"],
        expires_at=database_expiration,
    )


def revoke_session(token: str | None) -> None:
    if not token:
        return

    try:
        claims = decode_access_token(token, verify_expiration=False)
    except InvalidTokenError:
        return

    revoked_at = datetime.now(UTC)

    def mark_revoked(connection):
        connection.execute(
            update(auth_sessions)
            .where(
                auth_sessions.c.id == claims.session_id,
                auth_sessions.c.user_id == claims.user_id,
                auth_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    try:
        run_transaction_with_retry(engine, mark_revoked)
    except SQLAlchemyError as error:
        raise AuthenticationStoreError from error
