"""Email bodies for `POST /api/v1/portal/support` (CQ-034 spec.md): one to
the support inbox, one confirmation back to the borrower.

Plain Python string-building (not Jinja), same table-based, inline-styled
convention as `portal/actions/templates.py` -- `_shell`/`_ROW` are a local
copy of that module's private helpers rather than an import of another
feature's underscore-prefixed symbols (same reasoning
`portal/reports/versions.py::_strategy_type`'s docstring gives for its own
small, feature-local duplicate).
"""

from __future__ import annotations

import html as _html_module

_ROW = (
    '<tr><td style="padding:4px 12px 4px 0;color:#5b6472;'
    'font-size:13px;white-space:nowrap;vertical-align:top;">{label}</td>'
    '<td style="padding:4px 0;color:#0f1b33;font-size:13px;">{value}</td></tr>'
)


def _shell(
    *, heading: str, intro: str, rows: list[tuple[str, str]], footer: str | None = None
) -> str:
    """A minimal, inline-styled, table-based email body -- one `<table>`
    for layout (widest email-client compatibility), a `<table>` of
    label/value rows for the details, no external stylesheet."""
    rows_html = "".join(_ROW.format(label=label, value=value) for label, value in rows)
    footer_html = (
        f'<p style="color:#5b6472;font-size:12px;margin-top:16px;">{footer}</p>' if footer else ""
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="font-family:-apple-system,Helvetica,Arial,sans-serif;'
        'background:#f4f5f7;padding:24px 0;">'
        "<tr><td>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e2e5eb;'
        'border-radius:8px;padding:24px;">'
        f'<tr><td style="padding-bottom:12px;">'
        f'<h1 style="margin:0;font-size:18px;color:#0f1b33;">{heading}</h1></td></tr>'
        f'<tr><td style="padding-bottom:16px;color:#0f1b33;font-size:14px;">{intro}</td></tr>'
        f'<tr><td><table role="presentation" cellpadding="0" cellspacing="0">{rows_html}</table>'
        "</td></tr>"
        f"<tr><td>{footer_html}</td></tr>"
        "</table>"
        "</td></tr>"
        "</table>"
    )


_NO_APPLICATION_TEXT = "No application yet"


def _esc(value: str) -> str:
    """Code-review finding: every row value here can be borrower- or
    LO-supplied free text (`message`/`phone`/`preferred_contact` from the
    request body; `borrower_name`/`lo_name` from `clients.full_name`/
    `users.full_name`; `property_label` from an LO-entered street
    address) -- interpolating it unescaped into HTML mailed to a real
    inbox is a stored-HTML/phishing-link vector. Every plain-text row
    value and every heading/intro/footer string is escaped; the one
    exception (the LO console `<a>` row) builds its own escaped `href`/
    link text explicitly rather than going through this helper's
    "already HTML" callers."""
    return _html_module.escape(value, quote=True)


def support_inbox_subject(*, reference: str, topic: str, borrower_name: str) -> str:
    return f"[{reference}] {topic} — {borrower_name}"


def support_inbox_html(
    *,
    reference: str,
    borrower_name: str,
    borrower_email: str,
    phone: str | None,
    preferred_contact: str,
    message: str,
    application_id: str | None,
    stage_label: str | None,
    internal_status: str | None,
    property_label: str | None,
    lo_name: str,
    lo_console_url: str | None,
) -> str:
    rows: list[tuple[str, str]] = [
        ("Borrower", _esc(borrower_name)),
        ("Email", _esc(borrower_email)),
        ("Phone", _esc(phone) if phone else "—"),
        ("Preferred contact", _esc(preferred_contact)),
        ("Message", _esc(message)),
    ]
    if application_id is None:
        rows.append(("Application", _NO_APPLICATION_TEXT))
    else:
        assert stage_label is not None
        assert internal_status is not None
        rows.append(("Application", _esc(application_id)))
        rows.append(("Stage", _esc(stage_label)))
        rows.append(("Internal status", _esc(internal_status)))
        property_text = _esc(property_label) if property_label else "Property to be determined"
        rows.append(("Property", property_text))
        if lo_console_url is not None:
            escaped_url = _esc(lo_console_url)
            rows.append(("LO console", f'<a href="{escaped_url}">{escaped_url}</a>'))
    rows.append(("Assigned LO", _esc(lo_name)))

    return _shell(
        heading=f"Support request {_esc(reference)}",
        intro=f"{_esc(borrower_name)} submitted a support request.",
        rows=rows,
    )


def confirmation_subject(reference: str) -> str:
    return f"We got your message — {reference}"


def confirmation_html(*, borrower_name: str, reference: str) -> str:
    return _shell(
        heading="We got your message",
        intro=(
            f"Thanks, {_esc(borrower_name)} — your support request has been received. "
            "We'll be in touch soon."
        ),
        rows=[("Your reference", _esc(reference))],
        footer="Keep this reference in case you follow up.",
    )
