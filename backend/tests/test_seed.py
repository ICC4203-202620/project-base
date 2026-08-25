from uuid import uuid4

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.fixtures import CUISINE_STYLES, DEMO_USERS, RESTAURANTS
from app.db.schema import (
    cuisine_styles,
    metadata,
    restaurant_cuisine_styles,
    restaurants,
    users,
)


def memory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return engine


def test_seed_is_disabled_by_default(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", False)

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == 0


def test_seed_creates_all_demo_data_once(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")

    assert seed_module.seed() is True
    assert seed_module.seed() is False

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == len(DEMO_USERS)
        assert connection.scalar(select(func.count()).select_from(cuisine_styles)) == len(
            CUISINE_STYLES
        )
        assert connection.scalar(select(func.count()).select_from(restaurants)) == len(RESTAURANTS)
        assert connection.scalar(
            select(func.count()).select_from(restaurant_cuisine_styles)
        ) == sum(len(fixture.cuisine_styles) for fixture in RESTAURANTS)


def test_seed_does_not_overwrite_modified_fixture(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed()

    fixture = RESTAURANTS[0]
    with engine.begin() as connection:
        connection.execute(
            update(restaurants)
            .where(restaurants.c.id == fixture.id)
            .values(name="Nombre editado por estudiante")
        )

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert (
            connection.scalar(select(restaurants.c.name).where(restaurants.c.id == fixture.id))
            == "Nombre editado por estudiante"
        )


def test_seed_does_not_overwrite_modified_demo_user(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    seed_module.seed()

    fixture = DEMO_USERS[0]
    with engine.begin() as connection:
        connection.execute(
            update(users)
            .where(users.c.id == fixture.id)
            .values(name="Perfil editado por estudiante", password_hash="changed-password-hash")
        )

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert connection.execute(
            select(users.c.name, users.c.password_hash).where(users.c.id == fixture.id)
        ).one() == ("Perfil editado por estudiante", "changed-password-hash")


def test_seed_skips_users_that_collide_by_id_or_email(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    hashed_passwords = []
    monkeypatch.setattr(
        seed_module,
        "hash_password",
        lambda password: hashed_passwords.append(password) or "test-password-hash",
    )

    first, second = DEMO_USERS
    with engine.begin() as connection:
        connection.execute(
            users.insert().values(
                id=first.id,
                email="existing-id@example.com",
                handle="@existingid",
                name="Existing ID",
                nationality="Chile",
                password_hash="existing",
            )
        )
        connection.execute(
            users.insert().values(
                id=uuid4(),
                email=second.email,
                handle="@existingemail",
                name="Existing email",
                nationality="Chile",
                password_hash="existing",
            )
        )

    assert seed_module.seed() is True
    assert hashed_passwords == []
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == len(DEMO_USERS)
        assert (
            connection.scalar(select(users.c.email).where(users.c.id == first.id))
            == "existing-id@example.com"
        )
        assert (
            connection.scalar(select(users.c.handle).where(users.c.email == second.email))
            == "@existingemail"
        )
