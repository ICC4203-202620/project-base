from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from app.db.schema import metadata, photos, restaurants, reviews
from app.media.storage import LocalMediaLocation, MediaStorageError
from app.services import reviews as review_service


class MemoryStorage:
    def __init__(self, *, fail_store=False):
        self.fail_store = fail_store
        self.stored = []
        self.deleted = []

    def store(self, *, media_id, stream, content_type, extension):
        if self.fail_store:
            raise MediaStorageError
        key = f"photos/{media_id}.{extension}"
        self.stored.append(
            {
                "key": key,
                "contents": stream.read(),
                "content_type": content_type,
            }
        )
        return key

    def delete(self, storage_key):
        self.deleted.append(storage_key)

    def resolve(self, storage_key):
        return LocalMediaLocation(path=storage_key)


def memory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return engine


def png_file() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (2, 2), color="tomato").save(stream, format="PNG")
    stream.seek(0)
    return stream


def insert_restaurant(engine, restaurant_id):
    with engine.begin() as connection:
        connection.execute(
            insert(restaurants).values(
                id=restaurant_id,
                name="Restaurante de prueba",
                normalized_name="restaurante de prueba",
                address="Santiago",
                normalized_address="santiago",
                identity_key="test-identity",
                latitude=-33.4,
                longitude=-70.6,
            )
        )


def test_create_review_stores_validated_image_and_metadata(monkeypatch):
    engine = memory_engine()
    restaurant_id = uuid4()
    author_id = uuid4()
    insert_restaurant(engine, restaurant_id)
    monkeypatch.setattr(review_service, "engine", engine)
    storage = MemoryStorage()

    review = review_service.create_review(
        author_id=author_id,
        restaurant_id=restaurant_id,
        dish_name="Ceviche",
        text="Muy fresco",
        photo_stream=png_file(),
        declared_content_type="image/png",
        storage=storage,
    )

    assert review.author_id == author_id
    assert review.restaurant_id == restaurant_id
    assert review.visibility == "public"
    assert review.photo.content_type == "image/png"
    assert review.photo.content_url == f"/api/v1/photos/{review.photo.id}/content"
    assert storage.stored[0]["key"] == review.photo.storage_key
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(photos)) == 1
        persisted = connection.execute(select(reviews)).mappings().one()
    assert persisted["dish_name"] == "Ceviche"
    assert persisted["photo_id"] == review.photo.id


def test_create_review_rejects_invalid_mime_and_size_before_storage(monkeypatch):
    storage = MemoryStorage()
    with pytest.raises(review_service.InvalidReviewPhotoError):
        review_service.create_review(
            author_id=uuid4(),
            restaurant_id=uuid4(),
            dish_name="Plato",
            text="Texto",
            photo_stream=png_file(),
            declared_content_type="image/jpeg",
            storage=storage,
        )
    assert storage.stored == []

    monkeypatch.setattr(review_service.settings, "media_max_upload_bytes", 1)
    with pytest.raises(review_service.ReviewPhotoTooLargeError):
        review_service.create_review(
            author_id=uuid4(),
            restaurant_id=uuid4(),
            dish_name="Plato",
            text="Texto",
            photo_stream=png_file(),
            declared_content_type="image/png",
            storage=storage,
        )
    assert storage.stored == []


def test_create_review_does_not_persist_when_storage_fails(monkeypatch):
    engine = memory_engine()
    restaurant_id = uuid4()
    insert_restaurant(engine, restaurant_id)
    monkeypatch.setattr(review_service, "engine", engine)

    with pytest.raises(review_service.ReviewMediaError):
        review_service.create_review(
            author_id=uuid4(),
            restaurant_id=restaurant_id,
            dish_name="Plato",
            text="Texto",
            photo_stream=png_file(),
            declared_content_type="image/png",
            storage=MemoryStorage(fail_store=True),
        )

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(reviews)) == 0


def test_create_review_compensates_object_when_relationship_or_database_fails(monkeypatch):
    engine = memory_engine()
    monkeypatch.setattr(review_service, "engine", engine)
    storage = MemoryStorage()

    with pytest.raises(review_service.ReviewNotFoundError):
        review_service.create_review(
            author_id=uuid4(),
            restaurant_id=uuid4(),
            dish_name="Plato",
            text="Texto",
            photo_stream=png_file(),
            declared_content_type="image/png",
            storage=storage,
        )
    assert storage.deleted == [storage.stored[0]["key"]]

    storage = MemoryStorage()
    monkeypatch.setattr(
        review_service,
        "run_transaction_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )
    with pytest.raises(review_service.ReviewStoreError):
        review_service.create_review(
            author_id=uuid4(),
            restaurant_id=uuid4(),
            dish_name="Plato",
            text="Texto",
            photo_stream=png_file(),
            declared_content_type="image/png",
            storage=storage,
        )
    assert storage.deleted == [storage.stored[0]["key"]]


def test_resolve_photo_applies_visibility_and_uses_storage(monkeypatch, tmp_path):
    engine = memory_engine()
    monkeypatch.setattr(review_service, "engine", engine)
    author_id = uuid4()
    other_user_id = uuid4()
    restaurant_id = uuid4()
    photo_id = uuid4()
    review_id = uuid4()
    timestamp = datetime.now(UTC)
    insert_restaurant(engine, restaurant_id)
    with engine.begin() as connection:
        connection.execute(
            insert(photos).values(
                id=photo_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                storage_key="photos/private.png",
                content_type="image/png",
                size_bytes=12,
                created_at=timestamp,
            )
        )
        connection.execute(
            insert(reviews).values(
                id=review_id,
                author_id=author_id,
                restaurant_id=restaurant_id,
                photo_id=photo_id,
                dish_name="Plato",
                text="Texto",
                visibility="private",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    class ResolvingStorage(MemoryStorage):
        def resolve(self, storage_key):
            assert storage_key == "photos/private.png"
            return LocalMediaLocation(path=tmp_path / "private.png")

    storage = ResolvingStorage()
    with pytest.raises(review_service.ReviewNotFoundError):
        review_service.resolve_photo(photo_id, viewer_id=other_user_id, storage=storage)

    photo, location = review_service.resolve_photo(photo_id, viewer_id=author_id, storage=storage)
    assert photo.id == photo_id
    assert location == LocalMediaLocation(path=tmp_path / "private.png")
