from datetime import UTC, datetime, timedelta
from uuid import UUID
import jwt
from argon2 import PasswordHasher
from app.core.config import settings

password_hasher = PasswordHasher()

def hash_password(password):
    return password_hasher.hash(password)

def verify_password(password, password_hash):
    try:
        return password_hasher.verify(password_hash, password)
    except Exception:
        return False

def create_access_token(user_id: UUID):
    return jwt.encode({"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expiration_minutes)}, settings.jwt_secret, algorithm="HS256")
