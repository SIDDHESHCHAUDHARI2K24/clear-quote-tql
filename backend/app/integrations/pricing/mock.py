"""`MockPricingClient`: validates OB-required fields, then rate-sheet-prices.

Implements spec.md's "PricingClient rate-sheet algorithm" against
`provider_rate_sheet` (seeded by CQ-010; this item's own tests seed fixture
rows directly).
"""

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.pricing.engine.quote_engine import bucket_for_dscr
from app.integrations.common.errors import PricingValidationError, ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from app.integrations.pricing.schemas import PricedProductDTO, PricingRequestDTO

ADAPTER = "pricing"

ALWAYS_REQUIRED = [
    "LoanPosition",
    "LoanType",
    "LoanPurpose",
    "BaseLoanAmount",
    "TotalLoanAmount",
    "PurchasePrice",
    "AppraisedValue",
    "LTV",
    "CLTV",
    "HCLTV",
    "RepresentativeFICO",
    "Occupancy",
    "PropertyType",
    "NumberOfUnits",
    "State",
    "County",
    "ZipCode",
    "AmortizationType",
    "AmortizationTerm",
    "PrepaymentPenalty",
    "IncomeVerificationType",
    "DesiredLockDays",
]

# Required only when Occupancy == "InvestmentProperty" (spec.md Decision:
# not explicit in the catalog, but implied by "DSCR is the assumed or
# computed value" and ShortTermRental only appearing on investment payloads).
CONDITIONALLY_REQUIRED_INVESTMENT = ["DSCR", "ShortTermRental"]

_PAR_TARGET = Decimal("100.000")
_BUYDOWN_POINTS_LOW = Decimal("0.0075")
_BUYDOWN_POINTS_HIGH = Decimal("0.01")


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _missing_fields(request: PricingRequestDTO) -> list[str]:
    missing = [name for name in ALWAYS_REQUIRED if _is_missing(getattr(request, name))]
    if request.Occupancy == "InvestmentProperty":
        missing.extend(
            name
            for name in CONDITIONALLY_REQUIRED_INVESTMENT
            if _is_missing(getattr(request, name))
        )
    return missing


def _parse_ppp_years(prepayment_penalty: str) -> int:
    """`"5 Years"` -> `5`; `"None"` -> `0` (never matches a real `ppp_years`,
    so a primary-loan request only matches PPP-agnostic (`ppp_years IS
    NULL`) rows, exactly as it should)."""
    if prepayment_penalty.strip().lower() == "none":
        return 0
    digits = "".join(ch for ch in prepayment_penalty if ch.isdigit())
    return int(digits) if digits else 0


class MockPricingClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_priced_products(self, request: PricingRequestDTO) -> list[PricedProductDTO]:
        missing = _missing_fields(request)
        if missing:
            raise PricingValidationError(missing)

        latency_ms = await simulate_latency(ADAPTER)
        request_summary = json.loads(request.model_dump_json(exclude_none=True))

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

        assert request.Occupancy is not None  # narrowed by _missing_fields above
        is_investment = request.Occupancy == "InvestmentProperty"
        program = RateSheetProgram.DSCR if is_investment else RateSheetProgram.CONVENTIONAL

        dscr_bucket_value: str | None = None
        if is_investment:
            assert request.DSCR is not None
            dscr_bucket_value = bucket_for_dscr(request.DSCR).value

        assert request.PrepaymentPenalty is not None
        ppp_years = _parse_ppp_years(request.PrepaymentPenalty)

        assert request.RepresentativeFICO is not None
        assert request.LTV is not None
        conditions = [
            ProviderRateSheet.active.is_(True),
            ProviderRateSheet.program == program,
            ProviderRateSheet.min_fico <= request.RepresentativeFICO,
            ProviderRateSheet.max_ltv >= request.LTV,
            or_(
                ProviderRateSheet.dscr_bucket.is_(None),
                ProviderRateSheet.dscr_bucket == dscr_bucket_value,
            ),
            or_(
                ProviderRateSheet.ppp_years.is_(None),
                ProviderRateSheet.ppp_years == ppp_years,
            ),
            or_(
                ProviderRateSheet.lead_source.is_(None),
                ProviderRateSheet.lead_source == request.LeadSource,
            ),
        ]
        if request.ShortTermRental != "Yes":
            # `NOT str_only OR request.ShortTermRental == "Yes"`: the second
            # half is a plain Python comparison (not row-dependent), so when
            # it's already False the whole OR only survives via the first
            # half -- add it as its own condition instead of an `or_()` with
            # a bare bool literal.
            conditions.append(ProviderRateSheet.str_only.is_(False))

        stmt = select(ProviderRateSheet).where(*conditions)
        rows = (await self._session.execute(stmt)).scalars().all()

        products = self._price_rows(rows, request)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return products

    def _price_rows(
        self, rows: Sequence[ProviderRateSheet], request: PricingRequestDTO
    ) -> list[PricedProductDTO]:
        assert request.TotalLoanAmount is not None
        computed: list[dict[str, Any]] = []
        for row in rows:
            note_rate = row.base_rate + (
                (row.fico_adjustment_bps + row.ltv_adjustment_bps) / Decimal("10000")
            )
            price_pct = row.base_price
            discount_points_pct = ((Decimal("100") - price_pct) / Decimal("100")).quantize(
                Decimal("0.00001")
            )
            discount_points_amount = request.TotalLoanAmount * discount_points_pct
            computed.append(
                {
                    "investor_name": row.investor_name,
                    "product_name": row.product_name,
                    "lock_period_days": row.lock_days,
                    "note_rate": note_rate,
                    "price_pct": price_pct,
                    "discount_points_pct": discount_points_pct,
                    "discount_points_amount": discount_points_amount,
                    "is_par_rate": False,
                    "is_buydown_rate": False,
                }
            )

        if computed:
            par_entry = min(computed, key=lambda p: abs(p["price_pct"] - _PAR_TARGET))
            par_entry["is_par_rate"] = True

            lower_rate_desc = sorted(
                (p for p in computed if p["note_rate"] < par_entry["note_rate"]),
                key=lambda p: p["note_rate"],
                reverse=True,
            )
            for candidate in lower_rate_desc:
                if _BUYDOWN_POINTS_LOW <= candidate["discount_points_pct"] <= _BUYDOWN_POINTS_HIGH:
                    candidate["is_buydown_rate"] = True
                    break

        computed.sort(key=lambda p: p["note_rate"])
        return [PricedProductDTO(**entry) for entry in computed]
