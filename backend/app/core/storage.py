"""Object storage (MinIO locally, any S3 API in production).

CQ-020: the send workflow stores each version's pre-approval letter PDF here
and `GET /packages/{id}/letter.pdf` streams it back. boto3 is synchronous, so
every call runs in a worker thread (`asyncio.to_thread`), the same way the
`/health` MinIO check does (`features/system/service.py`).

Module-level functions (not a class) so tests can monkeypatch one call.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings


@lru_cache
def _client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _bucket() -> str:
    return get_settings().s3_bucket


async def put_object(key: str, body: bytes, content_type: str) -> None:
    """Writes `body` at `key` (overwrites: a retried upload of the same
    bytes is a no-op in effect)."""
    await asyncio.to_thread(
        _client().put_object, Bucket=_bucket(), Key=key, Body=body, ContentType=content_type
    )


async def get_object(key: str) -> bytes | None:
    """The object's bytes, or `None` when it doesn't exist."""

    def _get() -> bytes | None:
        try:
            response = _client().get_object(Bucket=_bucket(), Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        body: bytes = response["Body"].read()
        return body

    return await asyncio.to_thread(_get)


async def object_exists(key: str) -> bool:
    def _head() -> bool:
        try:
            _client().head_object(Bucket=_bucket(), Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                return False
            raise
        return True

    return await asyncio.to_thread(_head)
