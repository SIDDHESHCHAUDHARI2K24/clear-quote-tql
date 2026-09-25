"""LO email for a new portal application (CQ-032 AC5, plan.md decision 21).

Plain string building, table-based and inline-styled, like
`portal/actions/templates.py`. Every interpolated value is HTML-escaped
(it is borrower-entered).
"""

from __future__ import annotations

from html import escape

_ROW = (
    '<tr><td style="padding:4px 12px 4px 0;color:#5b6472;font-size:13px;'
    'white-space:nowrap;vertical-align:top;">{label}</td>'
    '<td style="padding:4px 0;color:#0f1b33;font-size:13px;">{value}</td></tr>'
)


def new_application_subject(borrower_name: str) -> str:
    return f"New application from {borrower_name}"


def new_application_html(
    *,
    lo_name: str,
    borrower_name: str,
    borrower_email: str,
    goal: str,
    price: str,
    location: str,
) -> str:
    rows = [
        ("Borrower", borrower_name),
        ("Email", borrower_email),
        ("Goal", goal),
        ("Target price", price),
        ("Location", location),
    ]
    rows_html = "".join(_ROW.format(label=escape(k), value=escape(v)) for k, v in rows)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="font-family:-apple-system,Helvetica,Arial,sans-serif;background:#f4f5f7;'
        'padding:24px 0;"><tr><td>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e2e5eb;'
        'border-radius:8px;padding:24px;">'
        '<tr><td style="padding-bottom:12px;"><h1 style="margin:0;font-size:18px;'
        f'color:#0f1b33;">New application from {escape(borrower_name)}</h1></td></tr>'
        '<tr><td style="padding-bottom:16px;color:#0f1b33;font-size:14px;">'
        f"Hi {escape(lo_name)}, a borrower applied through the Borrower portal and was "
        "assigned to you. The pipeline is verifying, enriching and pricing it now; no "
        "action is needed until it is priced or flagged.</td></tr>"
        f'<tr><td><table role="presentation" cellpadding="0" cellspacing="0">{rows_html}'
        "</table></td></tr>"
        "</table></td></tr></table>"
    )
