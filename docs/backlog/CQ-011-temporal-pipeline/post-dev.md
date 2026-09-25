# CQ-011 — Post-development notes

## Summary

Built `ApplicationPipelineWorkflow` (import → verify → enrich → validate → auto-price → draft quote set) as one Temporal workflow per application, with the six contract activities as thin wrappers over CQ-012/CQ-013's stage functions plus status transitions and `activity_events` bookkeeping done inside each activity (Temporal determinism: only activities touch the DB). Added the worker entrypoint (`python -m app.workflows.worker` / `make worker`), the two pipeline API endpoints, and a full `backend/app/workflows/tests/` suite (10-persona matrix, thin-wrapper, retry-policy, resume-signal ×2, activity_events-sequence, worker-registration) plus the endpoint tests, all against `temporalio.testing.WorkflowEnvironment` (no real Temporal needed in CI).

This session (handoff 2) completed the post-CQ-010-merge pass the previous session deliberately stopped short of: merged `phase-p0-p1` (CQ-010's real `import_from_los` + nullable `applications.occupancy` migration `e7b20ff388a7`), swapped the fake import stub for the real function everywhere, rebuilt Aisha Coleman's (persona 7) fixture to reproduce her defect for real instead of via a `build_ob_search_request` monkeypatch, added the persona-7 resume test, and fixed two real bugs the merge (and a real-Temporal smoke run) surfaced — see "Deviations/fixes" below. Full persona matrix, `make lint`, `make test` and `make demo-reset` are all green; one real-Temporal smoke run is recorded below.

## Deviations from spec / fixes made this session

| Area | What | Why |
| --- | --- | --- |
| `import_application` | Module-scope import of the real `import_from_los`/`ImportResult` (was: lazy import + `Any` return type, plan.md #3/#10) | CQ-010 merged; the placeholder is no longer needed. plan.md #14. |
| `application_pipeline.py` | Added `import app.features.applications.service` to the `imports_passed_through()` block | Temporal's sandbox couldn't resolve `ImportResult`'s forward-referenced `uuid.UUID` field type across the workflow/activity boundary otherwise (`NameError: uuid`) — same class of fix already applied for CQ-013's dataclasses. plan.md #16. |
| `backend/app/workflows/tests/conftest.py` | `make_persona_application` no longer pre-builds `ApplicationParty`/`HousingHistory`/`Employment`/`Liability`/`Asset`/`representative_fico`; it seeds a `ProviderLosRecord`/`ProviderCreditReport` pair and lets the real `import_from_los` write those rows | Avoids duplicate rows (fixture + real import both writing) and the `field_values` unique-constraint collision the orchestrator flagged. plan.md #14. |
| `install_import_from_los` (test helper) | Monkeypatches `app.workflows.activities.import_from_los` (not just the service module's attribute) | `activities.py` now imports the function by name at module scope; patching only the source module's attribute doesn't reach an already-bound local name. plan.md #14. |
| Aisha Coleman (persona 7) | `make_persona_application(occupancy=None)` reproduces the "occupancy_type null in LOS" defect for real (no `build_ob_search_request` monkeypatch); flag `field_key` assertion changed `"Occupancy"` → `"occupancy_type"` | CQ-010's real nullable-occupancy migration + CQ-013's merged `_FIELD_KEY_OVERRIDES` mapping make the real path reproducible. plan.md #4/#13/#15 (superseded). |
| **`backend/app/workflows/worker.py`** | Added the full "every model module" import list (mirrors `alembic/env.py`'s own, with a comment explaining why) | **Real bug, found via this session's real-Temporal smoke run**: a bare worker process never imports `app.features.clients.models` transitively, so `import_application` failed with `sqlalchemy.exc.NoReferencedTableError` on `applications.client_id`'s FK to `clients` — the table exists in the DB but SQLAlchemy never learned about its mapped class in that process. Pytest never catches this because the test session's own `alembic upgrade head` already imports every model module first, process-wide. plan.md #17. |
| `test_activity_events_sequence.py` / `test_resume_signal.py` | Event-sequence assertions order by `ActivityEvent.at`, not `.created_at` | `created_at` is `server_default=func.now()`, resolved once per Postgres transaction; every event a test's savepoint-bound activity sessions write shares one outer transaction, so ties broke on incidental physical row order and flaked once under full-suite load. `at` is set Python-side per call and strictly increases. plan.md #18. |
| Task queue (carried over) | `APPLICATION_PIPELINE_TASK_QUEUE = get_settings().temporal_task_queue` (`clear-quote-pipeline`), not spec's illustrative `"application-pipeline"` | plan.md #6 (unchanged this session). |
| `activity_events` types (carried over) | `enrich_application`/`validate_pricing_inputs`/`auto_price_application` all write `pipeline.enriched` on success; failures share `pipeline.pricing_blocked` | plan.md #5 (unchanged this session) — flagged for CQ-016/028/029 owners. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 (10-persona matrix) | Pass | `uv run pytest backend/app/workflows/tests/test_application_pipeline_personas.py -q` → `10 passed`, now against the real `import_from_los` for every persona including Aisha. |
| AC2 (thin wrappers + verify's `passed` derivation) | Pass | `uv run pytest backend/app/workflows/tests/test_activities_are_thin_wrappers.py -q` → `11 passed`. |
| AC3 (retry policy) | Pass | `uv run pytest backend/app/workflows/tests/test_retry_policy.py -q` → `4 passed`. |
| AC4 (resume signal) | Pass | `uv run pytest backend/app/workflows/tests/test_resume_signal.py -q` → `2 passed` (Ben Ford's housing-fix case + the new Aisha Coleman occupancy-fix case). |
| AC5 (activity_events sequence) | Pass | `uv run pytest backend/app/workflows/tests/test_activity_events_sequence.py -q` → `2 passed`. |
| AC6 (worker registration) | Pass | `uv run pytest backend/app/workflows/tests/test_worker_registration.py -q` → `1 passed`. Also confirmed against the **real** local Temporal server with the fixed `worker.py` — see below. |
| AC7 (pipeline endpoints) | Pass | `uv run pytest backend/app/features/applications/tests/test_pipeline_endpoints.py -q` → `3 passed`. Also confirmed against a **real** running API server — see below. |

## Real Temporal + real API smoke run (localhost:7233 / localhost:8000)

With the shared stack up (`make up`, Temporal healthy at `localhost:7233`):

1. `make worker` (after the `worker.py` model-registration fix, plan.md #17) — connected and registered cleanly:
   ```
   INFO:__main__:Connected to Temporal at localhost:7233 (namespace default)
   INFO:__main__:Registered ApplicationPipelineWorkflow and 6 activities (import_application, verify_application, enrich_application, validate_pricing_inputs, auto_price_application, draft_quote_set) on task queue 'clear-quote-pipeline'
   ```
2. `make api` (uvicorn on `:8000`).
3. Created one throwaway application row directly in `cq_dev` (a fresh `client`/`application`/`property` plus a self-contained `provider_los_records`/`provider_credit_reports` pair cloned from Marcus Hale's Tampa/Hillsborough/STR persona data, under a unique `SMOKE-*` loan number — reused none of the seeded personas' own rows).
4. `curl -X POST localhost:8000/api/v1/applications/{id}/pipeline/start` → `200 {"workflow_id": "application-<id>", "started": true}`.
5. Within ~6s (real, non-time-skipping Temporal), `applications.status` for that id became `priced`:
   ```
   id                                   | status | occupancy  | strategy
   29e9edc6-39cf-4509-84f0-10cec21811fd | priced | investment | str
   ```
   and `activity_events` had exactly the 6 expected rows in order (`pipeline.imported, pipeline.verified, pipeline.enriched ×3, pipeline.priced`), confirmed via direct SQL against `cq_dev`.
6. Re-`curl`ing `pipeline/start` on the same id returned `{"started": false}` (200) — idempotent, confirmed against the real server, not just `TestClient`.
7. `curl -X POST .../pipeline/resume` on a fresh random (never-started) application id returned `404 {"error": {"code": "WORKFLOW_NOT_RUNNING", ...}}` — confirmed against the real server.
8. Cleanup: stopped both processes (`pkill`), deleted the throwaway `applications`/`clients`/`provider_los_records`/`provider_credit_reports` rows from `cq_dev` (verified `applications` count back to 210 = 10 personas + 200 background, matching a fresh `demo-reset`'s own output). No seeded persona data was touched.

This confirms the full real client → real Temporal server → real worker → real activities → real Postgres round trip works outside the time-skipping test harness, and specifically caught+fixed the `worker.py` model-registration bug (plan.md #17) that the mocked/time-skipping test suite structurally cannot catch.

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (full suite) | `uv run pytest backend -q` | `247 passed` (3 consecutive full-suite runs, no flakes, after the `at`-ordering fix, plan.md #18). |
| Backend workflows+applications only | `uv run pytest backend/app/workflows backend/app/features/applications/tests -q` | `40 passed` |
| ruff check | `uv run ruff check backend` | `All checks passed!` |
| ruff format --check | `uv run ruff format --check backend` | `224 files already formatted` |
| mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 224 source files` |
| `make lint` (full: ruff/mypy/eslint/tsc/prettier) | `make lint` | All green — `pnpm install` was run this session (previously never run in this worktree), so the frontend half (`eslint`, `tsc`, `prettier --check`) now passes too, not just backend. |
| `make test` (backend + seed + frontend) | `make test` | `247 passed` (backend) + `23 passed` (`seed`) + all `pnpm -r run test` suites green (packages/ui 27, packages/api-client 1, both apps 4 each). |
| `make demo-reset` | `make demo-reset` (with `SEED_STAFF_PASSWORD` set in local `.env`) | `elapsed: 1.3s`; persona end-statuses match spec's table exactly: 6× `priced`, `aisha_coleman: needs_attention`, `ben_ford: needs_attention`, `grace_kim: sent`, `luis_romero: option_selected`; 200 background applications seeded. |

### Local environment note

This worktree's `.env` (gitignored, per-checkout) was already present from handoff 1 (`TEST_DATABASE_URL` → dedicated `cq_test_cq011`, `FIELD_ENCRYPTION_KEY`, `DEV_LO_ID`). Added `SEED_STAFF_PASSWORD` for `make demo-reset`. Ran `pnpm install` in this worktree for the first time this session (`Packages: +480`) so `make lint`'s frontend half now runs. `make worker`'s Makefile target does `cd backend && ...`, and `Settings`' `env_file=".env"` is resolved relative to the process's cwd, not the repo root — the real-Temporal smoke run needed a `backend/.env` copy of the root `.env` for `make worker` to pick up settings; deleted it after the smoke run (not committed, gitignored either way) since `uv run pytest backend`/`make lint`/`make test` all run from the repo root and only need the root `.env`.

## Review findings (stage 6)

Fresh-subagent review (did not write this code). Verdict: **APPROVE** — no critical or major findings; all 7 ACs independently re-verified, including a real Temporal + real Postgres + real API round trip (separate from handoff 2's own smoke run, using a freshly created throwaway application).

### Commands re-run

| Command | Result |
| --- | --- |
| `gh run view 36114014423 --log` | Confirmed: `backend` job actually ran `uv run pytest backend` (`collected 247 items`, all passed) and `ruff check`/`ruff format --check`/mypy green; `frontend` job's `pnpm -r run lint/typecheck/test` all green (27+4+4 frontend tests passed). Not just a green checkmark — the log shows real collection/pass counts. |
| `git merge-tree --write-tree phase-p0-p1 HEAD` | Clean — printed a single tree hash, no `CONFLICT` markers. Merges into `phase-p0-p1` without conflict. |
| `uv run pytest backend/app/workflows backend/app/features/applications/tests -q` (repo root, real `.env`) | `40 passed` — matches post-dev's own count. |
| `uv run ruff check backend` | `All checks passed!` |
| `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 224 source files` |
| Real Temporal + real API smoke run (separate throwaway application, IN/Hamilton primary/conventional, reusing already-seeded tax-rate/rate-sheet background data): `make worker` + `uvicorn` against the shared `clear-quote` stack (already up), `POST .../pipeline/start` | `200 {"started": true}`; within ~3s real wall-clock, `applications.status` → `priced`, `activity_events` had exactly 6 rows in order `pipeline.imported, pipeline.verified, pipeline.enriched ×3, pipeline.priced` (via direct SQL) — matches spec's Marcus Hale happy-path shape exactly. |
| Same run, re-`POST .../pipeline/start` | `200 {"started": false}` — idempotent against the real server. |
| Same run, `POST .../pipeline/resume` on a fresh random (never-started) id | `404 {"error": {"code": "WORKFLOW_NOT_RUNNING", "message": "...", "details": {"application_id": "..."}}}` — matches CQ-004's pinned error shape exactly. |
| Cleanup | Deleted the throwaway `activity_events`/`applications`/`clients`/`users`/`provider_los_records`/`provider_credit_reports` rows; `applications` count back to 210 (10 personas + 200 background); stopped the `worker`/`uvicorn` processes started for this review; removed the `backend/.env` copy created for the smoke run; `make down` never run. |

### Findings

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `backend/app/workflows/worker.py:31-55` vs `alembic/env.py:17-41` | Judge decision #17: the "every model module" import list is hand-duplicated in two files (currently identical sets, verified line-by-line). Nothing enforces they stay in sync, and the author's own post-dev notes say pytest structurally can't catch a drift (the test suite's own `alembic upgrade head` imports every model module first, process-wide, before any test runs) — a future feature's new `models.py` added to one list and not the other would silently break every real-worker activity touching that table (`NoReferencedTableError`) with no CI signal. | Add a small test asserting the two import lists are equal (e.g. parse both files' `import app....models` lines and diff the sets), or extract the list to one shared module (`app.core.model_registry`) both `alembic/env.py` and `worker.py` import — already suggested in post-dev's own Follow-ups, just not done. |
| 2 | minor | `backend/app/workflows/activities.py:14-19` (event-type mapping) | Judge decision #5: `enrich_application`, `validate_pricing_inputs` and `auto_price_application` all write `pipeline.enriched` on success. This does satisfy spec's pinned 7-type vocabulary and AC5's two literal test sequences (Marcus's 6 rows, Aisha's 4-type sequence) exactly — re-verified by reading `test_activity_events_sequence.py` and re-running it — so it is not a contract break. But a full happy-path `activity_events` timeline can no longer distinguish which of the three stages produced a given "enriched" row, which weakens the "visible per-application run history" goal from system-design.md's Architecture section for CQ-016/028/029's future audit UI. | Already flagged in post-dev's Follow-ups for the consuming items' owners; no change needed in CQ-011 itself. Consider 2-3 additional pinned type strings (e.g. `pipeline.validated`, `pipeline.priced_scenarios`) in a later item — additive, non-breaking. |
| 3 | nit | `backend/app/workflows/tests/test_activity_events_sequence.py:38-44`, `test_resume_signal.py:163-165` | Judge decision #18: ordering by `ActivityEvent.at` (Python-side `datetime.now(UTC)`) instead of `created_at` (`server_default=func.now()`, resolved once per Postgres transaction) is correctly reasoned for this test suite's single-transaction, savepoint-bound activity sessions, and reproduced the flake it describes when checked by hand. Not a bug. | None needed for CQ-011. Worth a one-line callout to CQ-016 (activity timeline UI) that it should also order by `at`, not `created_at`, for the same reason if it ever reads this table directly instead of through a service function. |
| 4 | nit | `backend/app/features/applications/router.py:30-66` | `POST .../pipeline/start` and `.../pipeline/resume` have no auth dependency, unlike the pricing routes' `get_current_lo_stub`. Confirmed intentional (plan.md Decision #9: spec doesn't mention an LO-auth dependency for these two routes) and consistent with "no auth until CQ-014" — not a defect, just noting per the review brief's ask. | None needed now; CQ-014 should add the same auth dependency other LO routes get once it lands. |

No critical or major findings. Every AC (1-7) was independently re-verified against its own test file's actual assertions (not just pass/fail counts) plus, for AC1/AC5/AC7, a live re-run against the real stack.

## How to test manually

1. `make up` (ensure Temporal is healthy at localhost:7233).
2. `cp .env.example .env`, fill in `FIELD_ENCRYPTION_KEY` (`uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`), `DEV_LO_ID=00000000-0000-0000-0000-000000000001`, and `SEED_STAFF_PASSWORD` (any value, needed for `make demo-reset`).
3. `make worker` in one terminal (registers `ApplicationPipelineWorkflow` on `clear-quote-pipeline`) — note its `env_file` resolves relative to `backend/` (the target does `cd backend`), so copy `.env` there too, or export the vars directly, if running it standalone outside `make`.
4. `uv run pytest backend/app/workflows -q` for the full time-skipping suite (no real Temporal needed).
5. `make demo-reset` then `make api` + `make worker` for a full real round trip against the seeded personas.

## CI

Pushed to `origin/cq-011-temporal-pipeline`. GitHub Actions run [`36114014423`](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36114014423): **success** — `backend` job (ruff check, ruff format --check, mypy, `uv run pytest backend`) green in 55s; `frontend` job (`pnpm -r run lint`, `pnpm -r run typecheck`, `pnpm exec prettier --check .`, `pnpm -r run test`) green in 32s.

## Follow-ups

- plan.md Decision #5's `activity_events` type reuse (`pipeline.enriched` for 3 different activities) is functionally correct but coarse for a real audit timeline UI — CQ-016/028/029 owners may want finer-grained types later; adding new ones is additive/safe (no rename).
- `docs/design/system-design.md`/`alembic/env.py`'s "every model module" import list is now duplicated in `backend/app/workflows/worker.py` (plan.md #17) — a future item could extract it to one shared module (e.g. `app.core.model_registry`) both `alembic/env.py` and `worker.py` import, so a new feature's `models.py` only needs registering in one place instead of two. Not done here to keep this fix minimal and scoped to the bug found.
