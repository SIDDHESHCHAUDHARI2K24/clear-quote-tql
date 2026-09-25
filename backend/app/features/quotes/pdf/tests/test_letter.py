"""CQ-019 AC3/AC4: the pre-approval letter template, rendered with persona
data through the real route."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.assets.models import Document
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.pdf.service import fico_bracket, verified_assets_display
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _letter(client: AsyncClient, application_id: uuid.UUID) -> tuple[str, dict]:
    package = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    response = await client.get(f"/api/v1/packages/{package['id']}/letter.html")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "sandbox" in response.headers["content-security-policy"]
    return response.text, package


def _text(html: str, testid: str) -> str:
    match = re.search(rf'data-testid="{testid}"[^>]*>(.*?)</', html, re.S)
    assert match, testid
    return " ".join(match.group(1).split())


def _usd(value: str) -> str:
    return f"${Decimal(value).quantize(Decimal('1')):,}"


async def test_letter_tbd_variant(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC3: Kathleen McReynolds (TBD property)."""
    ids = await _seed(db_session, "kathleen_mcreynolds")
    # `_seed` skips MinIO documents; add the documents-table rows directly.
    now = datetime.now(UTC)
    for doc_type, received in (("pay_stub", now), ("bank_statement", None), ("w2", now)):
        db_session.add(
            Document(
                application_id=ids["kathleen_mcreynolds"],
                doc_type=doc_type,
                object_key=f"test/{doc_type}.pdf",
                received_at=received,
            )
        )
    await db_session.commit()
    await make_staff_session(role=UserRole.MANAGER)
    html, package = await _letter(client, ids["kathleen_mcreynolds"])

    assert _text(html, "letter-property") == "- TBD -"
    assert _text(html, "letter-borrower") == "Kathleen McReynolds"
    assert _text(html, "letter-fico") == "Credit score 720–739"
    assert _text(html, "letter-assets") == "Verified Assets $80K+"

    # Par quote terms only: the letter's loan amount is the par quote's.
    par = await db_session.get(Quote, uuid.UUID(package["recommended_quote_id"]))
    assert par is not None and par.label == "Par"
    assert isinstance(par.computed, dict)
    terms = re.search(r'data-testid="letter-terms".*?</table>', html, re.S)
    assert terms
    assert f">{_usd(str(par.computed['loan_amount']))}<" in terms.group(0)
    assert html.count("Loan Amount") == 1
    for other_id in package["quote_ids"][1:]:
        other = await db_session.get(Quote, uuid.UUID(other_id))
        assert other is not None
        assert f"{other.rate}%" not in html  # no rate from any quote
    assert f"{par.rate}%" not in html  # the rate is not locked; the letter shows none

    # Assigned LO signs (Decision 4).
    application = await db_session.get(Application, ids["kathleen_mcreynolds"])
    assert application is not None
    lo = await db_session.get(User, application.lo_id)
    assert lo is not None
    signature = re.search(r'data-testid="letter-signature".*?</div>\s*</div>', html, re.S)
    assert signature
    block = signature.group(0)
    assert lo.full_name in block
    assert f'NMLS #<span class="num">{lo.nmls}</span>' in block
    assert lo.email in block
    assert (lo.title or "Loan Officer") in block
    assert lo.phone and lo.phone[-4:] in block

    # Checklist from the documents table; portal link placeholder until CQ-020.
    checklist = re.search(r'data-testid="letter-checklist".*?</ul>', html, re.S)
    assert checklist
    items = [" ".join(i.split()) for i in re.findall(r"<li>(.*?)</li>", checklist.group(0), re.S)]
    assert items == [
        "Bank statements — requested",
        "Pay stubs — received",
        "W-2s — received",
    ]
    assert "the link arrives in your quote" in _text(html, "letter-portal")


async def test_letter_llc_and_address_variants(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC4: Sam Reed vests in Asheville Holdings LLC; Marcus Hale has a
    specific address."""
    ids = await _seed(db_session, "sam_reed", "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)

    sam_html, _ = await _letter(client, ids["sam_reed"])
    assert _text(sam_html, "letter-borrower") == "Asheville Holdings LLC"
    assert "Sam Reed" not in sam_html
    assert _text(sam_html, "letter-property").startswith("212 Merrimon Ave, Asheville, NC")

    marcus_html, _ = await _letter(client, ids["marcus_hale"])
    assert _text(marcus_html, "letter-borrower") == "Marcus Hale"
    assert re.fullmatch(r"4412 W Gray St, Tampa, FL \d{5}", _text(marcus_html, "letter-property"))


def test_fico_bracket_and_assets_display() -> None:
    assert fico_bracket(782) == "780+"
    assert fico_bracket(780) == "780+"
    assert fico_bracket(779) == "760–779"
    assert fico_bracket(722) == "720–739"
    assert fico_bracket(619) == "Below 620"
    assert verified_assets_display(Decimal("135000")) == "Verified Assets $135K+"
    assert verified_assets_display(Decimal("1200000")) == "Verified Assets $1,200K+"
    assert verified_assets_display(Decimal("0")) is None
