from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.db import seed as seed_module
from app.db.fixtures import (
    CUISINE_STYLES,
    DEMO_USERS,
    PHOTO_FIXTURES,
    RESTAURANT_FOLLOWS,
    RESTAURANTS,
    REVIEW_FIXTURES,
    USER_FOLLOWS,
)
from app.db.schema import (
    cuisine_styles,
    metadata,
    photos,
    restaurant_cuisine_styles,
    restaurant_follows,
    restaurants,
    reviews,
    user_follows,
    users,
)


class FixtureStorage:
    def __init__(self):
        self.stored: list[str] = []
        self.deleted: list[str] = []

    def store(self, *, media_id, stream, content_type, extension):
        assert content_type == "image/webp"
        assert stream.read(4) == b"RIFF"
        key = f"test/photos/{media_id}.{extension}"
        self.stored.append(key)
        return key

    def delete(self, storage_key):
        self.deleted.append(storage_key)


@pytest.fixture(autouse=True)
def fixture_storage(monkeypatch):
    storage = FixtureStorage()
    monkeypatch.setattr(seed_module, "get_media_storage", lambda: storage)
    return storage


def memory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return engine


def assert_feed_fixture_references_exist(connection):
    user_ids = set(connection.scalars(select(users.c.id)))
    restaurant_ids = set(connection.scalars(select(restaurants.c.id)))
    photo_ids = set(connection.scalars(select(photos.c.id)))

    for follower_id, followed_id in connection.execute(
        select(user_follows.c.follower_id, user_follows.c.followed_id)
    ):
        assert follower_id in user_ids
        assert followed_id in user_ids
    for user_id, restaurant_id in connection.execute(
        select(restaurant_follows.c.user_id, restaurant_follows.c.restaurant_id)
    ):
        assert user_id in user_ids
        assert restaurant_id in restaurant_ids
    for author_id, restaurant_id, photo_id in connection.execute(
        select(reviews.c.author_id, reviews.c.restaurant_id, reviews.c.photo_id)
    ):
        assert author_id in user_ids
        assert restaurant_id in restaurant_ids
        assert photo_id in photo_ids
    for author_id, restaurant_id in connection.execute(
        select(photos.c.author_id, photos.c.restaurant_id)
    ):
        assert author_id in user_ids
        assert restaurant_id in restaurant_ids


def test_seed_is_disabled_by_default(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", False)

    assert seed_module.seed() is False
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == 0


def test_seed_creates_all_demo_data_once(monkeypatch, fixture_storage):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")

    assert seed_module.seed() is True
    assert len(fixture_storage.stored) == len(REVIEW_FIXTURES) + len(PHOTO_FIXTURES)
    assert seed_module.seed() is False
    assert len(fixture_storage.stored) == len(REVIEW_FIXTURES) + len(PHOTO_FIXTURES)

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == len(DEMO_USERS)
        assert connection.scalar(select(func.count()).select_from(cuisine_styles)) == len(
            CUISINE_STYLES
        )
        assert connection.scalar(select(func.count()).select_from(restaurants)) == len(RESTAURANTS)
        assert connection.scalar(select(func.count()).select_from(photos)) == len(
            REVIEW_FIXTURES
        ) + len(PHOTO_FIXTURES)
        assert connection.scalar(select(func.count()).select_from(reviews)) == len(REVIEW_FIXTURES)
        assert connection.scalar(select(func.count()).select_from(user_follows)) == len(
            USER_FOLLOWS
        )
        assert connection.scalar(select(func.count()).select_from(restaurant_follows)) == len(
            RESTAURANT_FOLLOWS
        )
        assert connection.scalar(
            select(func.count()).select_from(restaurant_cuisine_styles)
        ) == sum(len(fixture.cuisine_styles) for fixture in RESTAURANTS)
        assert_feed_fixture_references_exist(connection)


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


def test_seed_maps_user_id_and_email_collisions_to_persisted_ids(monkeypatch, fixture_storage):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    hashed_passwords = []
    monkeypatch.setattr(
        seed_module,
        "hash_password",
        lambda password: hashed_passwords.append(password) or "test-password-hash",
    )

    first, second = DEMO_USERS[:2]
    second_persisted_id = uuid4()
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
                id=second_persisted_id,
                email=second.email,
                handle="@existingemail",
                name="Existing email",
                nationality="Chile",
                password_hash="existing",
            )
        )

    assert seed_module.seed() is True
    assert seed_module.seed() is False
    assert len(fixture_storage.stored) == len(REVIEW_FIXTURES) + len(PHOTO_FIXTURES)
    assert hashed_passwords == [DEMO_USERS[2].password]
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
        assert connection.execute(
            select(user_follows.c.follower_id, user_follows.c.followed_id)
        ).one() == (first.id, second_persisted_id)
        followed_review_authors = set(
            connection.scalars(
                select(reviews.c.author_id).where(
                    reviews.c.id.in_((REVIEW_FIXTURES[0].id, REVIEW_FIXTURES[1].id))
                )
            )
        )
        assert followed_review_authors == {second_persisted_id}
        assert_feed_fixture_references_exist(connection)


def test_seed_maps_restaurant_identity_collision_to_persisted_id(monkeypatch, fixture_storage):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")

    fixture = RESTAURANTS[0]
    persisted_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            restaurants.insert().values(
                id=persisted_id,
                name=fixture.name,
                normalized_name=seed_module.normalize_restaurant_text(fixture.name),
                search_name=seed_module.normalize_restaurant_search_text(fixture.name),
                address=fixture.address,
                normalized_address=seed_module.normalize_restaurant_text(fixture.address),
                identity_key=seed_module.restaurant_identity_key(fixture.name, fixture.address),
                latitude=fixture.latitude,
                longitude=fixture.longitude,
            )
        )

    assert seed_module.seed() is True
    assert seed_module.seed() is False
    assert len(fixture_storage.stored) == len(REVIEW_FIXTURES) + len(PHOTO_FIXTURES)
    with engine.connect() as connection:
        assert connection.execute(
            select(restaurant_follows.c.user_id, restaurant_follows.c.restaurant_id)
        ).one() == (DEMO_USERS[0].id, persisted_id)
        mapped_review_restaurants = set(
            connection.scalars(
                select(reviews.c.restaurant_id).where(
                    reviews.c.id.in_(
                        (REVIEW_FIXTURES[0].id, REVIEW_FIXTURES[2].id, REVIEW_FIXTURES[3].id)
                    )
                )
            )
        )
        assert mapped_review_restaurants == {persisted_id}
        assert_feed_fixture_references_exist(connection)


def test_seed_rejects_ambiguous_user_identity(monkeypatch, fixture_storage):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)

    fixture = DEMO_USERS[0]
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            [
                {
                    "id": fixture.id,
                    "email": "uuid-owner@example.com",
                    "handle": "@uuidowner",
                    "name": "UUID owner",
                    "nationality": "Chile",
                    "password_hash": "existing",
                },
                {
                    "id": uuid4(),
                    "email": fixture.email,
                    "handle": "@emailowner",
                    "name": "Email owner",
                    "nationality": "Chile",
                    "password_hash": "existing",
                },
            ],
        )

    with pytest.raises(seed_module.FixtureIdentityConflictError):
        seed_module.seed()
    assert fixture_storage.stored == []
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == 2
        assert connection.scalar(select(func.count()).select_from(reviews)) == 0


def test_seed_rejects_self_follow_before_writing(monkeypatch, fixture_storage):
    engine = memory_engine()
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module.settings, "seed_demo_data", True)
    monkeypatch.setattr(seed_module, "hash_password", lambda password: "test-password-hash")
    monkeypatch.setattr(
        seed_module,
        "USER_FOLLOWS",
        ((DEMO_USERS[0].id, DEMO_USERS[0].id),),
    )

    with pytest.raises(seed_module.FixtureIdentityConflictError, match="self-follow"):
        seed_module.seed()
    assert fixture_storage.stored == []
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == 0
        assert connection.scalar(select(func.count()).select_from(user_follows)) == 0


def test_user_follow_constraints_reject_self_follows_and_duplicates():
    engine = memory_engine()
    first_id = uuid4()
    second_id = uuid4()

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(user_follows.insert().values(follower_id=first_id, followed_id=first_id))

    with engine.begin() as connection:
        connection.execute(
            user_follows.insert().values(follower_id=first_id, followed_id=second_id)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            user_follows.insert().values(follower_id=first_id, followed_id=second_id)
        )
