"""The one `Principal` type shared by every principal-agnostic auth module
(plan.md Decision #8): `features/auth/otp`, `features/auth/sessions`, and
(from CQ-015) the borrower equivalents of `features/auth/staff`.

Defined once here rather than in `otp/service.py` or `sessions/service.py`
so neither module has to import the other just for this type.
"""

from typing import Literal

Principal = Literal["staff", "borrower"]
