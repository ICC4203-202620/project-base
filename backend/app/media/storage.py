import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO, Protocol
from uuid import UUID

from app.core.config import MediaStorageBackend, Settings, settings

COPY_CHUNK_BYTES = 1024 * 1024


class MediaStorageError(Exception):
    """A media provider could not complete the requested operation."""


class MediaObjectNotFoundError(MediaStorageError):
    """The database references an object that is absent from its provider."""


@dataclass(frozen=True)
class LocalMediaLocation:
    path: Path


@dataclass(frozen=True)
class RemoteMediaLocation:
    url: str


type MediaLocation = LocalMediaLocation | RemoteMediaLocation


class MediaStorage(Protocol):
    def store(
        self,
        *,
        media_id: UUID,
        stream: BinaryIO,
        content_type: str,
        extension: str,
    ) -> str: ...

    def delete(self, storage_key: str) -> None: ...

    def resolve(self, storage_key: str) -> MediaLocation: ...


class LocalMediaStorage:
    def __init__(self, base_path: Path):
        self.base_path = base_path.resolve()

    @staticmethod
    def _key(media_id: UUID, extension: str) -> str:
        return f"photos/{media_id}.{extension}"

    def _path(self, storage_key: str) -> Path:
        path = (self.base_path / storage_key).resolve()
        if not path.is_relative_to(self.base_path):
            raise MediaStorageError("Unsafe local media key")
        return path

    def store(
        self,
        *,
        media_id: UUID,
        stream: BinaryIO,
        content_type: str,
        extension: str,
    ) -> str:
        del content_type
        storage_key = self._key(media_id, extension)
        destination = self._path(storage_key)
        temporary_path: Path | None = None

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stream.seek(0)
            with NamedTemporaryFile(
                mode="wb",
                prefix=f".{media_id}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                while chunk := stream.read(COPY_CHUNK_BYTES):
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
            return storage_key
        except (OSError, ValueError) as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise MediaStorageError("Could not store local media") from error

    def delete(self, storage_key: str) -> None:
        try:
            self._path(storage_key).unlink(missing_ok=True)
        except OSError as error:
            raise MediaStorageError("Could not delete local media") from error

    def resolve(self, storage_key: str) -> LocalMediaLocation:
        path = self._path(storage_key)
        if not path.is_file():
            raise MediaObjectNotFoundError("Local media object not found")
        return LocalMediaLocation(path=path)


class S3MediaStorage:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str | None,
        presigned_url_expiration_seconds: int,
        client=None,
    ):
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix
        self.presigned_url_expiration_seconds = presigned_url_expiration_seconds

    def _key(self, media_id: UUID, extension: str) -> str:
        return f"{self.prefix}/photos/{media_id}.{extension}"

    def store(
        self,
        *,
        media_id: UUID,
        stream: BinaryIO,
        content_type: str,
        extension: str,
    ) -> str:
        storage_key = self._key(media_id, extension)
        try:
            stream.seek(0)
            self.client.upload_fileobj(
                stream,
                self.bucket,
                storage_key,
                ExtraArgs={"ContentType": content_type},
            )
        except Exception as error:
            raise MediaStorageError("Could not store S3 media") from error
        return storage_key

    def delete(self, storage_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=storage_key)
        except Exception as error:
            raise MediaStorageError("Could not delete S3 media") from error

    def resolve(self, storage_key: str) -> RemoteMediaLocation:
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=self.presigned_url_expiration_seconds,
            )
        except Exception as error:
            raise MediaStorageError("Could not resolve S3 media") from error
        return RemoteMediaLocation(url=url)


def create_media_storage(config: Settings) -> MediaStorage:
    if config.media_storage_backend is MediaStorageBackend.LOCAL:
        return LocalMediaStorage(config.media_local_path)
    return S3MediaStorage(
        bucket=config.media_s3_bucket or "",
        prefix=config.media_s3_prefix,
        region=config.media_s3_region,
        presigned_url_expiration_seconds=config.media_presigned_url_expiration_seconds,
    )


@lru_cache
def get_media_storage() -> MediaStorage:
    return create_media_storage(settings)
