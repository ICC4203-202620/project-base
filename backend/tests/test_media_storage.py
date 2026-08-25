from io import BytesIO
from uuid import uuid4

import pytest

from app.media.storage import (
    LocalMediaLocation,
    LocalMediaStorage,
    MediaObjectNotFoundError,
    MediaStorageError,
    RemoteMediaLocation,
    S3MediaStorage,
)


class FakeS3Client:
    def __init__(self):
        self.upload = None
        self.deleted = None
        self.presigned = None

    def upload_fileobj(self, stream, bucket, key, ExtraArgs):
        self.upload = {
            "contents": stream.read(),
            "bucket": bucket,
            "key": key,
            "extra_args": ExtraArgs,
        }

    def delete_object(self, *, Bucket, Key):
        self.deleted = {"bucket": Bucket, "key": Key}

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.presigned = {
            "operation": operation,
            "params": Params,
            "expires_in": ExpiresIn,
        }
        return "https://signed.example/photo"


def test_local_storage_atomically_persists_resolves_and_deletes(tmp_path):
    storage = LocalMediaStorage(tmp_path)
    media_id = uuid4()

    key = storage.store(
        media_id=media_id,
        stream=BytesIO(b"image-contents"),
        content_type="image/png",
        extension="png",
    )

    assert key == f"photos/{media_id}.png"
    location = storage.resolve(key)
    assert isinstance(location, LocalMediaLocation)
    assert location.path.read_bytes() == b"image-contents"
    assert list(location.path.parent.glob("*.tmp")) == []

    storage.delete(key)
    with pytest.raises(MediaObjectNotFoundError):
        storage.resolve(key)


def test_local_storage_rejects_keys_outside_its_root(tmp_path):
    storage = LocalMediaStorage(tmp_path)

    with pytest.raises(MediaStorageError, match="Unsafe"):
        storage.resolve("../secret.txt")


def test_s3_storage_uses_private_object_key_and_short_lived_download():
    client = FakeS3Client()
    storage = S3MediaStorage(
        bucket="foodie-private",
        prefix="course/group",
        region="us-east-1",
        presigned_url_expiration_seconds=120,
        client=client,
    )
    media_id = uuid4()

    key = storage.store(
        media_id=media_id,
        stream=BytesIO(b"image-contents"),
        content_type="image/webp",
        extension="webp",
    )

    assert key == f"course/group/photos/{media_id}.webp"
    assert client.upload == {
        "contents": b"image-contents",
        "bucket": "foodie-private",
        "key": key,
        "extra_args": {"ContentType": "image/webp"},
    }
    location = storage.resolve(key)
    assert location == RemoteMediaLocation(url="https://signed.example/photo")
    assert client.presigned == {
        "operation": "get_object",
        "params": {"Bucket": "foodie-private", "Key": key},
        "expires_in": 120,
    }

    storage.delete(key)
    assert client.deleted == {"bucket": "foodie-private", "key": key}
