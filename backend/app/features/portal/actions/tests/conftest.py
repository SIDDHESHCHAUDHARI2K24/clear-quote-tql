"""Local fixtures for `portal/actions/tests`.

Re-exports `portal/reports/tests/conftest.py`'s `make_application`/
`set_field_value`/`seed_conventional_rate_sheet` instead of duplicating
them -- pytest registers any `@pytest_asyncio.fixture`-decorated name it
finds in a directory's `conftest.py`, including ones imported from
elsewhere, so this import alone makes them available to every test module
under `portal/actions/tests/` (same technique `portal/reports/tests`
itself could have used for `pricing/conftest.py`, but chose to duplicate
instead per its own docstring -- re-exporting here since the fixtures are
identical and this is a sibling, not a copy someone else owns).
"""

from __future__ import annotations

from app.features.portal.reports.tests.conftest import (  # noqa: F401
    make_application,
    seed_conventional_rate_sheet,
    set_field_value,
)
