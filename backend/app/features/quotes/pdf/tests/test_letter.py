"""CQ-019 AC3/AC4: the pre-approval letter template, rendered with persona
data through the real route."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.assets.models import Document
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import User
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.pdf.service import _parse_fico, fico_bracket, verified_assets_display
from app.features.quotes.send.router import LETTER_CSP
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

    # Checklist from the documents table: received documents only (catalog
    # §10; code review M9) -- the unreceived bank statement is left off.
    checklist = re.search(r'data-testid="letter-checklist".*?</ul>', html, re.S)
    assert checklist
    items = [" ".join(i.split()) for i in re.findall(r"<li>(.*?)</li>", checklist.group(0), re.S)]
    assert items == [
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


def test_parse_fico_is_defensive_about_malformed_jsonb() -> None:
    """M7: `representative_fico`'s `FieldValue.value` is JSONB and could
    hold anything; a bad value must not crash the letter."""
    assert _parse_fico(725) == 725
    assert _parse_fico(725.0) == 725
    assert _parse_fico("725") == 725
    assert _parse_fico(" 725 ") == 725
    assert _parse_fico(None) is None
    assert _parse_fico(True) is None
    assert _parse_fico("unknown") is None
    assert _parse_fico({"note": "pending"}) is None
    assert _parse_fico([]) is None


async def test_letter_omits_fico_bracket_for_malformed_field_value(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M7: a non-numeric `representative_fico` value used to 500 the whole
    letter (`int(fico_row)`); it must render with no bracket instead."""
    ids = await _seed(db_session, "kathleen_mcreynolds")
    await make_staff_session(role=UserRole.MANAGER)
    await db_session.execute(
        update(FieldValue)
        .where(
            FieldValue.application_id == ids["kathleen_mcreynolds"],
            FieldValue.field_key == "representative_fico",
        )
        .values(value="unknown")
    )
    await db_session.commit()

    html, _ = await _letter(client, ids["kathleen_mcreynolds"])
    assert 'data-testid="letter-fico"' not in html


async def test_letter_escapes_llc_name(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M8: an LLC name is borrower-editable free text; it must render HTML
    -escaped, never as raw markup."""
    ids = await _seed(db_session, "sam_reed")
    await db_session.execute(
        update(ApplicationParty)
        .where(
            ApplicationParty.application_id == ids["sam_reed"],
            ApplicationParty.role == PartyRole.BORROWER,
        )
        .values(llc_entity_name="<script>x</script> LLC")
    )
    await db_session.commit()
    await make_staff_session(role=UserRole.MANAGER)

    html, _ = await _letter(client, ids["sam_reed"])
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt; LLC" in html


async def test_letter_sends_csp_header(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M8: `letter.html` must never run script, even opened directly."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    package = (await client.get(f"/api/v1/applications/{ids['marcus_hale']}/package")).json()

    response = await client.get(f"/api/v1/packages/{package['id']}/letter.html")
    assert response.status_code == 200, response.text
    assert response.headers["content-security-policy"] == LETTER_CSP


async def test_letter_checklist_lists_received_documents_only(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M9: catalog §10 -- the checklist is "documents received", not every
    requested document."""
    ids = await _seed(db_session, "kathleen_mcreynolds")
    now = datetime.now(UTC)
    for doc_type, received in (("pay_stub", now), ("bank_statement", None)):
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

    html, _ = await _letter(client, ids["kathleen_mcreynolds"])
    checklist = re.search(r'data-testid="letter-checklist".*?</ul>', html, re.S)
    assert checklist
    items = [" ".join(i.split()) for i in re.findall(r"<li>(.*?)</li>", checklist.group(0), re.S)]
    assert items == ["Pay stubs — received"]
