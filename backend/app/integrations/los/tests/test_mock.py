"""AC2: `MockLosClient` conforms to `LosClient` and reads `provider_los_records`."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import LoanNotFoundError
from app.integrations.los.mock import MockLosClient
from app.integrations.los.models import ProviderLosRecord
from app.integrations.los.protocol import LosClient
from app.integrations.los.schemas import LoanFileDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    client: LosClient = MockLosClient(db_session)
    assert isinstance(client, LosClient)


async def test_get_loan_file_returns_seeded_payload(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderLosRecord(
            loan_number="LN-100",
            payload={
                "borrower_full_name": "Kathleen McReynolds",
                "occupancy_type": "Investment_Property",
                "purchase_price": "300000.00",
            },
        )
    )
    await db_session.commit()

    loan_file = await MockLosClient(db_session).get_loan_file("LN-100")

    assert isinstance(loan_file, LoanFileDTO)
    assert loan_file.loan_number == "LN-100"
    assert loan_file.borrower_full_name == "Kathleen McReynolds"
    assert loan_file.occupancy_type == "Investment_Property"
    assert loan_file.purchase_price == 300000


async def test_get_loan_file_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(LoanNotFoundError) as exc_info:
        await MockLosClient(db_session).get_loan_file("DOES-NOT-EXIST")

    assert exc_info.value.loan_number == "DOES-NOT-EXIST"
    assert exc_info.value.code == "LOAN_NOT_FOUND"
    assert exc_info.value.status_code == 502
