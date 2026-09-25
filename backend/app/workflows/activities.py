"""Temporal activities for `ApplicationPipelineWorkflow` (spec.md CQ-011
Contracts). Each activity is a thin wrapper over a CQ-012/CQ-013 stage
service function, plus the status transition and the one pinned
`activity_events` row for that stage — both of which have to happen inside
the activity, not the workflow, since only activities may touch the DB
(plan.md #2).

Event-type mapping (plan.md #5 — only 7 pinned strings cover 6 activities'
success/failure outcomes):

| Activity                  | Success             | Failure                  |
|----------------------------|----------------------|---------------------------|
| import_application          | pipeline.imported    | (raises; workflow fails)  |
| verify_application           | pipeline.verified     | pipeline.flagged          |
| enrich_application            | pipeline.enriched      | pipeline.pricing_blocked  |
| validate_pricing_inputs        | pipeline.enriched (reused) | pipeline.pricing_blocked |
| auto_price_application           | pipeline.enriched (reused) | pipeline.pricing_blocked |
| draft_quote_set                    | pipeline.priced        | pipeline.pricing_blocked |
| (resume signal -> record_pipeline_resumed) | pipeline.resumed | n/a |
| load_application_source (P5/P6 E14)        | (no event)       | n/a |
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from app.core.enums import ApplicationSource, ApplicationStatus, FlagSeverity
from app.features.applications.models import Application
from app.features.applications.service import ImportResult, import_from_los
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.schemas import RuleResult
from app.features.applications.verification.service import run_and_persist
from app.features.pricing.enrichment.service import (
    EnrichmentResult,
    enrich_pricing_fields,
    validate_ob_required_fields,
)
from app.features.pricing.scenarios.service import PricingResult, auto_price
from app.features.quotes.builder.service import QuoteSetResult, draft_default_quote_set
from app.integrations.common.errors import PricingValidationError, ProviderUnavailableError
from app.workflows import db as workflow_db
from app.workflows.constants import PipelineStage

_ACTOR_SYSTEM = "system"

_TYPE_IMPORTED = "pipeline.imported"
_TYPE_VERIFIED = "pipeline.verified"
_TYPE_FLAGGED = "pipeline.flagged"
_TYPE_ENRICHED = "pipeline.enriched"
_TYPE_PRICING_BLOCKED = "pipeline.pricing_blocked"
_TYPE_PRICED = "pipeline.priced"
_TYPE_RESUMED = "pipeline.resumed"


@dataclass(frozen=True)
class VerificationResult:
    """CQ-011's own derived result (spec.md Contracts, `verify_application`)
    — wraps CQ-012's `VerificationRunResult` and adds the pure `passed`
    derivation: `True` unless any `RuleResult` has
    `severity == FlagSeverity.BLOCKING and passed == False`."""

    rule_results: list[RuleResult]
    passed: bool


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _dataclass_payload(obj: Any) -> dict[str, Any]:
    return {k: _json_safe(v) for k, v in dataclasses.asdict(obj).items()}


async def _write_event(
    db: AsyncSession, application_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> None:
    db.add(
        ActivityEvent(
            application_id=application_id,
            actor=_ACTOR_SYSTEM,
            type=event_type,
            payload=payload,
            at=datetime.now(UTC),
        )
    )
    await db.commit()


async def _transition_status(
    db: AsyncSession, application_id: uuid.UUID, status: ApplicationStatus
) -> None:
    application = await db.get(Application, application_id)
    if application is not None:
        application.status = status
        await db.flush()


async def _set_stage(
    db: AsyncSession, application_id: uuid.UUID, stage: PipelineStage | ApplicationStatus
) -> None:
    """CQ-016 (D7): writes `applications.last_pipeline_stage`, committing
    immediately so a concurrent `GET .../summary` poll sees progress while
    this activity is still running -- same "commit as you go" pattern as
    `_write_event`/`_transition_status`. `stage` is either one of the 6
    running `PipelineStage` names (written at the start of an activity) or
    a terminal `ApplicationStatus` (`NEEDS_ATTENTION`/`PRICED`, written once
    the chain stops or finishes -- see `workflows/constants.py`)."""
    application = await db.get(Application, application_id)
    if application is not None:
        application.last_pipeline_stage = stage.value
        await db.commit()


def _needs_attention_message(exc: Exception) -> str:
    """Formats the `needs_attention` message per spec.md's per-activity
    failure-message column."""
    if isinstance(exc, ProviderUnavailableError):
        return f"Cannot price: {exc.adapter} unavailable"
    message = getattr(exc, "message", None)
    return str(message) if message else f"Cannot price: {exc}"


async def _fail_pricing_stage(db: AsyncSession, application_id: uuid.UUID, exc: Exception) -> None:
    """Shared failure path for `enrich_application`, `validate_pricing_
    inputs`, `auto_price_application` and `draft_quote_set`: transitions
    `ready_to_price -> needs_attention` and writes the one pinned
    `pipeline.pricing_blocked` row, then the caller re-raises `exc` so
    Temporal's `non_retryable_error_types` surfaces it to the workflow
    (spec.md "Retry policy")."""
    message = _needs_attention_message(exc)
    await _transition_status(db, application_id, ApplicationStatus.NEEDS_ATTENTION)
    await _set_stage(db, application_id, ApplicationStatus.NEEDS_ATTENTION)
    await _write_event(db, application_id, _TYPE_PRICING_BLOCKED, {"message": message})


@activity.defn(name="load_application_source")
async def load_application_source(application_id: str) -> str:
    """P5/P6 foundation (E14): returns `applications.source` (`"los"` or
    `"portal"`) so the workflow can skip `import_application` for a portal
    application (CQ-032), whose parties/property/employment/assets were
    written locally at submit and have no LOS record to import. Read-only:
    writes no status, stage or event. A missing row reads as `los`, so the
    import stage reports the setup error exactly as before."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        application = await db.get(Application, app_uuid)
        if application is None:
            return ApplicationSource.LOS.value
        return ApplicationSource(application.source).value


@activity.defn(name="import_application")
async def import_application(application_id: str) -> ImportResult:
    """Wraps CQ-010's `applications.service.import_from_los` (`application_
    id -> ImportResult`). plan.md #3/#10 (superseded): CQ-010 has since
    merged, so this imports the real function/type at module scope instead
    of the lazy-import + `Any` workaround used before the merge.

    Does not catch anything to change *status* or control flow: a failed
    import (no LOS record) is a setup error, not a demo path (spec.md) —
    the workflow still lets it fail the run. It does still write a
    terminal `last_pipeline_stage` (CQ-016 code-review fix) before
    re-raising, so `applications.last_pipeline_stage` doesn't get stuck at
    `"importing"` forever -- without this, the workspace summary's polling
    banner (spec.md CQ-016 AC7: "disappears when the workflow ends") would
    never stop polling for an application whose import fails.
    """
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.IMPORTING)
        try:
            result = await import_from_los(app_uuid, db)
        except Exception:
            await _set_stage(db, app_uuid, ApplicationStatus.NEEDS_ATTENTION)
            raise
        await _write_event(db, app_uuid, _TYPE_IMPORTED, _dataclass_payload(result))
        return result


@activity.defn(name="verify_application")
async def verify_application(application_id: str) -> VerificationResult:
    """Wraps CQ-012's `verification.service.run_and_persist` (`application_
    id -> VerificationRunResult`). `run_and_persist` never raises for a
    failed check (spec.md) — this activity derives `passed` itself and
    transitions status, since CQ-012 never touches `applications.status`
    (see that module's own docstring)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.VERIFYING)
        # CQ-028a review: no commit here, so the flags and the status below
        # land in one transaction under the application lock; an LO edit's
        # re-verify then sees both or neither.
        run_result = await run_and_persist(app_uuid, db, commit=False)
        passed = not any(
            result.severity is FlagSeverity.BLOCKING and not result.passed
            for result in run_result.rule_results
        )
        status = ApplicationStatus.READY_TO_PRICE if passed else ApplicationStatus.NEEDS_ATTENTION
        event_type = _TYPE_VERIFIED if passed else _TYPE_FLAGGED
        failed_rules = [
            result.rule_id
            for result in run_result.rule_results
            if result.severity is FlagSeverity.BLOCKING and not result.passed
        ]
        await _transition_status(db, app_uuid, status)
        if not passed:
            await _set_stage(db, app_uuid, ApplicationStatus.NEEDS_ATTENTION)
        await _write_event(
            db,
            app_uuid,
            event_type,
            {"rule_count": len(run_result.rule_results), "failed_rules": failed_rules},
        )
        return VerificationResult(rule_results=run_result.rule_results, passed=passed)


@activity.defn(name="enrich_application")
async def enrich_application(application_id: str) -> EnrichmentResult:
    """Wraps CQ-013's `pricing.enrichment.service.enrich_pricing_fields`
    (`db, application_id -> EnrichmentResult`)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.ENRICHING)
        try:
            result = await enrich_pricing_fields(db, app_uuid)
        except (PricingValidationError, ProviderUnavailableError) as exc:
            await _fail_pricing_stage(db, app_uuid, exc)
            raise
        await _write_event(db, app_uuid, _TYPE_ENRICHED, _dataclass_payload(result))
        return result


@activity.defn(name="validate_pricing_inputs")
async def validate_pricing_inputs(application_id: str) -> bool:
    """Wraps CQ-013's `pricing.enrichment.service.validate_ob_required_
    fields` (`db, application_id -> bool`, raises `PricingValidationError`
    on missing OB-required fields)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.VALIDATING)
        try:
            result = await validate_ob_required_fields(db, app_uuid)
        except (PricingValidationError, ProviderUnavailableError) as exc:
            await _fail_pricing_stage(db, app_uuid, exc)
            raise
        await _write_event(db, app_uuid, _TYPE_ENRICHED, {"validated": True})
        return result


@activity.defn(name="auto_price_application")
async def auto_price_application(application_id: str) -> PricingResult:
    """Wraps CQ-013's `pricing.scenarios.service.auto_price` (`db,
    application_id -> PricingResult`)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.PRICING)
        try:
            result = await auto_price(db, app_uuid)
        except (PricingValidationError, ProviderUnavailableError) as exc:
            await _fail_pricing_stage(db, app_uuid, exc)
            raise
        await _write_event(db, app_uuid, _TYPE_ENRICHED, _dataclass_payload(result))
        return result


@activity.defn(name="draft_quote_set")
async def draft_quote_set(application_id: str, pricing_result: PricingResult) -> QuoteSetResult:
    """Wraps CQ-013/CQ-018's `quotes.builder.service.draft_default_quote_
    set` (`db, application_id, pricing_result -> QuoteSetResult`). Success
    is this workflow's only terminal transition (`ready_to_price ->
    priced`)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _set_stage(db, app_uuid, PipelineStage.DRAFTING_QUOTES)
        try:
            result = await draft_default_quote_set(db, app_uuid, pricing_result)
        except (PricingValidationError, ProviderUnavailableError) as exc:
            await _fail_pricing_stage(db, app_uuid, exc)
            raise
        await _transition_status(db, app_uuid, ApplicationStatus.PRICED)
        await _set_stage(db, app_uuid, ApplicationStatus.PRICED)
        await _write_event(db, app_uuid, _TYPE_PRICED, _dataclass_payload(result))
        return result


@activity.defn(name="record_pipeline_resumed")
async def record_pipeline_resumed(application_id: str) -> None:
    """Writes the pinned `pipeline.resumed` row when a `resume` signal is
    processed (spec.md "activity_events types"). Not one of the six named
    "stage" activities in the Contracts table, but DB I/O must still happen
    inside an activity, never the workflow itself (Temporal determinism)."""
    app_uuid = uuid.UUID(application_id)
    async with workflow_db.session_factory() as db:
        await _write_event(db, app_uuid, _TYPE_RESUMED, {})
