"""CQ-019 AC2: the LO preview and the borrower portal report are the same
payload -- both come from `build_package_view_model`."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.portal.reports.versions import freeze_package_version
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.report.schemas import ReportViewModel
from app.features.quotes.send.models import QuotePackage
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]

SEND_TIME_HEADER_FIELDS = ("prepared_at", "rates_as_of", "expires_at", "expired", "superseded")
"""The only fields allowed to differ between the preview and the sent
report: they are set from the send time (plan.md Decision 3)."""

PORTAL_ONLY_FIELDS = ("borrower_action", "newest_report_token")
"""CQ-022/CQ-024 extras the portal adds around the `ReportViewModel`."""


def _without_send_time(payload: dict[str, Any]) -> dict[str, Any]:
    trimmed = copy.deepcopy(payload)
    for key in PORTAL_ONLY_FIELDS:
        trimmed.pop(key, None)
    for key in SEND_TIME_HEADER_FIELDS:
        trimmed["header"].pop(key)
    return trimmed


@pytest.mark.parametrize("persona", ["marcus_hale", "kathleen_mcreynolds", "priya_nair"])
async def test_report_view_model_same_for_lo_and_portal(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: Callable[..., Awaitable[Any]],
    persona: str,
) -> None:
    ids = await _seed(db_session, persona)
    application_id = ids[persona]
    await make_staff_session(role=UserRole.MANAGER)

    package_json = (await client.get(f"/api/v1/applications/{application_id}/package")).json()
    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={
            "quote_ids": package_json["quote_ids"],
            "recommended_quote_id": package_json["quote_ids"][-1],
            "lo_note": "Call me before you make an offer.",
        },
    )
    assert response.status_code == 200, response.text

    preview = await client.get(f"/api/v1/packages/{package_json['id']}/report")
    assert preview.status_code == 200, preview.text
    lo_payload = preview.json()
    ReportViewModel.model_validate(lo_payload)
    assert lo_payload["recommendation"]["lo_note"] == "Call me before you make an offer."

    package = await db_session.get(QuotePackage, package_json["id"], populate_existing=True)
    assert package is not None
    version = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    application = await db_session.get(Application, application_id)
    assert application is not None
    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row=client_row)
    portal = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert portal.status_code == 200, portal.text
    portal_payload = portal.json()

    assert set(portal_payload) - set(PORTAL_ONLY_FIELDS) == set(lo_payload)
    assert _without_send_time(portal_payload) == _without_send_time(lo_payload)
    # The recommendation sentence is the stored draft text, not a generic one.
    assert package.recommendation_text
    assert portal_payload["recommendation"]["text"] == package.recommendation_text
    if persona == "kathleen_mcreynolds":
        assert lo_payload["matches"], "TBD persona's matches are part of the parity check"
