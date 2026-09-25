"""`MockCreditClient`: reads `provider_credit_reports`.

Soft pull populates `experian_score` only (per catalog: "Soft pull only
pulls Experian") -- that split is baked into the seeded row itself (CQ-010),
not computed here; this mock only returns what's stored.

CQ-032 (plan.md decision 12, phase-p5-p6-plan.md E14): a borrower who
applies through the portal has no LOS loan number and no seeded report.
Their credit key is `portal_credit_key(application_id)` (`PORTAL-...`);
when no seeded row exists for such a key, the mock synthesizes a
deterministic report from the key's SHA-256 (soft pull: Experian only;
hard pull: all three bureaus plus the middle score) instead of failing.
Seeded keys are unaffected.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import CreditPullFailedError, ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.credit.schemas import CreditReportDTO

ADAPTER = "credit"

PORTAL_KEY_PREFIX = "PORTAL-"
_SYNTHETIC_MIN_SCORE = 680
_SYNTHETIC_SCORE_SPAN = 120


def portal_credit_key(application_id: uuid.UUID) -> str:
    """The credit-bureau key for a portal (wizard) application."""
    return f"{PORTAL_KEY_PREFIX}{application_id.hex[:12].upper()}"


def _synthetic_report(loan_number: str, pull_type: CreditPullType) -> CreditReportDTO:
    digest = hashlib.sha256(loan_number.encode("utf-8")).digest()
    scores = [
        _SYNTHETIC_MIN_SCORE + int.from_bytes(digest[i : i + 2], "big") % _SYNTHETIC_SCORE_SPAN
        for i in (0, 2, 4)
    ]
    experian, equifax, transunion = scores
    if pull_type is CreditPullType.SOFT_PULL:
        return CreditReportDTO(
            pull_type=pull_type,
            experian_score=experian,
            equifax_score=None,
            transunion_score=None,
            middle_score=experian,
            tradelines=[],
        )
    return CreditReportDTO(
        pull_type=pull_type,
        experian_score=experian,
        equifax_score=equifax,
        transunion_score=transunion,
        middle_score=sorted(scores)[1],
        tradelines=[],
    )


class MockCreditClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pull_credit(self, loan_number: str, pull_type: CreditPullType) -> CreditReportDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"loan_number": loan_number, "pull_type": pull_type.value}

        if await is_forced_to_fail(ADAPTER):
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="PROVIDER_UNAVAILABLE",
            )
            raise ProviderUnavailableError(ADAPTER)

        record = (
            await self._session.execute(
                select(ProviderCreditReport).where(
                    ProviderCreditReport.loan_number == loan_number,
                    ProviderCreditReport.pull_type == pull_type,
                )
            )
        ).scalar_one_or_none()

        if record is None and loan_number.startswith(PORTAL_KEY_PREFIX):
            await record_call(
                self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
            )
            return _synthetic_report(loan_number, pull_type)

        if record is None:
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="CREDIT_PULL_FAILED",
            )
            raise CreditPullFailedError(loan_number, pull_type)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return CreditReportDTO(
            pull_type=record.pull_type,
            experian_score=record.experian_score,
            equifax_score=record.equifax_score,
            transunion_score=record.transunion_score,
            middle_score=record.middle_score,
            tradelines=record.tradelines,
        )
