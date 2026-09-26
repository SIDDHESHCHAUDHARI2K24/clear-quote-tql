"""Local fixtures for `portal/home/tests`.

Re-exports `make_application` from `portal/reports/tests/conftest.py`
(same technique `portal/actions/tests/conftest.py` uses -- see its
docstring) plus two small factories this item's own tests need: a sent
`QuotePackageVersion` (CQ-031 doesn't care about the snapshot's contents,
only that a row exists and carries a `report_token`) and a pending
`Consent` request.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.portal.reports.tests.conftest import make_application  # noqa: F401
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


@pytest_asyncio.fixture
async def make_sent_version(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[QuotePackageVersion]]:
    async def _make(
        application: Application,
        *,
        version: int = 1,
        superseded: bool = False,
        sent_days_ago: int = 1,
        package: QuotePackage | None = None,
    ) -> QuotePackageVersion:
        if package is None:
            package = QuotePackage(
                application_id=application.id,
                quote_ids=[uuid.uuid4()],
                report_token=secrets.token_urlsafe(24),
            )
            db_session.add(package)
            await db_session.flush()

        sent_at = datetime.now(UTC) - timedelta(days=sent_days_ago)
        row = QuotePackageVersion(
            package_id=package.id,
            version=version,
            snapshot={},
            report_token=secrets.token_urlsafe(24),
            sent_at=sent_at,
            expires_at=sent_at + timedelta(days=21),
            superseded=superseded,
        )
        db_session.add(row)
        await db_session.flush()
        return row

    return _make


@pytest_asyncio.fixture
async def make_pending_consent(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Consent]]:
    async def _make(
        application: Application,
        *,
        expires_in_days: int | None = 14,
        requested_days_ago: int = 0,
    ) -> Consent:
        requested_at = datetime.now(UTC) - timedelta(days=requested_days_ago)
        expires_at = (
            requested_at + timedelta(days=expires_in_days) if expires_in_days is not None else None
        )
        row = Consent(
            application_id=application.id,
            type=ConsentType.HARD_PULL,
            status=ConsentStatus.PENDING,
            requested_at=requested_at,
            expires_at=expires_at,
        )
        db_session.add(row)
        await db_session.flush()
        return row

    return _make
