"""`portal/support/templates.py` (CQ-034 spec.md)."""

from __future__ import annotations

from app.features.portal.support import templates


def test_support_inbox_subject_format() -> None:
    subject = templates.support_inbox_subject(
        reference="SUP-7F3K2", topic="quote", borrower_name="Marcus Hale"
    )
    assert subject == "[SUP-7F3K2] quote — Marcus Hale"


def test_support_inbox_html_with_application() -> None:
    html = templates.support_inbox_html(
        reference="SUP-7F3K2",
        borrower_name="Marcus Hale",
        borrower_email="marcus.hale@clearquote-demo.test",
        phone="8135550123",
        preferred_contact="email",
        message="A question about my buydown option.",
        application_id="11111111-1111-1111-1111-111111111111",
        stage_label="Your pre-approval is ready",
        internal_status="sent",
        property_label="123 Main St, Tampa, FL 33602",
        lo_name="Jordan Blake",
        lo_console_url="http://localhost:3010/applications/11111111-1111-1111-1111-111111111111",
    )
    assert "Marcus Hale" in html
    assert "marcus.hale@clearquote-demo.test" in html
    assert "8135550123" in html
    assert "A question about my buydown option." in html
    assert "Your pre-approval is ready" in html
    assert "sent" in html
    assert "123 Main St, Tampa, FL 33602" in html
    assert "Jordan Blake" in html
    assert "http://localhost:3010/applications/11111111-1111-1111-1111-111111111111" in html
    assert "No application yet" not in html


def test_support_inbox_html_without_application_says_no_application_yet() -> None:
    html = templates.support_inbox_html(
        reference="SUP-7F3K2",
        borrower_name="Nadia Noapp",
        borrower_email="noapp.borrower@clearquote-demo.test",
        phone=None,
        preferred_contact="email",
        message="How do I start an application?",
        application_id=None,
        stage_label=None,
        internal_status=None,
        property_label=None,
        lo_name="Jordan Blake",
        lo_console_url=None,
    )
    assert "No application yet" in html
    assert "Jordan Blake" in html


def test_confirmation_html_has_reference() -> None:
    subject = templates.confirmation_subject("SUP-7F3K2")
    html = templates.confirmation_html(borrower_name="Marcus Hale", reference="SUP-7F3K2")
    assert "SUP-7F3K2" in subject
    assert "SUP-7F3K2" in html
    assert "Marcus Hale" in html


def test_support_inbox_html_escapes_borrower_supplied_markup() -> None:
    """Code review (round 1): `message`, `phone`, `borrower_name` and
    `property_label` are all borrower- or LO-entered free text -- a
    message containing a `<a href=...>` tag must render as inert text in
    the mailed HTML, not a live link/markup break."""
    injected = '<a href="http://evil.example/verify">Click to verify your loan</a>'
    html = templates.support_inbox_html(
        reference="SUP-7F3K2",
        borrower_name=injected,
        borrower_email="marcus.hale@clearquote-demo.test",
        phone=injected,
        preferred_contact="email",
        message=injected,
        application_id="11111111-1111-1111-1111-111111111111",
        stage_label="Your pre-approval is ready",
        internal_status="sent",
        property_label=injected,
        lo_name="Jordan Blake",
        lo_console_url="http://localhost:3010/applications/11111111-1111-1111-1111-111111111111",
    )
    assert injected not in html
    assert "&lt;a href=" in html
    # The one legitimate `<a href=...>` in the email is the LO console
    # link this module itself builds, from a config'd base URL + a UUID.
    assert html.count("<a href=") == 1
    assert 'href="http://localhost:3010/applications/' in html


def test_confirmation_html_escapes_borrower_name() -> None:
    injected = "<script>alert(1)</script>"
    html = templates.confirmation_html(borrower_name=injected, reference="SUP-7F3K2")
    assert injected not in html
    assert "&lt;script&gt;" in html
