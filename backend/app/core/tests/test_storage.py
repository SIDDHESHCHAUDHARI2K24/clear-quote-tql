"""`core/storage` (P5/P6 foundation, E3): a pure unit test against an
in-memory stub client, plus a live round trip against local MinIO (skipped
when MinIO is unreachable)."""

from __future__ import annotations

import io
import uuid
from typing import Any

import httpx
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core import storage


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


class _StubS3:
    """Just enough of boto3's S3 client surface for `core/storage`."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, tuple[bytes, str]]] = {}

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise _client_error("404")

    def create_bucket(self, *, Bucket: str) -> None:
        self.buckets.setdefault(Bucket, {})

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.buckets[Bucket][Key] = (Body, ContentType)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            body, content_type = self.buckets[Bucket][Key]
        except KeyError as exc:
            raise _client_error("NoSuchKey") from exc
        return {"Body": io.BytesIO(body), "ContentType": content_type}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.buckets.get(Bucket, {}).pop(Key, None)

    def generate_presigned_url(
        self, operation: str, *, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        return f"https://stub/{Params['Bucket']}/{Params['Key']}?op={operation}&exp={ExpiresIn}"


async def test_round_trip_with_stub_client() -> None:
    stub = _StubS3()
    await storage.ensure_bucket("docs", client=stub)
    await storage.ensure_bucket("docs", client=stub)  # idempotent
    assert list(stub.buckets) == ["docs"]

    key = await storage.put_object(
        "applications/1/documents/a.pdf",
        b"%PDF-1.4 hi",
        "application/pdf",
        bucket="docs",
        client=stub,
    )
    assert key == "applications/1/documents/a.pdf"

    stored = await storage.get_object(key, bucket="docs", client=stub)
    assert stored.body == b"%PDF-1.4 hi"
    assert stored.content_type == "application/pdf"

    chunks = list(storage.stream_object(key, bucket="docs", client=stub, chunk_size=4))
    assert chunks == [b"%PDF", b"-1.4", b" hi"]

    url = await storage.presigned_get_url(key, expires_in=60, bucket="docs", client=stub)
    assert url == "https://stub/docs/applications/1/documents/a.pdf?op=get_object&exp=60"

    await storage.delete_object(key, bucket="docs", client=stub)
    with pytest.raises(storage.ObjectNotFoundError):
        await storage.get_object(key, bucket="docs", client=stub)
    with pytest.raises(storage.ObjectNotFoundError):
        storage.stream_object(key, bucket="docs", client=stub)


async def test_bucket_defaults_to_settings_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubS3()
    settings = storage.get_settings().model_copy(update={"s3_bucket": "configured-bucket"})
    monkeypatch.setattr(storage, "get_settings", lambda: settings)

    await storage.ensure_bucket(client=stub)
    await storage.put_object("k", b"v", "text/plain", client=stub)
    assert stub.buckets == {"configured-bucket": {"k": (b"v", "text/plain")}}


async def test_ensure_bucket_reraises_non_missing_errors() -> None:
    class _Forbidden(_StubS3):
        def head_bucket(self, *, Bucket: str) -> None:
            raise _client_error("403")

    with pytest.raises(ClientError):
        await storage.ensure_bucket("docs", client=_Forbidden())


def _live_client_or_skip() -> Any:
    client = storage.get_client()
    try:
        client.list_buckets()
    except (EndpointConnectionError, ClientError, OSError) as exc:
        pytest.skip(f"local MinIO unreachable: {exc}")
    return client


async def test_round_trip_against_local_minio() -> None:
    client = _live_client_or_skip()
    bucket = "cq-storage-test"
    key = f"tests/{uuid.uuid4()}.txt"

    await storage.ensure_bucket(bucket, client=client)
    await storage.put_object(key, b"hello minio", "text/plain", bucket=bucket, client=client)
    try:
        stored = await storage.get_object(key, bucket=bucket, client=client)
        assert stored.body == b"hello minio"
        assert stored.content_type == "text/plain"
        assert b"".join(storage.stream_object(key, bucket=bucket, client=client)) == b"hello minio"

        url = await storage.presigned_get_url(key, bucket=bucket, client=client)
        assert key in url and "Signature" in url
        async with httpx.AsyncClient() as http:
            fetched = await http.get(url)
        assert fetched.status_code == 200
        assert fetched.content == b"hello minio"
    finally:
        await storage.delete_object(key, bucket=bucket, client=client)

    with pytest.raises(storage.ObjectNotFoundError):
        await storage.get_object(key, bucket=bucket, client=client)
