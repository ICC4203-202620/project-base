from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.schema import users
from app.db.session import engine


def seed() -> bool:
    """Create the development user once when explicitly enabled."""
    if not settings.seed_demo_user:
        return False

    with engine.begin() as connection:
        existing_user = connection.scalar(
            select(users.c.id).where(users.c.email == "demo@example.com")
        )
        if existing_user:
            return False

        connection.execute(
            users.insert().values(
                id=uuid4(),
                email="demo@example.com",
                handle="@demo",
                name="Demo Foodie",
                nationality="Chile",
                password_hash=hash_password("demo-password"),
            )
        )
        return True

if __name__ == "__main__":
    seed()
