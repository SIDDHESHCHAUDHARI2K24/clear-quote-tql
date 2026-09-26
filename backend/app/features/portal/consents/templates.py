"""LO notification emails for a borrower's hard-pull decision (CQ-033)."""

from __future__ import annotations

import html


def _wrap(body: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="font-family:-apple-system,Helvetica,Arial,sans-serif;">'
        f'<tr><td style="padding:24px;color:#0f1b33;font-size:14px;">{body}</td></tr></table>'
    )


def authorized_subject(fico: int) -> str:
    return f"Credit check authorized — FICO {fico}"


def authorized_html(*, borrower_name: str, fico: int, link: str) -> str:
    name = html.escape(borrower_name)
    href = html.escape(link, quote=True)
    return _wrap(
        f"<p>{name} authorized the hard credit check. The pull is complete.</p>"
        f"<p><strong>Representative FICO: {fico}</strong> (middle of three bureau scores).</p>"
        f'<p><a href="{href}" style="color:#1d4ed8;">Open the Credit tab</a></p>'
    )


def declined_subject() -> str:
    return "Credit check declined"


def declined_html(*, borrower_name: str, reason: str | None, link: str) -> str:
    name = html.escape(borrower_name)
    href = html.escape(link, quote=True)
    why = f"<p>Reason given: {html.escape(reason)}</p>" if reason else "<p>No reason was given.</p>"
    return _wrap(
        f"<p>{name} declined the hard credit check. No credit pull was made.</p>"
        f"{why}"
        f'<p><a href="{href}" style="color:#1d4ed8;">Open the Credit tab</a></p>'
    )


def failed_subject() -> str:
    return "Credit check could not be completed"


def failed_html(*, borrower_name: str, link: str) -> str:
    name = html.escape(borrower_name)
    href = html.escape(link, quote=True)
    return _wrap(
        f"<p>{name} authorized the hard credit check, but the credit bureau could not be "
        "reached. No credit pull was made and the request is still open, so the borrower "
        "can try again.</p>"
        f'<p><a href="{href}" style="color:#1d4ed8;">Open the Credit tab</a></p>'
    )
