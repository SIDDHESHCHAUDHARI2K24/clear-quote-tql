# CQ-009 — Post-development notes

## Summary

Built all 9 emulated-integration `Protocol`/`Mock*` pairs (LOS, Pricing, Rent, STR, Tax, Insurance, Credit, PropertySearch, CRM) under `backend/app/integrations/`, plus the shared `common/` infrastructure they all use: latency simulation, a per-adapter Valkey failure toggle, and an `integration_calls` audit-log writer. `MockPricingClient` implements the full OB required-field validation (with the primary/investment conditional split) and the rate-sheet algorithm (FICO/LTV/DSCR-bucket/PPP/STR/lead-source filtering, par/buydown marking, ascending sort). Every adapter reads its own `provider_*` table (CQ-007); `CrmClient` only writes `crm_events`. `record_call` writes its audit row through its own short-lived session/connection (fix round 1, below), independent of the caller's transaction. 49 integration tests, all passing, plus the pre-existing 85 backend tests unaffected.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `record_call(adapter, request_summary, success, latency_ms, error_code=None, application_id=None)` (no session param) | `record_call(session, adapter, request_summary, success, latency_ms, *, error_code=None, application_id=None, audit_sessionmaker=None)`; every `Mock*.__init__(self, session: AsyncSession)`. `record_call` uses `session` only to derive its own `AsyncEngine` (`session.bind`) and writes the audit row through a **separate** short-lived session on that engine — never the caller's session. | CQ-004's `app.core.db` module engine is pinned to `DATABASE_URL`, a different DB from `TEST_DATABASE_URL` that CI's Postgres service never creates; deriving from the caller's own engine avoids a second hardcoded one. The separate-session part is fix round 1 (below): reusing the caller's session for the commit both risked committing the caller's other pending work and lost the audit row on a caller rollback. See plan.md Decision 2 (revised). |
| Failure toggle "stored in Valkey" (implies the real local Valkey) | Tests use in-process `fakeredis`; production code (`failure_toggle.py`) unchanged, still targets the real `redis.asyncio`/`Settings.valkey_url` | CI has no Redis/Valkey service; the shared local Valkey is also used by parallel agents' sessions. See plan.md Decision 1. |
| `PropertySearchClient` "ranks LTR by cashflow and STR by DSCR" | `deal_ranking_score` = simple price-relative-to-budget proxy | True cashflow/DSCR ranking needs `quote_engine` + rent data `provider_listings` doesn't have; out of scope here (money math lives only in quote_engine). See plan.md Decision 3. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — contract tests per adapter; forced failure raises `ProviderUnavailableError(adapter=...)` | Pass | `uv run pytest backend/app/integrations/common/tests/test_contract.py -q` → `9 passed` (parametrized over all 9 adapters) |
| AC2 — all 9 Protocols + Mocks exist at the exact module paths/signatures | Pass | `uv run pytest backend/app/integrations/*/tests/test_mock.py -q` → `25 passed`; every mock asserted `isinstance(mock, Protocol)` via `@runtime_checkable` |
| AC3 — latency bounded 200-1200ms when enabled; <1s/100 calls when disabled | Pass | `uv run pytest backend/app/integrations/common/tests/test_latency.py -q` → `2 passed` |
| AC4 — per-adapter forced failure toggle sets/clears independently | Pass | `uv run pytest backend/app/integrations/common/tests/test_failure_toggle.py -q` → `3 passed` |
| AC5 — every call writes exactly one `integration_calls` row with correct `latency_ms`/`success` | Pass | `uv run pytest backend/app/integrations/common/tests/test_logging.py -q` → `4 passed` (incl. `test_audit_row_survives_caller_rollback` and `test_provider_call_never_commits_the_callers_session`, added in fix round 1) |
| AC6 — `PricingValidationError` names every missing required field, incl. empty `Occupancy` (persona 7) | Pass | `uv run pytest backend/app/integrations/pricing/tests/test_validation.py -q` → `4 passed`, incl. `test_missing_occupancy` |
| AC7 — valid investment request returns 8-15 rows sorted ascending by `note_rate`, exactly one `is_par_rate` | Pass | `uv run pytest backend/app/integrations/pricing/tests/test_rate_sheet.py -q` → `2 passed` |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| New integration tests | `uv run pytest backend/app/integrations -q` | `49 passed` |
| Full backend suite (run twice, back to back) | `uv run pytest backend -q` | `134 passed, 1 warning` both times (pre-existing httpx deprecation warning only) — confirms `_clean_integration_calls` leaves no cross-run leakage |
| `integration_calls` row count after full suite | `docker exec clear-quote-postgres-1 psql -U cq -d cq_test -c "select count(*) from integration_calls;"` | `0` |
| Ruff lint | `uv run ruff check backend` | `All checks passed!` |
| Ruff format | `uv run ruff format --check backend` | `168 files already formatted` |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 168 source files` |
| Full lint (backend + frontend) | `make lint` | All green (ruff, ruff format, mypy, eslint x4 packages, tsc x4, prettier) — `node_modules` installed by reviewer during stage 6 |
| Full test (backend + frontend) | `make test` | `134 passed` backend; `1+27+4+4 = 36` frontend tests passed across `packages/api-client`, `packages/ui`, `apps/borrower-portal`, `apps/lo-console` |
| CI (initial push) | `git push -u origin cq-009-mock-integrations`; `gh run watch 36101491478 --exit-status` | Run [36101491478](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36101491478) — success |
| CI (fix round 1) | `git push`; `gh run watch 36102399491 --repo SIDDHESHCHAUDHARI2K24/clear-quote-tql --exit-status` | Run [36102399491](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36102399491) — success; `backend` and `frontend` jobs both green (unrelated GH Actions cache-service warnings in the annotations, no failures) |

## Review findings (stage 6)

Fresh-subagent review (did not write this code). Verdict: **APPROVE** — no critical/major findings.

### Verification re-run

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `uv run pytest backend -q` | `132 passed, 1 warning` (matches post-dev log) |
| Integration tests only | `uv run pytest backend/app/integrations -q` | `47 passed` |
| Ruff check | `uv run ruff check backend` | `All checks passed!` |
| Ruff format | `uv run ruff format --check backend` | `168 files already formatted` |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 168 source files` |
| `pnpm install` (worktree had no `node_modules`) | `pnpm install` | Done, 480 packages |
| `make lint` | `make lint` | ruff/mypy/eslint/tsc/prettier all green |
| CI run 36101491478 | `gh run view 36101491478 --log \| grep integrations` | Confirmed: `test_contract.py`, `test_failure_toggle.py`, `test_latency.py`, `test_logging.py`, and all 9 adapters' `test_mock.py` (plus pricing's `test_rate_sheet.py`/`test_validation.py`) actually executed in the CI run, ending `132 passed, 1 warning in 12.70s`; both `backend` and `frontend` jobs green |
| Per-test DB isolation (empirical) | Ran full suite, then queried `TEST_DATABASE_URL`'s `integration_calls` table directly | `0` rows — confirms `record_call`'s `session.commit()` only releases a savepoint (`db_session` fixture's `join_transaction_mode="create_savepoint"`), not the outer transaction; no leakage across tests |
| Merge check vs `phase-p0-p1` | `git merge-tree --write-tree phase-p0-p1 HEAD` | Clean tree, no conflict markers |
| Merge check vs `cq-012-verification-rules` | `git merge-tree --write-tree cq-012-verification-rules HEAD` | Clean tree, no conflict markers; `comm -12` on the two branches' changed-file lists shows zero file overlap with CQ-009 (CQ-012 only touches `backend/app/features/applications/verification/...`) |
| Network/SDK/secret scan | `grep -rniE "requests\.\|httpx\.(get\|post\|Client\()\|aiohttp\|api_key\|SDK\|encompass\.com\|optimalblue\|rentcast\.io\|airdna\.co"` over `backend/app/integrations/` | No matches — every adapter only reads/writes its own `provider_*`/`crm_events` table |

### Findings

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `backend/app/integrations/common/logging.py:50` | `record_call` calls `session.commit()` on the **caller's** session, and every `Mock*.__init__` requires that same session. For this item (tests using `backend/conftest.py`'s `db_session`, which binds with `join_transaction_mode="create_savepoint"`) this is provably safe — verified empirically above, `integration_calls` has 0 leaked rows after a full suite run, because the inner `commit()` only releases a savepoint. The real risk is downstream: when CQ-011 (Temporal activities) or CQ-013 (pricing service) hand a `Mock*` a session that is *not* bound with `create_savepoint` semantics (e.g. a plain top-level session on `AsyncSessionLocal`), every provider call will silently commit whatever other pending writes are sitting in that session at the time — partial commits mid-activity, and a later `session.rollback()` on error will no longer undo that earlier work. The author's own plan.md Decision 2 and post-dev "Follow-ups" already flag this explicitly to CQ-011/CQ-013 authors, so it's a documented, deliberate tradeoff forced by a real constraint (CQ-004's module-level engine is pinned to `DATABASE_URL`, a different DB than `TEST_DATABASE_URL`, which CI's Postgres service never creates) rather than an oversight — hence minor, not major, for *this* item. Suggested fix for whichever of CQ-011/CQ-013 lands first: don't rely on "the caller's session happens to be savepoint-mode"; instead make `record_call` write through a **separate, short-lived session/connection** dedicated to the audit row (its own commit, independent of the caller's transaction). This is also more correct for the actual use case: on a *failure* path (the case CQ-029's panel most wants to show), the caller's own transaction will often roll back precisely because the provider call failed — a plain `session.flush()`-only fix would still lose that audit row on rollback, whereas an independent session/connection makes the `integration_calls` row durable regardless of the caller's outcome. Track as a CQ-011/CQ-013 task, not a blocker here. |
| 2 | nit | `backend/app/integrations/pricing/mock.py:191-199` | Buydown-rate selection loops through *all* candidates with a lower `note_rate` than par (closest-first) until one lands in the 0.75–1.00 points band, rather than only checking the single adjacent-lower row. Spec's wording ("the row with the next-lower note_rate ... whose points cost is between 0.75 and 1.00") is ambiguous between "the very next row" and "the nearest lower row that satisfies the band" — current behavior is a defensible reading and is exercised correctly by `test_rate_sheet.py`, but worth a one-line comment or a spec clarification so a future reader doesn't have to re-derive the ambiguity. |
| 3 | nit | `docs/backlog/CQ-009-mock-integrations/post-dev.md` | Frontend `make lint`/typecheck were not run locally before this review (worktree had no `node_modules`); post-dev log already says so and asks the merger to `pnpm install` first. Now done as part of this review (see verification table above) — green. |

No critical or major findings. AC1–AC7 all independently re-verified against the actual test files (not just trusting the post-dev log): `test_contract.py` parametrizes over all 9 adapters and asserts `ProviderUnavailableError(adapter=..., code="PROVIDER_UNAVAILABLE", status_code=502)`; `test_validation.py::test_missing_occupancy` reproduces persona 7 exactly (`Occupancy=""`, `missing_fields` includes `"Occupancy"`, message `"Cannot price: missing Occupancy"`, `status_code == 422`); `test_rate_sheet.py` seeds 10 DSCR rows and asserts `8 <= len(products) <= 15`, ascending `note_rate`, exactly one `is_par_rate`. All 9 Protocols/DTOs read against the spec's method-signature table match exactly (paths, method names, params, return types). No real network calls, SDKs, or API keys found anywhere in the diff; every mock reads/writes only its own `provider_*` table or `crm_events`.

### Fix round 1 (finding #1, resolved)

Per the coordinator's follow-up, fixed before CQ-011/CQ-013 start rather than deferring: `record_call` (`backend/app/integrations/common/logging.py`) now writes the audit row through its own short-lived `AsyncSession`, opened from an `AsyncEngine` derived from the caller's `session.bind` (unwrapping an `AsyncConnection` via `.engine` for the test `db_session` case) — never the caller's session object. TDD: `common/tests/test_logging.py` gained `test_audit_row_survives_caller_rollback` (rolls back a standalone caller transaction directly on `test_engine`, then reads the row back from a fresh connection) and `test_provider_call_never_commits_the_callers_session` (monkeypatches the caller session's `.commit()` and asserts it's never invoked); both failed against the pre-fix code (RED) and pass now (GREEN). Since these audit rows are now real, independent commits, `backend/app/integrations/conftest.py` gained an autouse `_clean_integration_calls` fixture (`pytest_asyncio`, truncates `integration_calls` via `test_engine` after each test) so the suite stays isolated the way `db_session`'s rollback keeps everything else isolated — verified by running the full suite twice back to back (`134 passed` both times) and confirming `0` rows in `integration_calls` afterward. Findings #2 and #3 (nits) were left as-is per the review's own recommendation (defensible reading; already resolved, respectively).

## How to test manually

1. `make up` (ensure Postgres/Valkey are running), `cp .env.example .env` in the worktree if no `.env` exists yet.
2. `uv run pytest backend/app/integrations -v` to see all 47 tests, or target one adapter, e.g. `uv run pytest backend/app/integrations/pricing -v`.
3. To exercise the real Valkey failure toggle (not the test fakeredis) interactively: `uv run python -c "import asyncio; from app.integrations.common.failure_toggle import set_forced_failure, is_forced_to_fail; asyncio.run(set_forced_failure('rent', True)); print(asyncio.run(is_forced_to_fail('rent')))"` then `redis-cli get integration:fail:rent` (expect `"1"`).

## Follow-ups

- CQ-010 (seed data): once real persona seed rows land in `provider_*` tables, spot-check `MockLosClient`/`MockPricingClient` etc. against them (this item's tests only use synthetic fixtures).
- CQ-011/CQ-013: construct `MockXClient(session)` from whatever `AsyncSession` you already hold. `record_call` (called on every mock invocation) no longer touches or commits that session — it only reads `session.bind` to find the right database and writes the audit row on its own separate session (fix round 1).
- CQ-023 (property matches): if true cashflow/DSCR-based `deal_ranking_score` is needed, it requires `quote_engine` plus rent/STR data not currently on `provider_listings` — see plan.md Decision 3.
