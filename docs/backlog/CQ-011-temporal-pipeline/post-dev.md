# CQ-011 — Post-development notes

## Summary

Built `ApplicationPipelineWorkflow` (import → verify → enrich → validate → auto-price → draft quote set) as one Temporal workflow per application, with the six contract activities as thin wrappers over CQ-012/CQ-013's stage functions plus status transitions and `activity_events` bookkeeping done inside each activity (Temporal determinism: only activities touch the DB). Added the worker entrypoint (`python -m app.workflows.worker` / `make worker`), the two pipeline API endpoints, and a full `backend/app/workflows/tests/` suite (10-persona matrix, thin-wrapper, retry-policy, resume-signal, activity_events-sequence, worker-registration) plus the endpoint tests, all against `temporalio.testing.WorkflowEnvironment` (no real Temporal needed in CI). CQ-010 merged into `phase-p0-p1` partway through this session (real `import_from_los` + nullable `applications.occupancy`); per the orchestrator's explicit instruction this session stopped short of the post-merge pass (merging `phase-p0-p1`, swapping the fake import stub for the real one, and updating Aisha's fixture) — see Follow-ups and `handoff.md`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Task queue literal `application-pipeline` | `APPLICATION_PIPELINE_TASK_QUEUE = get_settings().temporal_task_queue` (resolves to `clear-quote-pipeline` per `.env.example`/CI) | plan.md Decision #6 — `Settings.temporal_task_queue` already owns that env var; a second hardcoded default would silently diverge. |
| 7 pinned `activity_events` types mapped 1:1 to 6 activities' success+failure | `enrich_application`/`validate_pricing_inputs`/`auto_price_application` all write `pipeline.enriched` on success (reused); all four pricing-stage failures write `pipeline.pricing_blocked` | plan.md Decision #5 — only 4 "success" strings exist in the pinned list for 6 success stages; this satisfies AC5's literal row counts/sequences using only the pinned vocabulary (no new strings). Flagged for CQ-016/028/029 owners. |
| Aisha Coleman: "occupancy_type null in LOS" → `PricingValidationError(["Occupancy"])` | Test-only monkeypatch of `build_ob_search_request` nulling her one application's `Occupancy` field | plan.md Decision #4 — on this branch, before CQ-010 merged, `applications.occupancy` was NOT NULL and the real function never derived `None`. **Superseded by CQ-010's now-merged nullable-occupancy migration** — see Follow-ups; not yet swapped over per the orchestrator's stop-here instruction. |
| `import_application` wraps `import_from_los` | Lazy import inside the activity function, tests install a fake stub via `sys.modules` | plan.md Decision #3 — CQ-010 wasn't merged when this activity was authored. **CQ-010 has since merged**; swapping to the real function is a queued follow-up. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 (10-persona matrix) | Pass | `uv run pytest backend/app/workflows/tests/test_application_pipeline_personas.py -q` → `10 passed`. Uses the pre-merge fake-import stub (Follow-up: rerun against real `import_from_los` once swapped in). |
| AC2 (thin wrappers + verify's `passed` derivation) | Pass | `uv run pytest backend/app/workflows/tests/test_activities_are_thin_wrappers.py -q` → `11 passed`. |
| AC3 (retry policy) | Pass | `uv run pytest backend/app/workflows/tests/test_retry_policy.py -q` → `4 passed`. |
| AC4 (resume signal, Ben Ford) | Pass | `uv run pytest backend/app/workflows/tests/test_resume_signal.py -q` → `1 passed`. |
| AC5 (activity_events sequence) | Pass | `uv run pytest backend/app/workflows/tests/test_activity_events_sequence.py -q` → `2 passed`. |
| AC6 (worker registration) | Pass | `uv run pytest backend/app/workflows/tests/test_worker_registration.py -q` → `1 passed`. Also confirmed against the **real** local Temporal server (see "Real Temporal smoke run" below). |
| AC7 (pipeline endpoints) | Pass | `uv run pytest backend/app/features/applications/tests/test_pipeline_endpoints.py -q` → `3 passed`. |

## Real Temporal smoke run (localhost:7233)

Ran `make worker` (env sourced from local `.env`) against the real local Temporal server started by `make up`:

```
INFO:__main__:Connected to Temporal at localhost:7233 (namespace default)
INFO:__main__:Registered ApplicationPipelineWorkflow and 6 activities (import_application, verify_application, enrich_application, validate_pricing_inputs, auto_price_application, draft_quote_set) on task queue 'clear-quote-pipeline'
```

Then, with that worker running, started a real workflow from a separate client against a random (non-existent) `application_id`: `client.start_workflow(...)` succeeded, the workflow was dispatched to the real worker, `import_application` ran and the workflow failed with `WorkflowFailureError` (expected — no matching row for a random UUID; this was intentionally not run against real `cq_dev` fixture data since that database's migration state belongs to CQ-010/other concurrent branches and this session was told not to touch it). This confirms the full client → real Temporal server → worker → activity round trip works outside the time-skipping test harness.

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (full suite) | `uv run pytest backend -q` | `237 passed` (2 separate full-suite runs; one earlier run also flaked once on `test_resume_reprices_ben_ford_without_reimporting` with a `START_TO_CLOSE` timeout under full-suite load — `ACTIVITY_TIMEOUT` was raised 30s→60s as a resilience margin, and 2 subsequent full-suite runs passed clean). |
| Backend workflows+applications only | `uv run pytest backend/app/workflows backend/app/features/applications/tests -q` | `32 passed` |
| ruff check | `uv run ruff check backend` | `All checks passed!` |
| ruff format --check | `uv run ruff format --check backend` | `221 files already formatted` |
| mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 221 source files` |
| Frontend (`pnpm -r run lint`) | `make lint` | **Fails**: `eslint: command not found` / `node_modules missing` — this worktree's frontend deps were never installed (`pnpm install` not run here); pre-existing environment gap, not caused by this item (no frontend files touched). |
| Pre-existing flake note | — | `backend/app/features/pricing/enrichment/tests/test_enrichment.py::test_enrich_primary_writes_tax_insurance_hoa` deadlocked once in an early full-suite baseline run *before* any CQ-011 code existed (confirmed by re-running that file alone: 6/6 pass) — unrelated to this item. |

### Local environment note

This worktree had no local `.env` (gitignored, per-checkout). Created one from `.env.example` (Fernet key generated fresh, `DEV_LO_ID` matching `backend/conftest.py`'s default) so `uv run pytest`/`make worker`/`make lint` resolve `Settings`. Also created a **dedicated** test database `cq_test_cq011` (same shared Postgres container) and pointed `TEST_DATABASE_URL` at it after finding the shared `cq_test` database's `alembic_version` pointed at a revision (`e7b20ff388a7`) not present in this branch's migration chain — another concurrent branch/agent had run migrations against the shared `cq_test`. Using a dedicated test DB avoids stepping on parallel agents' shared-stack test runs. `cq_dev` has the same foreign revision now (confirmed after CQ-010 merged) — untouched, not needed by this item's automated tests.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |

(Empty — stage 6 review is done afterward by a fresh subagent, per the agent loop.)

## How to test manually

1. `make up` (ensure Temporal is healthy at localhost:7233).
2. `cp .env.example .env`, fill in `FIELD_ENCRYPTION_KEY` (`uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) and `DEV_LO_ID=00000000-0000-0000-0000-000000000001`.
3. `make worker` in one terminal (registers `ApplicationPipelineWorkflow` on `clear-quote-pipeline`).
4. `uv run pytest backend/app/workflows -q` for the full time-skipping suite (no real Temporal needed).

## Follow-ups

- **CQ-010 merged into `phase-p0-p1` mid-session (real `import_from_los` + nullable `applications.occupancy` migration `e7b20ff388a7`).** Per the orchestrator's explicit instruction, this session stopped short of the post-merge pass. Next session should, in order: (1) `git merge phase-p0-p1` into `cq-011-temporal-pipeline`; (2) swap `install_fake_import_from_los`'s default for a thin pass-through to the real `app.features.applications.service.import_from_los` (keep `install_import_from_los` for tests that still want a spy/failure double — AC2/AC3's import tests); (3) update Aisha's fixture in both `test_application_pipeline_personas.py` and `test_activity_events_sequence.py` to set `occupancy=None` for real instead of monkeypatching `build_ob_search_request`, and change the flag `field_key` assertion from `"Occupancy"` to `"occupancy_type"` per the orchestrator's note; (4) add a resume-signal test for persona 7 (Aisha) mirroring `test_resume_signal.py`'s Ben Ford case but exercising `validate_pricing_inputs`'s failure → LO sets occupancy → resume → `priced`; (5) stop manually seeding `representative_fico` in `make_persona_application` for personas that now go through the real `import_from_los` (it does the soft credit pull itself) to avoid a `field_values` unique-constraint collision — keep the manual seed only for tests still using the fake stub; (6) rerun the full 10-persona matrix against the real import path; (7) rerun `make lint`/`uv run pytest backend` once more; (8) push and record the GitHub Actions run id/result here.
- plan.md Decision #5's `activity_events` type reuse (`pipeline.enriched` for 3 different activities) is functionally correct but coarse for a real audit timeline UI — CQ-016/028/029 owners may want finer-grained types later; adding new ones is additive/safe (no rename).
- Frontend `pnpm install` was never run in this worktree — `make lint`'s frontend half can't be verified from here; not blocking since this item touches no frontend files.
