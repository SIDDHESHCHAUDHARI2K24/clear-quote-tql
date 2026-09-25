"""LO-facing email bodies for the three borrower actions (spec.md).

Plain Python string-building, not Jinja (H4's `jinja2`/`weasyprint` are
reserved for CQ-020's PDF letter, per that item's foundation notes) --
matches the existing convention (`auth/borrower/service.py`'s
`_OTP_EMAIL_HTML`/`_EXISTING_ACCOUNT_HTML`), just table-based and
inline-styled per this item's own brief ("plain, table-based,
inline-styled").

**AC5**: never say "accept", "lock" or "approved rate" anywhere in this
module -- the borrower's rate is never locked and the report is never a
binding acceptance (system-design.md's Application status machine note,
Decision 5). `tests/test_templates.py::test_no_binding_language` scans
every function in this module's output for those words.
"""

from __future__ import annotations

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


def move_forward_subject(borrower_name: str, option_label: str) -> str:
    return f"{borrower_name} would like to move forward with {option_label}"


def move_forward_html(*, borrower_name: str, option_label: str, borrower_email: str) -> str:
    intro = (
        f"{borrower_name} would like to move forward with the "
        f"<strong>{option_label}</strong> option."
    )
    return _shell(
        heading="A borrower wants to move forward",
        intro=intro,
        rows=[
            ("Borrower", borrower_name),
            ("Email", borrower_email),
            ("Option", option_label),
        ],
        footer=(
            "Nothing is finalized yet -- this is a request to move forward, not a "
            "binding commitment. Follow up with the borrower about next steps."
        ),
    )


def ask_other_subject(borrower_name: str) -> str:
    return f"{borrower_name} has a question about their options"


def ask_other_html(
    *, borrower_name: str, option_label: str | None, message: str, borrower_email: str
) -> str:
    intro = f"{borrower_name} asked about another option and left a note."
    rows = [("Borrower", borrower_name), ("Email", borrower_email)]
    if option_label is not None:
        rows.append(("Currently viewing", option_label))
    rows.append(("Message", message))
    return _shell(heading="A borrower has a question", intro=intro, rows=rows)


def ask_updated_subject(borrower_name: str) -> str:
    return f"{borrower_name} asked for updated numbers"


def ask_updated_html(*, borrower_name: str, borrower_email: str, message: str | None) -> str:
    intro = f"{borrower_name} asked for updated numbers -- their report has expired."
    rows = [("Borrower", borrower_name), ("Email", borrower_email)]
    if message:
        rows.append(("Message", message))
    return _shell(heading="A borrower needs an updated quote", intro=intro, rows=rows)
