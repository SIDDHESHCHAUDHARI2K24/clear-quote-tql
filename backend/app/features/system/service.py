"""Backing-service health checks aggregated into a `HealthReport`.

Each `check_*` function returns a `CheckResult` (never raises) named after
the service it checks — `run_health_checks` calls them unqualified (module
globals) so tests can `monkeypatch.setattr(service, "check_valkey", ...)`
to force a failure without touching real infrastructure, then flattens the
results into the pinned `dict[str, str]` shape for `HealthReport.checks`.
"""

import asyncio
from typing import Literal

import boto3
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.config import get_settings
from app.features.system.schemas import CheckResult, HealthReport

TEMPORAL_CONNECT_TIMEOUT_SECONDS = 3.0


def _error(exc: Exception) -> str:
    reason = str(exc) or type(exc).__name__
    return f"error: {reason[:200]}"


async def check_database(session: AsyncSession) -> CheckResult:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        return CheckResult(name="database", status=_error(exc))
    return CheckResult(name="database", status="ok")


async def check_valkey(valkey_url: str) -> CheckResult:
    try:
        client = Redis.from_url(valkey_url)
        try:
            await client.ping()
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="valkey", status=_error(exc))
    return CheckResult(name="valkey", status="ok")


async def check_minio(
    endpoint: str, bucket: str, access_key: str, secret_key: str, region: str
) -> CheckResult:
    def _head_bucket() -> None:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        client.head_bucket(Bucket=bucket)

    try:
        await asyncio.to_thread(_head_bucket)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="minio", status=_error(exc))
    return CheckResult(name="minio", status="ok")


async def check_temporal(address: str, namespace: str) -> CheckResult:
    try:
        client = await asyncio.wait_for(
            Client.connect(address, namespace=namespace),
            timeout=TEMPORAL_CONNECT_TIMEOUT_SECONDS,
        )
        del client
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name="temporal", status=_error(exc))
    return CheckResult(name="temporal", status="ok")


async def run_health_checks(db: AsyncSession) -> HealthReport:
    settings = get_settings()

    results = [
        await check_database(db),
        await check_valkey(settings.valkey_url),
        await check_minio(
            settings.s3_endpoint,
            settings.s3_bucket,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_region,
        ),
        await check_temporal(settings.temporal_address, settings.temporal_namespace),
    ]
    checks = {result.name: result.status for result in results}

    overall: Literal["ok", "degraded"] = (
        "ok" if all(result.status == "ok" for result in results) else "degraded"
    )
    return HealthReport(status=overall, checks=checks)
