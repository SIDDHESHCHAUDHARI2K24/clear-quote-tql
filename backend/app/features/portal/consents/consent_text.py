"""Hard-pull consent text, version `hard_pull_v1` (CQ-033, plan.md decision 1).

The exact text the borrower sees is served by `GET /portal/consents/{id}`
and its SHA-256 is stored on the `consents` row with the decision, so the
stored hash proves which wording was agreed to. Changing the wording means
a new `HARD_PULL_TEXT_VERSION` (and a new constant), never an edit in place.

Hardening m2: the checkbox sentence ("I authorize ...") is part of the
versioned text -- its last paragraph -- so the hash covers it. The API
serves it separately as `authorization` (the checkbox label) next to `body`
(the paragraphs above it); `sha256` hashes the whole text, and the portal
echoes it back on accept (409 `CONSENT_TEXT_CHANGED` on a mismatch). The
sentence was folded into `hard_pull_v1` in place because no v1 decision
exists outside rebuildable dev/demo databases (pre-release).
"""

from __future__ import annotations

import hashlib

HARD_PULL_TEXT_VERSION = "hard_pull_v1"

HARD_PULL_AUTHORIZATION_V1 = (
    "I authorize Clear Quote to obtain my credit report from Experian, Equifax and "
    "TransUnion as described above."
)
"""The checkbox sentence: the last paragraph of `HARD_PULL_TEXT_V1`."""

HARD_PULL_TEXT_V1 = "\n\n".join(
    (
        "Who is asking: Clear Quote, on behalf of your loan officer, will request your "
        "credit report.",
        "Which bureaus: we will obtain your credit report and scores from all three "
        "national credit bureaus: Experian, Equifax and TransUnion.",
        "Why: to verify your credit history and debts, finalize your pre-approval and "
        "price your loan with your representative credit score (the middle of the three "
        "scores).",
        "Effect on your score: this is a hard inquiry. It is visible to other lenders and "
        "may lower your credit scores by a few points. Mortgage inquiries made within a "
        "short shopping period are usually counted as one inquiry.",
        "By authorizing, you give Clear Quote written permission under the Fair Credit "
        "Reporting Act to obtain your consumer credit report for this loan application. "
        "You may decline instead; your loan officer will be told and no credit check will "
        "be made.",
        HARD_PULL_AUTHORIZATION_V1,
    )
)

HARD_PULL_TEXTS: dict[str, str] = {HARD_PULL_TEXT_VERSION: HARD_PULL_TEXT_V1}


def hard_pull_text(version: str = HARD_PULL_TEXT_VERSION) -> str:
    return HARD_PULL_TEXTS[version]


def split_text(text: str) -> tuple[str, str]:
    """(body, authorization): the paragraphs above the checkbox and the
    checkbox sentence (the text's last paragraph)."""
    body, _, authorization = text.rpartition("\n\n")
    return body, authorization


def consent_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
