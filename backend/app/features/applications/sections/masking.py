"""SSN masking: section responses never carry a full SSN (plan.md #20)."""

from __future__ import annotations


def mask_ssn(ssn: str | None) -> str | None:
    if not ssn:
        return None
    digits = "".join(ch for ch in ssn if ch.isdigit())
    last4 = digits[-4:] if len(digits) >= 4 else ""
    return f"***-**-{last4}" if last4 else "***-**-****"
