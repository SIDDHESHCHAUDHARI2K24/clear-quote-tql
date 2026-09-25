"""Integration error hierarchy.

`IntegrationError` is re-exported (not re-declared) from `app.core.errors`
per spec.md's Decision: every adapter error subclasses CQ-004's real
`IntegrationError`/`AppError` so `register_exception_handlers` turns any of
these into the pinned `{"error": {"code","message","details"}}` shape
without a second, same-named class existing anywhere.
"""

from app.core.errors import IntegrationError
from app.integrations.credit.models import CreditPullType

__all__ = [
    "CreditPullFailedError",
    "IntegrationError",
    "LoanNotFoundError",
    "PricingValidationError",
    "ProviderUnavailableError",
    "RentDataNotFoundError",
    "StrDataNotFoundError",
    "TaxRateNotFoundError",
]


class ProviderUnavailableError(IntegrationError):
    """Raised by any adapter on forced failure or a simulated timeout."""

    code = "PROVIDER_UNAVAILABLE"

    def __init__(self, adapter: str) -> None:
        super().__init__(
            f"Provider unavailable: {adapter}",
            code=self.code,
            details={"adapter": adapter},
        )
        self.adapter = adapter


class PricingValidationError(IntegrationError):
    """Raised by `PricingClient` when required OB fields are missing.

    Overrides `status_code` to 422 (a caller-input problem the LO can fix)
    instead of the inherited 502 (a provider outage).
    """

    code = "PRICING_VALIDATION_ERROR"
    status_code = 422

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(
            f"Cannot price: missing {missing_fields[0]}",
            code=self.code,
            status_code=self.status_code,
            details={"missing_fields": missing_fields},
        )
        self.missing_fields = missing_fields


class LoanNotFoundError(IntegrationError):
    """Raised by `LosClient` when no seeded LOS record matches."""

    code = "LOAN_NOT_FOUND"

    def __init__(self, loan_number: str) -> None:
        super().__init__(
            f"Loan not found: {loan_number}",
            code=self.code,
            details={"loan_number": loan_number},
        )
        self.loan_number = loan_number


class RentDataNotFoundError(IntegrationError):
    """Raised by `RentClient` when no seeded rent comp matches."""

    code = "RENT_DATA_NOT_FOUND"

    def __init__(self, zip_code: str) -> None:
        super().__init__(
            f"Rent data not found: {zip_code}",
            code=self.code,
            details={"zip_code": zip_code},
        )
        self.zip_code = zip_code


class StrDataNotFoundError(IntegrationError):
    """Raised by `StrClient` when no seeded STR comp matches."""

    code = "STR_DATA_NOT_FOUND"

    def __init__(self, zip_code: str) -> None:
        super().__init__(
            f"STR data not found: {zip_code}",
            code=self.code,
            details={"zip_code": zip_code},
        )
        self.zip_code = zip_code


class TaxRateNotFoundError(IntegrationError):
    """Raised by `TaxClient` when no seeded county tax rate matches."""

    code = "TAX_RATE_NOT_FOUND"

    def __init__(self, state: str, county: str) -> None:
        super().__init__(
            f"Tax rate not found: {county}, {state}",
            code=self.code,
            details={"state": state, "county": county},
        )
        self.state = state
        self.county = county


class CreditPullFailedError(IntegrationError):
    """Raised by `CreditClient` when no seeded credit report matches."""

    code = "CREDIT_PULL_FAILED"

    def __init__(self, loan_number: str, pull_type: CreditPullType) -> None:
        super().__init__(
            f"Credit pull failed: {loan_number} ({pull_type.value})",
            code=self.code,
            details={"loan_number": loan_number, "pull_type": pull_type.value},
        )
        self.loan_number = loan_number
        self.pull_type = pull_type
