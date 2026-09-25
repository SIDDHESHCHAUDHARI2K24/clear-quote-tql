# CQ-011 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `run_and_persist`/CQ-013 function parameter order | Read the real merged signatures instead of trusting the header summary: `run_and_persist(application_id, db)` (CQ-012, app_id first), `enrich_pricing_fields(db, application_id)`, `validate_ob_required_fields(db, application_id)`, `auto_price(db, application_id)`, `draft_default_quote_set(db, application_id, pricing_result)` (all CQ-013, db first). `import_from_los(application_id, db)` (CQ-010 branch, app_id first). Activities call each with its own real order, positionally, verified against source. |
| 2 | Decision | DB access from activities | Temporal workflow code must stay deterministic/side-effect-free; only activities do I/O. Every activity opens its own `AsyncSession` via `app.workflows.db.session_factory()` (module-level, monkeypatchable — production defaults to `app.core.db.AsyncSessionLocal`; tests bind it to the test's own open connection so writes are visible and roll back with `db_session`). Status transitions and `activity_events` rows are written **inside the activity** (after calling the wrapped service function), not by the workflow — the workflow only orchestrates control flow (which activity to call next, when to catch a non-retryable failure and pause). Spec's "the workflow catches... writes the flag/message" is read as "the pipeline" collectively; only activities can touch Postgres. |
| 3 | Decision | `import_application` vs CQ-010 not merged yet | `app.features.applications.service` does not exist on this branch yet. `import_application` does a **lazy import inside the function body** (`from app.features.applications.service import import_from_los`) so `app.workflows.activities` still imports cleanly today. Tests that exercise `import_application` install a fake module into `sys.modules["app.features.applications.service"]` (via a fixture) *only if the real one isn't already importable* — once CQ-010 merges, the fixture detects the real module and monkeypatches its `import_from_los` attribute directly instead. No test code changes needed after merge. |
| 4 | Decision | Aisha Coleman's "occupancy_type null in LOS" can't be reproduced via real code | `applications.occupancy` is a NOT NULL column, and CQ-013's `build_ob_search_request` always derives OB's `Occupancy` as a literal `"PrimaryResidence"`/`"InvestmentProperty"` string — never `None` — so `PricingValidationError(["Occupancy"])` can never actually fire through legitimate application state. Aisha's persona test monkeypatches `app.features.pricing.enrichment.service.build_ob_search_request` for her one `application_id` only (falling back to the real function for every other id) so it returns a request with `Occupancy=None`, reproducing the exact `PricingValidationError`/"Cannot price: missing Occupancy" path through the *real* `validate_ob_required_fields` → `MockPricingClient.get_priced_products` code, without touching CQ-013 production code (out of scope here). Flagging for CQ-010/CQ-013 owners in case a future real defect-injection mechanism is wanted. |
| 5 | Decision | `activity_events` type mapping (only 7 pinned strings for 6 activities × success/failure) | `import_application`→`pipeline.imported` (failure: none, workflow just fails). `verify_application`→`pipeline.verified` / `pipeline.flagged`. `enrich_application`, `validate_pricing_inputs`, `auto_price_application`→`pipeline.enriched` on success (reused — none of these three change status, so they share one "still getting ready" milestone type), `pipeline.pricing_blocked` on failure (shared generic pricing-stage-blocked type — spec's pinned list has no per-activity failure type for enrich/validate/auto_price/draft). `draft_quote_set`→`pipeline.priced` on success (this is the one status flip to the terminal `priced` value), `pipeline.pricing_blocked` on failure. Resume signal → one `pipeline.resumed` row from a small internal `record_pipeline_resumed` activity (not one of the six contract activities, but DB writes must happen in an activity). This satisfies AC5 ("exactly one row per completed stage", 6 rows for Marcus, the literal 4-type sequence for Aisha) using only the pinned vocabulary (no new type strings), at the cost of "enriched" appearing up to 3x in a full happy path. Flagging in post-dev.md follow-ups for CQ-016/CQ-028/CQ-029 owners — this is a small gap, decided with data in hand, not a blocking one. |
| 6 | Decision | Task queue constant | `.env.example`/CI already pin `TEMPORAL_TASK_QUEUE=clear-quote-pipeline` via `Settings.temporal_task_queue` (CQ-002/003), diverging from spec's illustrative default `"application-pipeline"`. `APPLICATION_PIPELINE_TASK_QUEUE` (`app/workflows/constants.py`) reads `get_settings().temporal_task_queue` rather than hardcoding a second, conflicting literal — still "overridable via env `TEMPORAL_TASK_QUEUE`" per spec, just via the setting that already owns that env var. |
| 7 | Decision | Retry policies | `import_application`/`enrich_application`: `RetryPolicy(initial_interval=1s, backoff_coefficient=2.0, maximum_interval=30s, maximum_attempts=3, non_retryable_error_types=["PricingValidationError","ProviderUnavailableError"])`. The other four (`verify_application`, `validate_pricing_inputs`, `auto_price_application`, `draft_quote_set`): same `non_retryable_error_types`, default other fields (spec only pins the tight schedule to import/enrich). Both live in `app/workflows/retry_policies.py`, imported by both the workflow and its tests so tests exercise the real configured objects. |
| 8 | Decision | Temporal client for API endpoints | `app/workflows/client.py::get_temporal_client()` — a cached module-level `Client`, FastAPI-injectable, overridden in tests via `app.dependency_overrides` to hand out the `WorkflowEnvironment`'s own client. |
| 9 | Decision | Pipeline endpoints auth | Spec doesn't mention an LO-auth dependency for `/pipeline/start` or `/pipeline/resume` (unlike the pricing routes' `get_current_lo_stub`), so neither route requires one. |
| 10 | Decision | `import_application`'s return-type annotation | Typed `Any` for now (with a comment) since `ImportResult` lives in the not-yet-merged `app.features.applications.service` and importing it even under `TYPE_CHECKING` would break `mypy` today. Follow-up once CQ-010 merges: tighten to the real `ImportResult` type. |
| 11 | Decision | Persona DB fixtures | Not seed-data dependent (per spec). A local `backend/app/workflows/tests/conftest.py` `make_persona_application` fixture builds the full row graph (User/Client/Application/Property/ApplicationParty/HousingHistory/Employment/Liability/Asset + a pre-seeded `field_values` row for `representative_fico`, since no activity in this 6-stage pipeline ever writes that field — a real credit pull is out of scope) plus provider seed rows (`ProviderTaxRate`, `ProviderRateSheet`, and `ProviderRent`/`ProviderStrRevenue` for LTR/STR) mirroring the exact fixture recipe already used by `pricing/scenarios/tests/test_default_scenarios_{primary,investment}.py`, so `enrich_application`/`auto_price_application` succeed for real (not mocked) on the 8 non-defect personas. |
| 13 | Decision (supersedes #4, pending CQ-010 merge) | Orchestrator update 2026-09-25: CQ-010 is being revised before merge — (a) `import_from_los` will also do the CreditClient SOFT pull and write `representative_fico` to `field_values` itself; (b) a new migration makes `applications.occupancy` nullable, and Aisha's real import leaves it `NULL`, so `validate_ob_required_fields` will raise "Cannot price: missing Occupancy" for real with flag `field_key="occupancy_type"` (not the literal `"Occupancy"` this branch's Decision #4 workaround uses today). No production code in this item hardcodes either the field name or the message text — both come straight through from `PricingValidationError.missing_fields`/`.message` via `_needs_attention_message`, so **no code change is needed now**. Kept isolated per the orchestrator's instruction: Aisha's tests still use the Decision #4 `build_ob_search_request` monkeypatch (the only reproducible path on this branch, since occupancy isn't nullable here yet) until CQ-010 merges. Follow-ups queued for the post-merge pass (post-dev.md): (1) replace the monkeypatch-based Aisha fixture in both `test_application_pipeline_personas.py` and `test_activity_events_sequence.py` with a real `occupancy=None` fixture once the migration lands, and update the flag assertion's `field_key` from `"Occupancy"` to `"occupancy_type"`; (2) stop manually seeding `representative_fico` in `make_persona_application` for personas that go through the *real* `import_from_los` (keep it only for tests still using the fake stub) once the real function writes it itself, to avoid a `field_values` unique-constraint collision; (3) add a resume-signal test for persona 7 (Aisha) mirroring `test_resume_signal.py`'s Ben Ford case but exercising the `validate_pricing_inputs` failure → LO sets occupancy → resume → `priced` path, per the orchestrator's explicit ask. |
| 12 | Decision | Activities session bound to test transaction | `backend/app/workflows/tests/conftest.py` provides a `bind_activities_to_test_session` fixture that builds a `session_factory` closure returning new `AsyncSession`s bound to the SAME connection `db_session` uses (`join_transaction_mode="create_savepoint"`), and monkeypatches `app.workflows.db.session_factory` to it — so activity writes inside a `WorkflowEnvironment` run are visible to the test's own assertions afterward and roll back with everything else. |

## Why

Every application needs the same automated import→verify→enrich→validate→price→draft chain, with retries, one visible run per application, and a resume path once an LO fixes a flag. This item wires that as one `ApplicationPipelineWorkflow` per `application_id`, backed by thin activities over CQ-012/CQ-013's already-built stage functions.

## What changes

| Area | Files (create) |
| --- | --- |
| Workflow core | `backend/app/workflows/{constants,db,errors,retry_policies,activities,application_pipeline,worker,client}.py` |
| API | `backend/app/features/applications/router.py`; `backend/app/core/registry.py` (append) |
| Makefile | `worker` target |
| Tests | `backend/app/workflows/tests/{conftest,test_application_pipeline_personas,test_activities_are_thin_wrappers,test_retry_policy,test_resume_signal,test_activity_events_sequence,test_worker_registration}.py`; `backend/app/features/applications/tests/test_pipeline_endpoints.py` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Constants, db session plumbing, errors, retry policies | — | `constants.py`, `db.py`, `errors.py`, `retry_policies.py` | exercised transitively |
| T2 | Activities (6 contract + 1 internal) | T1 | `activities.py` | `test_activities_are_thin_wrappers.py` |
| T3 | Workflow | T1, T2 | `application_pipeline.py` | persona/retry/resume/events tests |
| T4 | Worker entrypoint + Makefile target | T2, T3 | `worker.py`, root `Makefile` | `test_worker_registration.py` |
| T5 | Temporal client dep + API endpoints | T1, T3 | `client.py`, `applications/router.py`, `core/registry.py` | `test_pipeline_endpoints.py` |
| T6 | Test fixtures (persona builder, provider seeds, session-binding) | T1-T3 | `workflows/tests/conftest.py` | all workflow tests |
| T7 | Persona matrix, retry, resume, activity_events tests | T2-T6 | test files | AC1, AC3, AC4, AC5 |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/workflows/tests/test_application_pipeline_personas.py` |
| AC2 | `backend/app/workflows/tests/test_activities_are_thin_wrappers.py` |
| AC3 | `backend/app/workflows/tests/test_retry_policy.py` |
| AC4 | `backend/app/workflows/tests/test_resume_signal.py` |
| AC5 | `backend/app/workflows/tests/test_activity_events_sequence.py` |
| AC6 | `backend/app/workflows/tests/test_worker_registration.py` |
| AC7 | `backend/app/features/applications/tests/test_pipeline_endpoints.py` |

## Progress

- [x] T1 constants/db/errors/retry_policies
- [x] T2 activities
- [x] T3 workflow
- [x] T4 worker + Makefile
- [x] T5 client + endpoints
- [x] T6 test fixtures
- [x] T7 tests (all ACs)
