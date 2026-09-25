"""The borrower's "your numbers are ready" email (CQ-020 spec, step 4).

Table-based and inline-styled so it renders in common mail clients, and one
screen long: greeting, a four-line summary (property or TBD, purchase
price, the recommended option's monthly payment and cash to close), the
"See your numbers" button to `/report/{token}` (H2: no magic link -- the
borrower signs in first), and the LO's signature. A plain-text alternative
carries the same lines and URL.

Every figure comes from the frozen `ReportViewModel` snapshot (already
engine output as decimal strings); this module only formats them for
display (whole dollars, thousands separators). No money math.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from typing import Any

SUBJECT = "Your pre-approval and numbers from Total Quality Lending"
BUTTON_LABEL = "See your numbers"
TBD_LABEL = "Property to be determined"


@dataclass(frozen=True)
class BorrowerEmail:
    subject: str
    html: str
    text: str


def _usd(value: str | None) -> str:
    if value is None:
        return "—"
    try:
        amount = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,}"


def _recommended_option(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    options = snapshot.get("options") or []
    for option in options:
        if option.get("recommended"):
            return dict(option)
    return dict(options[0]) if options else None


def summary_rows(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    header = snapshot.get("header") or {}
    option = _recommended_option(snapshot) or {}
    hero = option.get("hero") or {}
    return [
        ("Property", header.get("property_label") or TBD_LABEL),
        ("Purchase price", _usd(header.get("purchase_price"))),
        ("Recommended monthly payment", _usd(hero.get("monthly_payment"))),
        ("Cash to close", _usd(hero.get("cash_to_close"))),
    ]


def render_borrower_email(snapshot: dict[str, Any], *, report_url: str) -> BorrowerEmail:
    header = snapshot.get("header") or {}
    lo = snapshot.get("lo") or {}
    first_name = header.get("first_name") or "there"
    lo_name = lo.get("name") or "Your loan officer"
    lo_title = lo.get("title") or "Loan Officer"
    lo_nmls = lo.get("nmls") or ""
    lo_phone = lo.get("phone") or ""
    lo_email = lo.get("email") or ""
    expires = header.get("expires_at")
    rows = summary_rows(snapshot)

    intro = (
        "Your pre-approval letter is attached, and your full set of options is ready "
        "in your Clear Quote report."
    )
    expiry_line = f"These numbers are good through {expires}." if expires else ""
    sign_in_line = "You'll sign in to your borrower account to see the report."

    row_html = "".join(
        '<tr><td style="padding:6px 16px 6px 0;color:#5b6472;font-size:14px;'
        f'white-space:nowrap;">{escape(label)}</td>'
        '<td style="padding:6px 0;color:#0f1b33;font-size:14px;font-weight:600;'
        f'text-align:right;">{escape(value)}</td></tr>'
        for label, value in rows
    )
    lo_contact = " · ".join(escape(p) for p in (lo_phone, lo_email) if p)
    nmls = f" · NMLS {escape(lo_nmls)}" if lo_nmls else ""
    safe_url = escape(report_url, quote=True)
    html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 0;'
        'font-family:-apple-system,Helvetica,Arial,sans-serif;">'
        "<tr><td>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e2e5eb;'
        'border-radius:8px;padding:24px;">'
        '<tr><td style="padding-bottom:4px;color:#1f3a5f;font-size:12px;'
        'letter-spacing:0.08em;text-transform:uppercase;">Total Quality Lending</td></tr>'
        '<tr><td style="padding-bottom:12px;">'
        f'<h1 style="margin:0;font-size:20px;color:#0f1b33;">Hi {escape(first_name)},</h1>'
        "</td></tr>"
        f'<tr><td style="padding-bottom:16px;color:#0f1b33;font-size:14px;">{escape(intro)}'
        "</td></tr>"
        '<tr><td style="padding-bottom:20px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-top:1px solid #e2e5eb;border-bottom:1px solid #e2e5eb;">'
        f"{row_html}</table></td></tr>"
        '<tr><td align="center" style="padding-bottom:12px;">'
        f'<a href="{safe_url}" data-testid="see-your-numbers" '
        'style="display:inline-block;background:#1f3a5f;color:#ffffff;text-decoration:none;'
        'font-size:15px;font-weight:600;padding:12px 28px;border-radius:6px;">'
        f"{BUTTON_LABEL}</a></td></tr>"
        '<tr><td style="padding-bottom:16px;color:#5b6472;font-size:12px;text-align:center;">'
        f"{escape(sign_in_line)} {escape(expiry_line)}</td></tr>"
        '<tr><td style="border-top:1px solid #e2e5eb;padding-top:12px;color:#0f1b33;'
        f'font-size:13px;">{escape(lo_name)}<br>'
        f'<span style="color:#5b6472;">{escape(lo_title)}{nmls}</span><br>'
        f'<span style="color:#5b6472;">{lo_contact}</span></td></tr>'
        "</table>"
        "</td></tr>"
        "</table>"
    )

    text_lines = [
        f"Hi {first_name},",
        "",
        intro,
        "",
        *(f"{label}: {value}" for label, value in rows),
        "",
        f"{BUTTON_LABEL}: {report_url}",
        sign_in_line,
    ]
    if expiry_line:
        text_lines.append(expiry_line)
    text_lines += [
        "",
        lo_name,
        f"{lo_title}{f' · NMLS {lo_nmls}' if lo_nmls else ''}",
        " · ".join(p for p in (lo_phone, lo_email) if p),
    ]
    return BorrowerEmail(subject=SUBJECT, html=html, text="\n".join(text_lines).strip() + "\n")
