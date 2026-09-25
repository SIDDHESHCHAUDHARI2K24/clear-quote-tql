"""MinIO/S3 object storage helper (P5/P6 foundation, E3/E13).

One place for every object-store call the app makes: CQ-020's letter PDFs,
CQ-028/CQ-032's document uploads (`applications/{id}/documents/...`) and
CQ-029's outbox attachment stream. Configured from the existing `s3_*`
settings (`S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`S3_REGION`).

boto3 is synchronous, and every caller is an async service, so the public
functions are `async` and run the boto3 call in a worker thread
(`asyncio.to_thread`). The one exception is `stream_object`, which returns a
plain (sync) chunk iterator: FastAPI/Starlette's `StreamingResponse`
iterates a sync iterator in its threadpool, so
`StreamingResponse(stream_object(key), media_type=...)` just works.

Every function takes an optional `bucket` (default: `settings.s3_bucket`)
and an optional `client` (default: one cached boto3 client) so tests can
pass a stub. `seed/generators/documents.py` keeps its own client for the
separate `clearquote-demo-docs` bucket (not refactored; see
docs/backlog/phase-p5-p6-foundation.md decision 11).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings

DEFAULT_CHUNK_SIZE = 64 * 1024
DEFAULT_PRESIGN_SECONDS = 900

_MISSING_CODES = {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}


class ObjectNotFoundError(LookupError):
    """The requested key (or bucket) does not exist."""


@dataclass(frozen=True)
class StoredObject:
    body: bytes
    content_type: str | None


@lru_cache
def _default_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def get_client() -> Any:
    """The shared boto3 S3 client built from the `s3_*` settings."""
    return _default_client()


def _resolve(bucket: str | None, client: Any | None) -> tuple[str, Any]:
    return bucket or get_settings().s3_bucket, client or get_client()


def _is_missing(exc: ClientError) -> bool:
    return str(exc.response.get("Error", {}).get("Code")) in _MISSING_CODES


def _ensure_bucket_sync(bucket: str, client: Any) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if not _is_missing(exc):
            raise
        client.create_bucket(Bucket=bucket)


async def ensure_bucket(bucket: str | None = None, *, client: Any | None = None) -> None:
    """Creates the bucket if it does not exist (idempotent)."""
    name, s3 = _resolve(bucket, client)
    await asyncio.to_thread(_ensure_bucket_sync, name, s3)


async def put_object(
    key: str,
    data: bytes,
    content_type: str,
    *,
    bucket: str | None = None,
    client: Any | None = None,
) -> str:
    """Stores `data` under `key` and returns the key."""
    name, s3 = _resolve(bucket, client)
    await asyncio.to_thread(
        s3.put_object, Bucket=name, Key=key, Body=data, ContentType=content_type
    )
    return key


def _get_object_sync(bucket: str, key: str, client: Any) -> StoredObject:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if _is_missing(exc):
            raise ObjectNotFoundError(key) from exc
        raise
    body = response["Body"]
    try:
        return StoredObject(body=body.read(), content_type=response.get("ContentType"))
    finally:
        body.close()


async def get_object(
    key: str, *, bucket: str | None = None, client: Any | None = None
) -> StoredObject:
    """The whole object in memory. Raises `ObjectNotFoundError` if missing."""
    name, s3 = _resolve(bucket, client)
    return await asyncio.to_thread(_get_object_sync, name, key, s3)


def stream_object(
    key: str,
    *,
    bucket: str | None = None,
    client: Any | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[bytes]:
    """A sync iterator of the object's bytes in `chunk_size` chunks (for
    `StreamingResponse`). The GET is issued eagerly, so a missing key raises
    `ObjectNotFoundError` here, before any response has started."""
    name, s3 = _resolve(bucket, client)
    try:
        response = s3.get_object(Bucket=name, Key=key)
    except ClientError as exc:
        if _is_missing(exc):
            raise ObjectNotFoundError(key) from exc
        raise
    body = response["Body"]

    def _chunks() -> Iterator[bytes]:
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    return _chunks()


async def presigned_get_url(
    key: str,
    *,
    expires_in: int = DEFAULT_PRESIGN_SECONDS,
    bucket: str | None = None,
    client: Any | None = None,
) -> str:
    """A time-limited GET URL for `key` (default 15 minutes)."""
    name, s3 = _resolve(bucket, client)
    url: str = await asyncio.to_thread(
        s3.generate_presigned_url,
        "get_object",
        Params={"Bucket": name, "Key": key},
        ExpiresIn=expires_in,
    )
    return url


async def delete_object(key: str, *, bucket: str | None = None, client: Any | None = None) -> None:
    """Deletes `key` (S3 semantics: deleting a missing key is not an error)."""
    name, s3 = _resolve(bucket, client)
    await asyncio.to_thread(s3.delete_object, Bucket=name, Key=key)
