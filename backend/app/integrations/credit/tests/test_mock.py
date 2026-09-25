"""AC2: `MockCreditClient` conforms to `CreditClient` and reads
`provider_credit_reports`. Soft pull populates `experian_score` only, per
the seeded row (this mock doesn't compute the split itself)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import CreditPullFailedError
from app.integrations.credit.mock import MockCreditClient
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.credit.protocol import CreditClient
from app.integrations.credit.schemas import CreditReportDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockCreditClient(db_session), CreditClient)


async def test_soft_pull_returns_experian_only(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderCreditReport(
            loan_number="LN-CREDIT-1",
            pull_type=CreditPullType.SOFT_PULL,
            experian_score=715,
            equifax_score=None,
            transunion_score=None,
            middle_score=715,
            tradelines=[],
        )
    )
    await db_session.commit()

    result = await MockCreditClient(db_session).pull_credit("LN-CREDIT-1", CreditPullType.SOFT_PULL)

    assert isinstance(result, CreditReportDTO)
    assert result.experian_score == 715
    assert result.equifax_score is None
    assert result.transunion_score is None
    assert result.middle_score == 715


async def test_hard_pull_returns_all_three_scores(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderCreditReport(
            loan_number="LN-CREDIT-2",
            pull_type=CreditPullType.HARD_PULL,
            experian_score=781,
            equifax_score=770,
            transunion_score=765,
            middle_score=770,
            tradelines=[{"creditor": "Chase", "balance": "1200.00"}],
        )
    )
    await db_session.commit()

    result = await MockCreditClient(db_session).pull_credit("LN-CREDIT-2", CreditPullType.HARD_PULL)

    assert result.experian_score == 781
    assert result.equifax_score == 770
    assert result.transunion_score == 765
    assert result.middle_score == 770


async def test_pull_credit_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(CreditPullFailedError) as exc_info:
        await MockCreditClient(db_session).pull_credit("MISSING", CreditPullType.HARD_PULL)

    assert exc_info.value.loan_number == "MISSING"
    assert exc_info.value.pull_type == CreditPullType.HARD_PULL
    assert exc_info.value.code == "CREDIT_PULL_FAILED"
