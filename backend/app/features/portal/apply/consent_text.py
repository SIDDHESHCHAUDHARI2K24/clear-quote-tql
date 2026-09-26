"""The apply wizard's tab-4 consent text (CQ-032 AC6, plan.md decision 18).

The exact text the borrower sees is served in the draft response and its
SHA-256 is stored on the `consents` row at submit, so the stored hash
proves which wording was agreed to. Changing the wording means a new
`CONSENT_TEXT_VERSION`.
"""

from __future__ import annotations

import hashlib

CONSENT_TEXT_VERSION = "apply-v1"

SOFT_PULL_TEXT = (
    "I authorize Clear Quote to obtain my credit report with a soft inquiry, which does "
    "not affect my credit score, to prepare my loan quote."
)
CONTACT_TEXT = (
    "I agree that Clear Quote and my loan officer may contact me by email, phone or text "
    "about this application."
)
TERMS_TEXT = (
    "I have read and agree to the Terms of Use and Privacy Notice, and I confirm the "
    "information in this application is true and complete."
)

CONSENT_TEXT = "\n\n".join((SOFT_PULL_TEXT, CONTACT_TEXT, TERMS_TEXT))
"""The full text shown on tab 4 (three checkboxes, in this order)."""


def consent_text_hash(text: str = CONSENT_TEXT) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
