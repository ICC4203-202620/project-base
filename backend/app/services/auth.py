import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jwt.exceptions import InvalidTokenError
from sqlalchemy import or_, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.countries import normalize_country_code
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.retry import run_transaction_with_retry
from app.db.schema import auth_sessions, users
from app.db.session import engine

# Handles are stored in this form, so uniqueness needs no functional index:
# Aurora DSQL does not support them.
HANDLE_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$")
MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 128


class InvalidCredentialsError(Exception):
    """The supplied login credentials do not identify a user."""


class InvalidSessionError(Exception):
    """The access token does not identify an active session."""


class AuthenticationStoreError(Exception):
    """The session store could not complete an authentication operation."""


class EmailAlreadyRegisteredError(Exception):
    """Another account already uses this email address."""


class HandleAlreadyTakenError(Exception):
    """Another account already uses this handle."""


def normalize_email(value: str) -> str:
    """Return the stored form of an email address."""
    return value.strip().lower()


def normalize_handle(value: str) -> str:
    """Return the stored form of a handle: no leading at sign, lower case.

    The at sign belongs to the interface. Storing it would force every search
    and every comparison to strip it first.
    """
    return value.strip().removeprefix("@").lower()


def is_valid_handle(handle: str) -> bool:
    return bool(HANDLE_PATTERN.fullmatch(handle))


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


def _conflicting_field(connection: Connection, email: str, handle: str) -> str | None:
    """Name the field that already belongs to another account, if any.

    The email wins when both collide with different rows: it is the login
    identity, so it is the one the person has to change first.
    """
    rows = (
        connection.execute(
            select(users.c.email, users.c.handle).where(
                or_(users.c.email == email, users.c.handle == handle)
            )
        )
        .mappings()
        .all()
    )
    if any(row["email"] == email for row in rows):
        return "email"
    return "handle" if rows else None


def _raise_for_conflict(connection: Connection, email: str, handle: str) -> None:
    field = _conflicting_field(connection, email, handle)
    if field == "email":
        raise EmailAlreadyRegisteredError
    if field == "handle":
        raise HandleAlreadyTakenError


def register_user(
    *,
    name: str,
    email: str,
    handle: str,
    nationality: str,
    password: str,
) -> IssuedSession:
    """Create an account and the session that authenticates it right away.

    Registering and then logging in would make the client hold the password in
    memory for a second round trip without buying anything.
    """
    normalized_email = normalize_email(email)
    normalized_handle = normalize_handle(handle)
    normalized_name = name.strip()
    normalized_nationality = normalize_country_code(nationality)

    # Hashing before the transaction keeps the slow work out of it, and makes a
    # rejected registration cost about the same as an accepted one.
    password_hash = hash_password(password)

    user_id = uuid4()
    session_id = uuid4()
    issued_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expiration_minutes)

    def create(connection: Connection) -> None:
        _raise_for_conflict(connection, normalized_email, normalized_handle)
        connection.execute(
            users.insert().values(
                id=user_id,
                email=normalized_email,
                handle=normalized_handle,
                name=normalized_name,
                nationality=normalized_nationality,
                password_hash=password_hash,
                created_at=issued_at,
            )
        )
        connection.execute(
            auth_sessions.insert().values(
                id=session_id,
                user_id=user_id,
                created_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
            )
        )

    try:
        run_transaction_with_retry(engine, create)
    except (EmailAlreadyRegisteredError, HandleAlreadyTakenError):
        raise
    except IntegrityError as error:
        # A concurrent registration won the race. The violated index does not
        # say which field collided, so the store is asked again.
        try:
            with engine.connect() as connection:
                field = _conflicting_field(connection, normalized_email, normalized_handle)
        except SQLAlchemyError:
            field = None
        if field == "email":
            raise EmailAlreadyRegisteredError from error
        if field == "handle":
            raise HandleAlreadyTakenError from error
        raise AuthenticationStoreError from error
    except SQLAlchemyError as error:
        raise AuthenticationStoreError from error

    session = AuthenticatedSession(
        id=session_id,
        user_id=user_id,
        email=normalized_email,
        handle=normalized_handle,
        name=normalized_name,
        expires_at=expires_at,
    )
    return IssuedSession(
        token=create_access_token(
            user_id,
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
