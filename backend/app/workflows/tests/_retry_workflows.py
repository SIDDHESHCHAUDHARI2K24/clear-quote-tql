"""Tiny throwaway single-activity workflows for `test_retry_policy.py`.

Kept in their own module (mirroring `application_pipeline.py`'s own
pattern) so the Temporal sandbox's re-import validation only has to trace
`temporalio`/`app.workflows.activities`/`app.workflows.retry_policies` —
not the whole test file's imports (pytest, SQLAlchemy, etc.), which trip
the sandbox's restricted-module checks.
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import enrich_application, import_application
    from app.workflows.retry_policies import ACTIVITY_TIMEOUT, IMPORT_ENRICH_RETRY_POLICY


@workflow.defn
class ImportRetryWorkflow:
    @workflow.run
    async def run(self, application_id: str) -> None:
        await workflow.execute_activity(
            import_application,
            application_id,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=IMPORT_ENRICH_RETRY_POLICY,
        )


@workflow.defn
class EnrichRetryWorkflow:
    @workflow.run
    async def run(self, application_id: str) -> None:
        await workflow.execute_activity(
            enrich_application,
            application_id,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=IMPORT_ENRICH_RETRY_POLICY,
        )
