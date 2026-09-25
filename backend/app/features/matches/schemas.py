"""`GET /applications/{id}/matches` response shape.

Decimal fields, not decimal strings -- this is an LO-console-facing API
route, not part of `ReportViewModel` (whose `packages/ui/src/report`
"no money math" scan is the reason *that* contract uses strings). Matches
`pricing/scenarios/schemas.py::QuotePreviewResponse`'s own convention
(`QuoteComputation` fields serialized as Decimal).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.features.quotes.report.inputs import ReportMatchInput


class MatchOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    matched_property_id: str
    property_image_url: str
    property_address: str
    bed_bath_sqft: str
    deal_grade_badge: str
    property_tagline: str
    price: Decimal
    total_monthly_payment: Decimal
    rent_estimate: Decimal | None
    rent_label: str | None
    monthly_cashflow: Decimal | None
    cash_to_close: Decimal
    cap_rate_pct: Decimal | None
    year1_tax_savings: Decimal | None

    @classmethod
    def from_input(cls, match: ReportMatchInput) -> MatchOut:
        return cls(
            matched_property_id=match.matched_property_id,
            property_image_url=match.property_image_url,
            property_address=match.property_address,
            bed_bath_sqft=match.bed_bath_sqft,
            deal_grade_badge=match.deal_grade_badge,
            property_tagline=match.property_tagline,
            price=match.price,
            total_monthly_payment=match.total_monthly_payment,
            rent_estimate=match.rent_estimate,
            rent_label=match.rent_label,
            monthly_cashflow=match.monthly_cashflow,
            cash_to_close=match.cash_to_close,
            cap_rate_pct=match.cap_rate_pct,
            year1_tax_savings=match.year1_tax_savings,
        )


class MatchListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    matches: list[MatchOut]
