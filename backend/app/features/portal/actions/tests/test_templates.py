"""AC5: no email wording uses "accept", "lock" or "approved rate"."""

from __future__ import annotations

import re

from app.features.portal.actions import templates

_ACCEPT_RE = re.compile(r"\baccept\w*\b", re.IGNORECASE)
_LOCK_RE = re.compile(r"\block\b", re.IGNORECASE)
_APPROVED_RATE_RE = re.compile(r"\bapproved rate\b", re.IGNORECASE)

_SAMPLES = [
    templates.move_forward_subject("Marcus Hale", "Buydown"),
    templates.move_forward_html(
        borrower_name="Marcus Hale",
        option_label="Buydown",
        borrower_email="marcus.hale@clearquote-demo.test",
    ),
    templates.ask_other_subject("Marcus Hale"),
    templates.ask_other_html(
        borrower_name="Marcus Hale",
        option_label="Par",
        message="Could we lower the cash to close?",
        borrower_email="marcus.hale@clearquote-demo.test",
    ),
    templates.ask_other_html(
        borrower_name="Marcus Hale",
        option_label=None,
        message="What else is available?",
        borrower_email="marcus.hale@clearquote-demo.test",
    ),
    templates.ask_updated_subject("Grace Kim"),
    templates.ask_updated_html(
        borrower_name="Grace Kim", borrower_email="grace.kim@clearquote-demo.test", message=None
    ),
    templates.ask_updated_html(
        borrower_name="Grace Kim",
        borrower_email="grace.kim@clearquote-demo.test",
        message="Can you refresh these numbers?",
    ),
]


def test_no_binding_language() -> None:
    for sample in _SAMPLES:
        assert not _ACCEPT_RE.search(sample), sample
        assert not _LOCK_RE.search(sample), sample
        assert not _APPROVED_RATE_RE.search(sample), sample
