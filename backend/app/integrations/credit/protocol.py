"""`CreditClient` Protocol (mock credit bureau)."""

from typing import Protocol, runtime_checkable

from app.integrations.credit.models import CreditPullType
from app.integrations.credit.schemas import CreditReportDTO


@runtime_checkable
class CreditClient(Protocol):
    async def pull_credit(self, loan_number: str, pull_type: CreditPullType) -> CreditReportDTO: ...
