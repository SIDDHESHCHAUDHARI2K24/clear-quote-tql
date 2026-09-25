"""`LosClient` Protocol (mock Encompass)."""

from typing import Protocol, runtime_checkable

from app.integrations.los.schemas import LoanFileDTO


@runtime_checkable
class LosClient(Protocol):
    async def get_loan_file(self, loan_number: str) -> LoanFileDTO: ...
