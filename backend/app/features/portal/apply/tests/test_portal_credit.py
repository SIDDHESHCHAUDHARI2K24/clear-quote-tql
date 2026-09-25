"""Mock credit fallback for portal applicants (plan.md decision 12, E14)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import CreditPullFailedError
from app.integrations.credit.mock import MockCreditClient, portal_credit_key
from app.integrations.credit.models import CreditPullType


async def test_portal_key_gets_a_deterministic_report(db_session: AsyncSession) -> None:
    app_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = portal_credit_key(app_id)
    assert key == "PORTAL-123456781234"
    credit = MockCreditClient(db_session)

    soft = await credit.pull_credit(key, CreditPullType.SOFT_PULL)
    assert soft.experian_score is not None and 680 <= soft.experian_score < 800
    assert soft.equifax_score is None and soft.transunion_score is None
    assert soft == await credit.pull_credit(key, CreditPullType.SOFT_PULL)

    hard = await credit.pull_credit(key, CreditPullType.HARD_PULL)
    scores = [hard.experian_score, hard.equifax_score, hard.transunion_score]
    assert all(s is not None and 680 <= s < 800 for s in scores)
    assert hard.middle_score == sorted(s for s in scores if s is not None)[1]
    assert hard.experian_score == soft.experian_score


async def test_unknown_non_portal_key_still_fails(db_session: AsyncSession) -> None:
    with pytest.raises(CreditPullFailedError):
        await MockCreditClient(db_session).pull_credit("LOS-NOPE", CreditPullType.SOFT_PULL)
