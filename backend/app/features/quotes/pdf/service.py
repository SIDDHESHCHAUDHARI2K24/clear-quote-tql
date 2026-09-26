"""Pre-approval letter (CQ-019): context building and HTML rendering.

`render_package_letter(db, package, *, portal_url=None, letter_date=None)`
is the entry point. It builds a `LetterContext` (catalog §10 variables) from
the package's rows and renders `templates/preapproval_letter.html` with
Jinja2 (autoescaped). The Send tab previews that HTML
(`GET /packages/{id}/letter.html`); CQ-020 feeds the same HTML to
WeasyPrint for the PDF, passing the real `/report/{token}` URL as
`portal_url`. Until then `portal_url=None` renders a placeholder line.

Every number is display formatting of engine output (`Quote.computed`) or a
`quote_engine` helper (`verified_assets_floor`); nothing here prices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import ValidationAppError
from app.features.applications.assets.models import Asset, Document
from app.features.applications.models import ApplicationParty, BusinessVesting, PartyRole
from app.features.applications.property.models import PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.quote_engine import verified_assets_floor
from app.features.pricing.engine.types import QuoteComputation, ScenarioInputs, StrategyType
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage
from app.features.quotes.send.view_model import PackageContext, load_package_context

TEMPLATES_DIR = Path(__file__).parent / "templates"
LETTER_TEMPLATE = "preapproval_letter.html"

LENDER_ENTITY_NAME = "Total Quality Lending"
LENDER_NMLS = "1933377"
LENDER_ADDRESS = "630 W Carmel Dr, Suite 160, Carmel, IN 46032"
LENDER_PHONE = "(800) 304-1928"
TBD_PROPERTY = "- TBD -"
DISCLAIMER_CORE = (
    "Loan contingency: further investigation of the property or borrower could result in "
    "a loan denial. This letter is not a commitment to lend and the interest rate is not "
    f"locked. {LENDER_ENTITY_NAME} is an Equal Housing Lender. NMLS ID #{LENDER_NMLS}."
)

_DOC_LABELS = {
    "pay_stub": "Pay stubs",
    "w2": "W-2s",
    "tax_return": "Tax returns",
    "bank_statement": "Bank statements",
}
_PROPERTY_TYPES = {
    PropertyType.SINGLE_FAMILY: "SFR",
    PropertyType.TWO_TO_FOUR_UNIT: "2-4 Unit",
    PropertyType.CONDO: "Condo",
    PropertyType.TOWNHOME: "Townhome",
}
_FICO_BANDS = (780, 760, 740, 720, 700, 680, 660, 640, 620)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class ChecklistItem:
    label: str
    status: str
    """"received" or "requested"."""


@dataclass(frozen=True)
class LetterContext:
    """Catalog §10 pre-approval letter template variables."""

    letter_date: str
    borrower_name: str
    """`llc_entity_name` when vesting in an LLC, else the borrower's name."""
    is_llc: bool
    lo_name: str
    lo_title: str
    lo_nmls: str
    lo_phone: str
    lo_email: str
    lender_entity_name: str
    lender_nmls: str
    lender_address: str
    lender_phone: str
    purchase_price: str
    loan_amount: str
    ltv_percentage: str
    loan_term_years: int
    loan_type: str
    occupancy: str
    property_type: str
    property_address: str
    """The full address, or `"- TBD -"`."""
    fico_bracket: str | None
    verified_assets_display: str | None
    verification_checklist: list[ChecklistItem]
    disclaimer_core: str
    portal_url: str | None


def fico_bracket(score: int) -> str:
    """catalog §3 `credit_score_bracket`: 20-point bands, e.g. `"780+"`,
    `"720–739"`, `"Below 620"`."""
    if score >= _FICO_BANDS[0]:
        return f"{_FICO_BANDS[0]}+"
    for low in _FICO_BANDS[1:]:
        if score >= low:
            return f"{low}–{low + 19}"
    return f"Below {_FICO_BANDS[-1]}"


def _parse_fico(value: Any) -> int | None:
    """`representative_fico`'s `FieldValue.value` is JSONB (`dict | list |
    str | float | bool | None`); a malformed or non-numeric override used to
    500 the letter via a bare `int(...)` (code review M7). Render no
    bracket instead of failing the letter."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def verified_assets_display(threshold: Decimal) -> str | None:
    """catalog §3: `"Verified Assets $135K+"` from `verified_assets_floor`."""
    if threshold <= 0:
        return None
    thousands = (threshold / Decimal("1000")).to_integral_value()
    return f"Verified Assets ${thousands:,}K+"


def _usd(value: Decimal) -> str:
    return f"${value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"


def _format_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone or ""


def _full_address(ctx: PackageContext) -> str:
    prop = ctx.prop
    if prop is None or prop.address_status is PropertyAddressStatus.TBD:
        return TBD_PROPERTY
    state_zip = " ".join(p for p in (prop.state, prop.zip) if p)
    return ", ".join(p for p in (prop.street_address, prop.city, state_zip) if p) or TBD_PROPERTY


def par_quote(ctx: PackageContext, recommended_quote_id: Any) -> Quote:
    """The letter shows the par quote only (system-design.md Send): the
    package's first Par, recommended first; else the recommended quote,
    else the first quote."""
    ordered = sorted(ctx.quotes, key=lambda q: q.id != recommended_quote_id)
    par = next((q for q in ordered if q.label == "Par"), None)
    if par is not None:
        return par
    if not ordered:
        raise ValidationAppError("The package has no quotes for the letter.")
    return ordered[0]


async def build_letter_context(
    db: AsyncSession,
    package: QuotePackage,
    *,
    portal_url: str | None = None,
    letter_date: date | None = None,
) -> LetterContext:
    ctx = await load_package_context(db, package)
    quote = par_quote(ctx, package.recommended_quote_id)
    computation = QuoteComputation.model_validate(quote.computed)
    inputs = ScenarioInputs.model_validate(ctx.scenarios[quote.scenario_id].inputs)

    borrower = (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == ctx.application.id,
                ApplicationParty.role == PartyRole.BORROWER,
            )
        )
    ).scalar_one_or_none()
    is_llc = bool(
        borrower is not None
        and borrower.business_vesting is BusinessVesting.TITLE_LIEN_IN_LLC
        and borrower.llc_entity_name
    )
    borrower_name = (
        borrower.llc_entity_name
        if is_llc and borrower is not None and borrower.llc_entity_name
        else ctx.client.full_name
    )

    fico_row = (
        await db.execute(
            select(FieldValue.value).where(
                FieldValue.application_id == ctx.application.id,
                FieldValue.field_key == "representative_fico",
            )
        )
    ).scalar_one_or_none()
    amounts = (
        (
            await db.execute(
                select(Asset.verified_amount).where(Asset.application_id == ctx.application.id)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        (
            await db.execute(
                select(Document)
                .where(Document.application_id == ctx.application.id)
                .order_by(Document.doc_type, Document.created_at)
            )
        )
        .scalars()
        .all()
    )
    # catalog §10: the checklist lists documents *received*, not
    # outstanding requests (code review M9).
    seen: dict[str, ChecklistItem] = {}
    for doc in documents:
        if doc.received_at is None:
            continue
        label = _DOC_LABELS.get(doc.doc_type, doc.doc_type.replace("_", " ").capitalize())
        seen[label] = ChecklistItem(label, "received")

    is_primary = ctx.strategy is StrategyType.PRIMARY
    term_years = inputs.term_months // 12
    lo = ctx.lo
    prop = ctx.prop
    return LetterContext(
        letter_date=(letter_date or clock.now().date()).strftime("%m/%d/%Y"),
        borrower_name=borrower_name,
        is_llc=is_llc,
        lo_name=lo.full_name,
        lo_title=lo.title or "Loan Officer",
        lo_nmls=lo.nmls or "",
        lo_phone=_format_phone(lo.phone),
        lo_email=lo.email,
        lender_entity_name=LENDER_ENTITY_NAME,
        lender_nmls=LENDER_NMLS,
        lender_address=LENDER_ADDRESS,
        lender_phone=LENDER_PHONE,
        purchase_price=_usd(inputs.purchase_price),
        loan_amount=_usd(computation.loan_amount),
        ltv_percentage=f"{(computation.ltv_pct * 100).quantize(Decimal('1'), ROUND_HALF_UP)}%",
        loan_term_years=term_years,
        loan_type=f"{'Conventional' if is_primary else 'DSCR'} {term_years} YR Fixed",
        occupancy="Primary Residence" if is_primary else "Investment",
        property_type=_PROPERTY_TYPES.get(prop.property_type, "SFR") if prop else "SFR",
        property_address=_full_address(ctx),
        fico_bracket=(fico_bracket(fico) if (fico := _parse_fico(fico_row)) is not None else None),
        verified_assets_display=verified_assets_display(verified_assets_floor(amounts)),
        verification_checklist=list(seen.values()),
        disclaimer_core=DISCLAIMER_CORE,
        portal_url=portal_url,
    )


def render_letter_html(context: LetterContext) -> str:
    """Pure: the letter HTML for `context`. CQ-020 passes this string to
    WeasyPrint (`HTML(string=...).write_pdf()`)."""
    return _env.get_template(LETTER_TEMPLATE).render(**asdict(context))


async def render_package_letter(
    db: AsyncSession,
    package: QuotePackage,
    *,
    portal_url: str | None = None,
    letter_date: date | None = None,
) -> str:
    context = await build_letter_context(
        db, package, portal_url=portal_url, letter_date=letter_date
    )
    return render_letter_html(context)


def render_letter_pdf(html: str) -> bytes:
    """CQ-020: WeasyPrint renders the letter HTML to a US Letter PDF (the
    template's own `@page { size: letter }`). Imported lazily: WeasyPrint
    loads Pango/cairo through cffi at import time, and only the send worker
    and the letter tests need it (macOS: `brew install pango` and
    `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, which the Makefile
    exports on Darwin). CPU-bound and synchronous -- async callers run it
    in `asyncio.to_thread`."""
    from weasyprint import HTML

    pdf: bytes = HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()
    return pdf
