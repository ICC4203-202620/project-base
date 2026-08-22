from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token


def test_access_token_round_trip_requires_session_and_time_claims():
    user_id = uuid4()
    session_id = uuid4()
    issued_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = issued_at + timedelta(minutes=15)

    token = create_access_token(
        user_id,
        session_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    claims = decode_access_token(token)

    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.issued_at == issued_at
    assert claims.expires_at == expires_at


def test_access_token_rejects_expired_or_incomplete_claims():
    now = datetime.now(UTC).replace(microsecond=0)
    expired_token = create_access_token(
        uuid4(),
        uuid4(),
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(expired_token)

    incomplete_token = jwt.encode(
        {"sub": str(uuid4()), "exp": now + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(incomplete_token)


def test_expired_token_can_be_verified_only_for_idempotent_revocation():
    now = datetime.now(UTC).replace(microsecond=0)
    user_id = uuid4()
    session_id = uuid4()
    token = create_access_token(
        user_id,
        session_id,
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )

    claims = decode_access_token(token, verify_expiration=False)

    assert claims.user_id == user_id
    assert claims.session_id == session_id
