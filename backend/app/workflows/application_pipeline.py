"""`ApplicationPipelineWorkflow`: import -> verify -> enrich -> validate ->
auto-price -> draft quote set, one Temporal workflow per application
(spec.md CQ-011 Contracts).
"""

from __future__ import annotations

from temporalio import workflow
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    # CQ-012/013's dataclasses (`PricingResult`, `QuoteSetResult`, ...) live
    # in modules that use `from __future__ import annotations`, so Temporal
    # resolves their `list[uuid.UUID]`-style field forward-refs via
    # `get_type_hints()` at workflow-side decode time, against *that
    # module's own* globals. `imports_passed_through()` only registers a
    # module in the sandbox's passthrough-aware registry for imports that
    # happen textually inside this block -- it does not propagate through
    # `app.workflows.activities`'s own internal imports -- so without an
    # explicit import here the lookup misses and raises `NameError: uuid`.
    # Importing them here (even unused) is what fixes it.
    import app.features.pricing.enrichment.service  # noqa: F401
    import app.features.pricing.scenarios.service  # noqa: F401
    import app.features.quotes.builder.service  # noqa: F401
    from app.core.enums import ApplicationStatus
    from app.workflows.activities import (
        auto_price_application,
        draft_quote_set,
        enrich_application,
        import_application,
        record_pipeline_resumed,
        validate_pricing_inputs,
        verify_application,
    )
    from app.workflows.retry_policies import (
        ACTIVITY_TIMEOUT,
        DEFAULT_RETRY_POLICY,
        IMPORT_ENRICH_RETRY_POLICY,
    )


@workflow.defn
class ApplicationPipelineWorkflow:
    def __init__(self) -> None:
        self._resume_requested = False

    @workflow.signal
    def resume(self) -> None:
        self._resume_requested = True

    async def _run_pricing_chain(self, application_id: str) -> bool:
        """Runs verify -> enrich -> validate -> auto_price -> draft_quote_
        set. Returns `True` once the chain reaches `priced`, `False` if it
        stopped at `needs_attention` — either `verify_application`'s own
        blocking flags, or a non-retryable pricing-stage failure. Both
        cases have already written status + the one pinned `activity_
        events` row from inside the activity that stopped the chain
        (plan.md #2) — this method only decides whether to keep going.
        """
        verification = await workflow.execute_activity(
            verify_application,
            application_id,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        if not verification.passed:
            return False

        try:
            await workflow.execute_activity(
                enrich_application,
                application_id,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=IMPORT_ENRICH_RETRY_POLICY,
            )
            await workflow.execute_activity(
                validate_pricing_inputs,
                application_id,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            pricing_result = await workflow.execute_activity(
                auto_price_application,
                application_id,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            await workflow.execute_activity(
                draft_quote_set,
                args=[application_id, pricing_result],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
        except ActivityError:
            # Non-retryable PricingValidationError/ProviderUnavailableError:
            # the failing activity already wrote needs_attention + its one
            # pipeline.pricing_blocked row (spec.md "Retry policy").
            return False
        return True

    @workflow.run
    async def run(self, application_id: str) -> str:
        # Not caught: a failed import (no LOS record) is a setup error, not
        # a demo path (spec.md) -- the whole workflow run fails.
        await workflow.execute_activity(
            import_application,
            application_id,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=IMPORT_ENRICH_RETRY_POLICY,
        )

        reached_priced = await self._run_pricing_chain(application_id)
        while not reached_priced:
            self._resume_requested = False
            await workflow.wait_condition(lambda: self._resume_requested)
            await workflow.execute_activity(
                record_pipeline_resumed,
                application_id,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            reached_priced = await self._run_pricing_chain(application_id)

        return ApplicationStatus.PRICED.value
