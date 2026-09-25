"""Local fixtures for `portal/support/tests`.

Re-exports `portal/reports/tests/conftest.py`'s `make_application` --
same technique `portal/actions/tests/conftest.py` uses instead of
duplicating it.
"""

from __future__ import annotations

from app.features.portal.reports.tests.conftest import make_application  # noqa: F401
