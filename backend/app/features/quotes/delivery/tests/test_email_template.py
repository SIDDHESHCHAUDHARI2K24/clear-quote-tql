"""The borrower email body (spec step 4; plan.md Decision 16)."""

from __future__ import annotations

from typing import Any

from app.features.quotes.delivery.email_template import (
    BUTTON_LABEL,
    SUBJECT,
    TBD_LABEL,
    render_borrower_email,
)

URL = "http://localhost:3020/report/tok_123"


def _snapshot(property_label: str | None = "12 Oak St, Carmel, IN 46032") -> dict[str, Any]:
    option = {
        "quote_id": "q1",
        "recommended": True,
        "hero": {"monthly_payment": "2612.40", "cash_to_close": "98765.50"},
    }
    return {
        "header": {
            "first_name": "Marcus",
            "property_label": property_label,
            "purchase_price": "425000.00",
            "expires_at": "2026-10-16",
        },
        "options": [{**option, "quote_id": "q0", "recommended": False}, option],
        "lo": {
            "name": "Jordan Lee",
            "title": "Loan Officer",
            "nmls": "1234567",
            "phone": "3175550100",
            "email": "jordan.lee@clearquote-demo.test",
        },
    }


def test_email_template_summary_and_link() -> None:
    email = render_borrower_email(_snapshot(), report_url=URL)
    assert email.subject == SUBJECT == "Your pre-approval and numbers from Total Quality Lending"
    for expected in ("Hi Marcus,", "12 Oak St", "$425,000", "$2,612", "$98,766", BUTTON_LABEL):
        assert expected in email.html
        if expected != BUTTON_LABEL:
            assert expected in email.text
    assert f'href="{URL}"' in email.html
    assert f"{BUTTON_LABEL}: {URL}" in email.text
    # Table-based and inline-styled: no <style> block, no external CSS.
    assert "<table" in email.html and "<style" not in email.html and "<link" not in email.html
    assert "NMLS 1234567" in email.html
    assert "(317) 555-0100" in email.text
    assert "good through October 16, 2026" in email.text


def test_email_template_tbd_and_escaping() -> None:
    snapshot = _snapshot(property_label=None)
    snapshot["header"]["first_name"] = "<script>"
    email = render_borrower_email(snapshot, report_url=URL)
    assert TBD_LABEL in email.html
    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html
