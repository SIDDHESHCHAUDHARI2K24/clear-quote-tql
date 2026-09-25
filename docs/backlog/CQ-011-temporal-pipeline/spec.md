# CQ-011 Temporal pipeline

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-009, CQ-012, CQ-013 |
| Kaneo task | CQ-011 in Kaneo (task id `pkzooifqak5acpcetl7y3xwy`) |
| Branch | `cq-011-temporal-pipeline` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

Every application — imported by an LO or submitted through the borrower apply wizard — runs the same automated chain (import → verify → enrich → validate → auto-price → draft quote set) as one Temporal workflow, with retries, a visible per-application run history, and a way to resume after the LO fixes a flag.

## Scope

1. `ApplicationPipelineWorkflow`: module path, task queue, workflow id convention.
2. Six activities (import, verify, enrich, validate, auto-price, draft quote set): names, inputs/outputs, and which stage service function each wraps.
3. Status transitions per stage, matching the `application_status` state diagram in `system-design.md`.
4. Retry policy per activity, including which errors are non-retryable and drive `needs_attention` immediately.
5. Resume-after-fix mechanics: a `resume` signal re-enters the same workflow run (decision below).
6. `activity_events` rows written per stage with pinned `type` values.
7. Worker entrypoint (`python -m app.workflows.worker`) and a `make worker` target.
8. Two API endpoints that start and resume the pipeline.
9. Tests against `temporalio.testing.WorkflowEnvironment` covering all 10 personas' expected end status.

## Out of scope

- Verification rule definitions and the `flags` schema (CQ-012) — the `verify_application` activity only calls CQ-012's `run_and_persist` service function.
- Enrichment/pricing calculation logic, OB required-field list and the DSCR two-pass loop itself (CQ-013) — activities only call CQ-013's service functions.
- Mock adapter behaviour, latency and failure toggles (CQ-009).
- Seed data, persona fixtures and `demo-reset`'s synchronous stage calls (CQ-010) — this item's workflow tests define their own literal persona fixtures (see Notes) rather than importing `seed/`, since CQ-011 does not depend on CQ-010.
- `applications` / `flags` / `activity_events` / `application_status` enum table and column definitions (CQ-007) — this item assumes the enum member names in the state diagram below and writes rows against them.
- The LO "resolve flag" UI action and the "force adapter failure" admin toggle UI (CQ-028, CQ-029) — they call this item's `/pipeline/resume` endpoint and forced-failure env toggle respectively, but their UI is out of scope here.
- The stale-quote scheduled job (CQ-030) — `stale` is never a workflow-driven transition.
- The borrower apply wizard and LOS-import UI that create the `applications` row in the first place (CQ-016, CQ-032) — this item only defines the hook they must call after insert (Decision D2).

## References

- `docs/design/system-design.md` — "Application status machine" (state diagram, this is the binding transition table), "Calculation engine" (DSCR two-pass loop), "Emulated integrations" (OB required-field rejection, forced-failure toggle), "Architecture" → Jobs row ("Temporal gives retries, resume-from-failed-stage and a visible run history per application"), repo layout (`backend/app/workflows/`).
- `docs/design/data-field-catalog.md` — §5/§6 (OB required fields: `Occupancy`, `LTV`, `AmortizationType`, `IncomeVerificationType`, `PrepaymentPenalty`, `DSCR`), §12 (`activity_events`-style audit fields).
- `AGENTS.md` — project map (`backend/app/workflows/`), money-math rule (activities never compute — they call `quote_engine` via the pricing service).

## Contracts

**Workflow.** `backend/app/workflows/application_pipeline.py::ApplicationPipelineWorkflow`. `run(self, application_id: str) -> str` (returns the final `application_status` value). Task queue `application-pipeline` (constant `APPLICATION_PIPELINE_TASK_QUEUE` in `backend/app/workflows/constants.py`, overridable via env `TEMPORAL_TASK_QUEUE`). Workflow id: `f"application-{application_id}"`. Start uses `WorkflowIDReusePolicy.REJECT_DUPLICATE` (one run per application, ever — resume reuses the existing run via signal, it never starts a second one).

**Activities** (`backend/app/workflows/activities.py`, `@activity.defn(name=...)`, each a thin wrapper with no business logic of its own):

| Activity name | Wraps | Input → Output |
| --- | --- | --- |
| `import_application` | `applications.service.import_from_los` | `application_id` → `ImportResult` (parties, housing, liabilities, employment, assets written) |
| `verify_application` | `applications.verification.service.run_and_persist` (CQ-012's actual name; returns `list[RuleResult]`) | `application_id` → `VerificationResult(rule_results: list[RuleResult], passed: bool)` — the activity wraps CQ-012's return value and derives `passed` (`True` unless any `RuleResult` has `severity == FlagSeverity.blocking and passed == False`); this is a pure derivation from CQ-012's own severity semantics, not a second rule engine |
| `enrich_application` | `pricing.enrichment.service.enrich_pricing_fields` (CQ-013's actual name) | `application_id` → `EnrichmentResult` (field_values written with source) |
| `validate_pricing_inputs` | `pricing.enrichment.service.validate_ob_required_fields` (CQ-013 — builds the OB request via `scenarios/ob_request.py::build_ob_search_request` and calls `PricingClient.get_priced_products` once to surface validation only) | `application_id` → raises `PricingValidationError(missing_fields)` (CQ-009, from `app.integrations.common.errors`) or returns `True` |
| `auto_price_application` | `pricing.scenarios.service.auto_price` (CQ-013, DSCR two-pass loop, Save & AutoQuote) | `application_id` → `PricingResult(scenario_ids, quote_ids)` |
| `draft_quote_set` | `quotes.builder.service.draft_default_quote_set` (CQ-013/CQ-018's default scenario sets) | `application_id, PricingResult` → `QuoteSetResult(quote_ids)` |

**Status transitions** (binding — matches the state diagram exactly):

| Activity | On success | On failure |
| --- | --- | --- |
| `import_application` | `intake → verifying` | workflow fails (no LOS record — treated as a setup error, not a demo path) |
| `verify_application` | `verifying → ready_to_price` (no open flags) | `verifying → needs_attention` (flags open) |
| `enrich_application` | unchanged (`ready_to_price`) | `ready_to_price → needs_attention` ("Cannot price: {adapter} unavailable") |
| `validate_pricing_inputs` | unchanged | `ready_to_price → needs_attention` ("Cannot price: missing {Field}") |
| `auto_price_application` | unchanged | `ready_to_price → needs_attention` ("Cannot price: {reason}") |
| `draft_quote_set` | `ready_to_price → priced` (workflow's terminal status) | `ready_to_price → needs_attention` |

`sent`, `viewed`, `option_selected`, `inquiry` and `stale` are never set by this workflow — they are LO/borrower actions (CQ-019, CQ-020, CQ-024) and the stale job (CQ-030). `priced` is this workflow's only success terminus; CQ-010's "Seed end status" for Grace/Luis is `priced` plus a fixture layer on top (see CQ-010 Decision D2), not a workflow output.

**Retry policy.** `RetryPolicy(initial_interval=1s, backoff_coefficient=2.0, maximum_interval=30s, maximum_attempts=3)` on `import_application` and `enrich_application` (transient mock-adapter latency). `non_retryable_error_types=["PricingValidationError", "ProviderUnavailableError"]` (both from CQ-009's `app.integrations.common.errors`, subclasses of CQ-004's `IntegrationError`/`AppError`) on all activities — these are business/demo-control outcomes, not transient faults, so the workflow catches them on the first attempt, writes the flag/message, and transitions to `needs_attention` immediately (this is what makes CQ-029's forced-failure toggle show `needs_attention` live). `verify_application` never raises for a failed check — the activity wraps CQ-012's `run_and_persist` result into `VerificationResult(rule_results, passed=False)`, a normal value, not an exception; the workflow reads `passed` and transitions to `needs_attention` itself, so there is no `VerificationFailedError` to retry or not.

**Resume mechanics (decision).** `needs_attention` parks the workflow: `await workflow.wait_condition(lambda: self._resume_requested)` inside a loop, unset by a `@workflow.signal def resume(self) -> None`. On signal, the workflow always re-enters at `verify_application` and re-runs the full `verify → enrich → validate → auto_price → draft_quote_set` chain — never a partial "resume from the exact failed activity". Rejected alternative: restarting a new workflow run with a `from_stage` param, which would fragment "one workflow per application" into multiple runs and lose the single visible history the stack decision calls out. All six activities are idempotent (re-running `verify_application` after a housing-history fix simply re-evaluates rules), so re-running the whole chain costs a few extra mock-adapter calls, not correctness.

**API.** `POST /applications/{id}/pipeline/start` — starts the workflow (id `application-{id}`, `REJECT_DUPLICATE`); no-ops (200, not an error) if a run already exists. Called automatically, in-process, by the application-creation service function right after the `applications` row commits (both the LOS-import path and the apply-wizard path go through that same creation function — CQ-016/CQ-032 call it, they do not call this endpoint directly). `POST /applications/{id}/pipeline/resume` — sends the `resume` signal; returns a named error `WorkflowNotRunningError` (404) if no run is active for that id.

**activity_events types** (one row per stage, `actor = "system"`): `pipeline.imported`, `pipeline.verified`, `pipeline.flagged`, `pipeline.enriched`, `pipeline.pricing_blocked`, `pipeline.priced`, `pipeline.resumed`.

**Worker.** `backend/app/workflows/worker.py`, `python -m app.workflows.worker` connects to `TEMPORAL_ADDRESS` (default `localhost:7233`), registers `ApplicationPipelineWorkflow` and all six activities on `application-pipeline`. Make target `make worker` runs `cd backend && uv run python -m app.workflows.worker` (added to the existing root Makefile from CQ-002; this item does not touch Docker Compose — that stays CQ-003's).

## Persona → expected pipeline status (condensed from CQ-010's full table; this item's tests define their own literal fixtures for these 10 cases so it stays independent of `seed/`)

| Persona | Market/occupancy | Defect | Expected workflow-terminal status |
| --- | --- | --- | --- |
| Marcus Hale | STR, Tampa FL | none | `priced` |
| Kathleen McReynolds | LTR, TBD property | none | `priced` |
| Priya Nair | Primary, Carmel IN | none | `priced` |
| Daniel Ortiz | Primary, Indianapolis IN | none | `priced` |
| Sam Reed / Asheville Holdings LLC | STR, Asheville NC | none | `priced` |
| Tom & Lisa Brandt | LTR, Cleveland OH | none | `priced` |
| Aisha Coleman | LTR, Columbus OH | `occupancy_type` null in LOS | `needs_attention`, message "Cannot price: missing Occupancy" |
| Ben Ford | Primary, Fort Wayne IN | 14 mo housing, no prior address | `needs_attention`, housing-history flag |
| Grace Kim | LTR, Denver CO | none | `priced` (CQ-010 advances it to `sent` afterward, outside this workflow) |
| Luis Romero | STR, Scottsdale AZ | none | `priced` (CQ-010 advances it to `option_selected` afterward, outside this workflow) |

## Acceptance criteria

- [ ] AC1 — Running `ApplicationPipelineWorkflow` against each of the 10 persona fixtures above in `temporalio.testing.WorkflowEnvironment` ends at the "Expected workflow-terminal status" column, including the exact flag message for Aisha and a housing-history flag for Ben (roadmap exit check). Test: `backend/app/workflows/tests/test_application_pipeline_personas.py` (parametrized, 10 cases).
- [ ] AC2 — Each activity is a thin wrapper: a unit test replaces the underlying service function with a spy and asserts the activity calls it exactly once with `application_id` and returns its result unchanged — except `verify_application`, which additionally derives `passed` from the returned `list[RuleResult]` per the pure rule in its activity-table row above (asserted by a dedicated test, not the generic spy test). Test: `backend/app/workflows/tests/test_activities_are_thin_wrappers.py`.
- [ ] AC3 — `import_application` and `enrich_application` retry up to 3 times on a transient error and give up (surfacing to the workflow) on the 3rd; `PricingValidationError` and `ProviderUnavailableError` are never retried. Test: `backend/app/workflows/tests/test_retry_policy.py`.
- [ ] AC4 — Sending `resume` to a workflow parked in `needs_attention` (Ben Ford's fixture, housing fixed) re-enters at `verify_application` and reaches `priced` without re-running `import_application` a second time (asserted via a call-count spy). Test: `backend/app/workflows/tests/test_resume_signal.py`.
- [ ] AC5 — Exactly one `activity_events` row per completed stage, with the pinned `type` values, for both the Marcus Hale happy path (6 rows) and the Aisha Coleman flagged path (import, verified, enriched, pricing_blocked). Test: `backend/app/workflows/tests/test_activity_events_sequence.py`.
- [ ] AC6 — `python -m app.workflows.worker` starts, connects to Temporal, and logs that `ApplicationPipelineWorkflow` and all six activities are registered on `application-pipeline`; `make worker` runs the same command. Test: `backend/app/workflows/tests/test_worker_registration.py` (starts the worker against `WorkflowEnvironment`, asserts registration).
- [ ] AC7 — `POST /applications/{id}/pipeline/start` is idempotent (second call returns 200 without starting a second run) and `POST /applications/{id}/pipeline/resume` returns `WorkflowNotRunningError` (404) when no run exists. Test: `backend/app/features/applications/tests/test_pipeline_endpoints.py`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Workflow (Temporal test env) | `pytest backend/app/workflows/tests/test_application_pipeline_personas.py` |
| AC2 | Unit | `pytest backend/app/workflows/tests/test_activities_are_thin_wrappers.py` |
| AC3 | Workflow (Temporal test env) | `pytest backend/app/workflows/tests/test_retry_policy.py` |
| AC4 | Workflow (Temporal test env) | `pytest backend/app/workflows/tests/test_resume_signal.py` |
| AC5 | Workflow (Temporal test env) | `pytest backend/app/workflows/tests/test_activity_events_sequence.py` |
| AC6 | Integration | `pytest backend/app/workflows/tests/test_worker_registration.py` |
| AC7 | API | `pytest backend/app/features/applications/tests/test_pipeline_endpoints.py` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: activity names, task queue, workflow id convention and `activity_events` type strings above are the contract CQ-016 (workspace header), CQ-028 (resolve-flag resume) and CQ-029 (forced-failure demo) build against — do not rename without a `Decision:` note and a Kaneo comment.
- Decision: this item's own persona fixtures are literal Python dicts inside the test file, not an import of `seed/personas/*.yaml` (CQ-010) — CQ-011 does not depend on CQ-010 per the header table, and wave ordering only guarantees CQ-010 exists *before* CQ-011, not that CQ-011 may depend on it. If the two persona tables ever drift, treat CQ-010's as the source of truth (it owns "seed data") and fix this item's fixtures to match.
- CQ-012 and CQ-013 are this item's real dependencies; if their service function names differ from the ones pinned above when this item starts, treat the difference as a brainstorm-stage gap check and log a `Decision:` reconciling the name (do not silently rename here without recording why).
- Error names (`PricingValidationError`, `ProviderUnavailableError`) match CQ-009's `app.integrations.common.errors` exactly, aligned during the P0/P1 cross-spec consistency pass — do not rename without updating both specs together.
