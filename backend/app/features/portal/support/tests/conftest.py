"""Local fixtures for `portal/support/tests`.

Re-exports `portal/reports/tests/conftest.py`'s `make_application`, plus
`portal/home/tests/conftest.py`'s `make_sent_version` (CQ-034 fix, review
round 1: this feature now calls CQ-031's `stage_and_label`/`has_ever_sent`
instead of keeping its own status->stage table, so its STALE tests need
the same sent-version factory CQ-031's own tests use) -- same technique
`portal/actions/tests/conftest.py` uses instead of duplicating them.
"""

from __future__ import annotations

from app.features.portal.home.tests.conftest import make_sent_version  # noqa: F401
from app.features.portal.reports.tests.conftest import make_application  # noqa: F401
