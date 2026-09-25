"""Row edits + the re-verify/resume hook (AC2; resume decisions)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy

from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.applications.sections.tests.conftest import FakeTemporal
from app.features.applications.timeline.models import ActivityEvent
from app.workflows.constants import application_workflow_id

MakeApp = Callable[..., Awaitable[Application]]

_PRIOR = {
    "street_address": "9 Old Rd",
    "city": "Fort Wayne",
    "state": "in",
    "zip": "46802",
    "housing_status": "rent",
    "residence_years": 0,
    "residence_months": 6,
}


async def _event_types(db: AsyncSession, application_id: uuid.UUID) -> list[str]:
    return list(
        (
            await db.execute(
                select(ActivityEvent.type).where(ActivityEvent.application_id == application_id)
            )
        )
        .scalars()
        .all()
    )


async def test_housing_history_flag(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    fake_temporal: FakeTemporal,
) -> None:
    """AC2 (Ben Ford): a short prior address keeps the flag with the months
    shown; one that reaches 24 months clears it and resumes the pipeline."""
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    url = f"/api/v1/applications/{app.id}/housing_history"

    short = await client.post(url, json=_PRIOR)

    assert short.status_code == 201
    body = short.json()
    assert body["housing"]["total_months"] == 20
    [flag] = body["flags"]
    assert flag["message"] == "Only 20 months of housing history on file; 24 required."
    assert body["resume"] == {"requested": False, "reason": "blocking_flags_remain"}
    added = [r for r in body["records"] if r["manual"]]
    assert len(added) == 1
    assert added[0]["fields"][2]["value"] == "IN"

    enough = await client.post(
        url, json={**_PRIOR, "street_address": "8 Older Rd", "residence_months": 4}
    )

    body = enough.json()
    assert body["housing"] == {"total_months": 24, "required_months": 24, "meets_requirement": True}
    assert body["flags"] == []
    assert body["resume"] == {"requested": True, "reason": "started"}
    assert fake_temporal.starts == [application_workflow_id(str(app.id))]
    types = await _event_types(db_session, app.id)
    assert types.count("row.added") == 2
    assert "flag.resolved" in types
    assert "pipeline.resume_requested" in types


async def test_resume_signals_running_workflow(
    client: AsyncClient, make_app: MakeApp, fake_temporal: FakeTemporal
) -> None:
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    workflow_id = application_workflow_id(str(app.id))
    fake_temporal.running.add(workflow_id)

    body = (
        await client.post(
            f"/api/v1/applications/{app.id}/housing_history",
            json={**_PRIOR, "residence_years": 1},
        )
    ).json()

    assert body["resume"] == {"requested": True, "reason": "resumed"}
    assert fake_temporal.signals == [workflow_id]
    assert fake_temporal.starts == []


async def test_edit_on_priced_app_does_not_resume(
    client: AsyncClient, make_app: MakeApp, fake_temporal: FakeTemporal
) -> None:
    app = await make_app(status=ApplicationStatus.PRICED)

    body = (
        await client.put(
            f"/api/v1/applications/{app.id}/fields/borrower_email", json={"value": "n@e.w"}
        )
    ).json()

    assert body["resume"] == {"requested": False, "reason": "not_needs_attention"}
    assert fake_temporal.signals == fake_temporal.starts == []


async def test_housing_patch_raises_flag_event(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app(housing=[(3, 0)])
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/housing")).json()
    row_id = section["records"][0]["id"]

    body = (
        await client.patch(
            f"/api/v1/applications/{app.id}/housing_history/{row_id}",
            json={"residence_years": 1},
        )
    ).json()

    assert body["housing"]["total_months"] == 12
    assert [f["rule"] for f in body["flags"]] == ["housing_history_24mo"]
    assert "flag.raised" in await _event_types(db_session, app.id)


async def test_add_co_borrower(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession
) -> None:
    app = await make_app()
    url = f"/api/v1/applications/{app.id}/parties"
    payload = {
        "first_name": "Lisa",
        "last_name": "Brandt",
        "ssn": "123-45-6780",
        "dob": "1984-05-19",
    }

    response = await client.post(url, json=payload)

    assert response.status_code == 201
    parties = [r for r in response.json()["records"] if r["kind"] == "party"]
    assert [p["role"] for p in parties] == ["borrower", "co_borrower"]
    assert parties[1]["manual"] is True
    co_first = next(f for f in parties[1]["fields"] if f["field_key"] == "co_borrower_first_name")
    assert co_first["source"] == "lo_entry"
    no_co = next(
        f for f in parties[0]["fields"] if f["field_key"] == "borrower_no_co_applicant_check"
    )
    assert no_co["value"] is False
    assert (await client.post(url, json=payload)).status_code == 409


async def test_patch_liability(client: AsyncClient, make_app: MakeApp) -> None:
    app = await make_app(liabilities=[("Chase", "250.00")])
    section = (await client.get(f"/api/v1/applications/{app.id}/sections/credit")).json()
    row_id = next(r["id"] for r in section["records"] if r["kind"] == "liability")

    body = (
        await client.patch(
            f"/api/v1/applications/{app.id}/liabilities/{row_id}",
            json={"monthly_payment": "199.99"},
        )
    ).json()

    field = next(
        f
        for r in body["records"]
        for f in r["fields"]
        if f["field_key"] == f"liabilities.{row_id}.monthly_payment"
    )
    assert field["value"] == "199.99"
    assert field["overridden"] is True
    other = await client.patch(
        f"/api/v1/applications/{app.id}/liabilities/{uuid.uuid4()}",
        json={"monthly_payment": "1"},
    )
    assert other.status_code == 404


async def test_resume_is_not_repeated_while_pending(
    client: AsyncClient, make_app: MakeApp, db_session: AsyncSession, fake_temporal: FakeTemporal
) -> None:
    """Review minor 8: a second edit before the pipeline picks the resume up
    neither signals again nor logs a second `pipeline.resume_requested`."""
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    base = f"/api/v1/applications/{app.id}"

    first = (
        await client.post(f"{base}/housing_history", json={**_PRIOR, "residence_years": 1})
    ).json()
    second = (await client.put(f"{base}/fields/borrower_email", json={"value": "n@e.w"})).json()

    assert first["resume"] == {"requested": True, "reason": "started"}
    assert second["resume"] == {"requested": True, "reason": "already_requested"}
    assert fake_temporal.starts == [application_workflow_id(str(app.id))]
    assert fake_temporal.signals == []
    types = await _event_types(db_session, app.id)
    assert types.count("pipeline.resume_requested") == 1

    # The started run fails before picking the resume up: not a dead end.
    workflow_id = application_workflow_id(str(app.id))
    fake_temporal.running.discard(workflow_id)
    fake_temporal.closed[workflow_id] = WorkflowExecutionStatus.TERMINATED
    third = (await client.put(f"{base}/fields/borrower_email", json={"value": "x@e.w"})).json()

    assert third["resume"] == {"requested": True, "reason": "started"}
    assert fake_temporal.starts == [workflow_id, workflow_id]


async def test_resume_restarts_failed_run(
    client: AsyncClient, make_app: MakeApp, fake_temporal: FakeTemporal
) -> None:
    """Review minor 6: a failed run is not a dead end; a completed one is."""
    failed = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    failed_id = application_workflow_id(str(failed.id))
    fake_temporal.closed[failed_id] = WorkflowExecutionStatus.FAILED

    body = (
        await client.post(
            f"/api/v1/applications/{failed.id}/housing_history",
            json={**_PRIOR, "residence_years": 1},
        )
    ).json()

    assert body["resume"] == {"requested": True, "reason": "started"}
    assert fake_temporal.starts == [failed_id]
    policy = fake_temporal.start_kwargs[0]["id_reuse_policy"]
    assert policy is WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY

    done = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    fake_temporal.closed[application_workflow_id(str(done.id))] = WorkflowExecutionStatus.COMPLETED
    body = (
        await client.post(
            f"/api/v1/applications/{done.id}/housing_history",
            json={**_PRIOR, "residence_years": 1},
        )
    ).json()

    assert body["resume"] == {"requested": False, "reason": "workflow_closed"}
    assert fake_temporal.starts == [failed_id]
