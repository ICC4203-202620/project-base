from sqlalchemy import select
from app.core.security import hash_password
from app.db.schema import users
from app.db.session import engine

def seed():
    with engine.begin() as connection:
        if not connection.scalar(select(users.c.id).where(users.c.email == "demo@foodie.local")):
            connection.execute(users.insert().values(email="demo@foodie.local", handle="@demo", name="Demo Foodie", nationality="Chile", password_hash=hash_password("demo-password")))

if __name__ == "__main__":
    seed()
