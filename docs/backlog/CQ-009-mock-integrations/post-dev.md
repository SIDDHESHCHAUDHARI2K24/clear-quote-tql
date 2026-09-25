# CQ-009 — Post-development notes

## Summary

Built all 9 emulated-integration `Protocol`/`Mock*` pairs (LOS, Pricing, Rent, STR, Tax, Insurance, Credit, PropertySearch, CRM) under `backend/app/integrations/`, plus the shared `common/` infrastructure they all use: latency simulation, a per-adapter Valkey failure toggle, and an `integration_calls` audit-log writer. `MockPricingClient` implements the full OB required-field validation (with the primary/investment conditional split) and the rate-sheet algorithm (FICO/LTV/DSCR-bucket/PPP/STR/lead-source filtering, par/buydown marking, ascending sort). Every adapter reads its own `provider_*` table (CQ-007); `CrmClient` only writes `crm_events`. 47 new tests, all passing, plus the pre-existing 85 backend tests unaffected.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `record_call(adapter, request_summary, success, latency_ms, error_code=None, application_id=None)` (no session param) | `record_call(session, adapter, request_summary, success, latency_ms, *, error_code=None, application_id=None)`; every `Mock*.__init__(self, session: AsyncSession)` | CQ-004's `app.core.db` module engine is pinned to `DATABASE_URL`, a different DB from `TEST_DATABASE_URL` that CI's Postgres service never creates. Every mock call logs a call, so this would break the whole suite in CI, not just CQ-009's tests. See plan.md Decision 2. |
| Failure toggle "stored in Valkey" (implies the real local Valkey) | Tests use in-process `fakeredis`; production code (`failure_toggle.py`) unchanged, still targets the real `redis.asyncio`/`Settings.valkey_url` | CI has no Redis/Valkey service; the shared local Valkey is also used by parallel agents' sessions. See plan.md Decision 1. |
| `PropertySearchClient` "ranks LTR by cashflow and STR by DSCR" | `deal_ranking_score` = simple price-relative-to-budget proxy | True cashflow/DSCR ranking needs `quote_engine` + rent data `provider_listings` doesn't have; out of scope here (money math lives only in quote_engine). See plan.md Decision 3. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — contract tests per adapter; forced failure raises `ProviderUnavailableError(adapter=...)` | Pass | `uv run pytest backend/app/integrations/common/tests/test_contract.py -q` → `9 passed` (parametrized over all 9 adapters) |
| AC2 — all 9 Protocols + Mocks exist at the exact module paths/signatures | Pass | `uv run pytest backend/app/integrations/*/tests/test_mock.py -q` → `25 passed`; every mock asserted `isinstance(mock, Protocol)` via `@runtime_checkable` |
| AC3 — latency bounded 200-1200ms when enabled; <1s/100 calls when disabled | Pass | `uv run pytest backend/app/integrations/common/tests/test_latency.py -q` → `2 passed` |
| AC4 — per-adapter forced failure toggle sets/clears independently | Pass | `uv run pytest backend/app/integrations/common/tests/test_failure_toggle.py -q` → `3 passed` |
| AC5 — every call writes exactly one `integration_calls` row with correct `latency_ms`/`success` | Pass | `uv run pytest backend/app/integrations/common/tests/test_logging.py -q` → `2 passed` |
| AC6 — `PricingValidationError` names every missing required field, incl. empty `Occupancy` (persona 7) | Pass | `uv run pytest backend/app/integrations/pricing/tests/test_validation.py -q` → `4 passed`, incl. `test_missing_occupancy` |
| AC7 — valid investment request returns 8-15 rows sorted ascending by `note_rate`, exactly one `is_par_rate` | Pass | `uv run pytest backend/app/integrations/pricing/tests/test_rate_sheet.py -q` → `2 passed` |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| New integration tests | `uv run pytest backend/app/integrations -q` | `47 passed in 1.63s` |
| Full backend suite | `uv run pytest backend -q` | `132 passed, 1 warning in 1.98s` (pre-existing httpx deprecation warning only) |
| Ruff lint | `uv run ruff check backend` | `All checks passed!` |
| Ruff format | `uv run ruff format --check backend` | `168 files already formatted` |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 168 source files` |
| Frontend lint (`pnpm -r run lint`) | `make lint` | **Not run to completion** — `node_modules` isn't installed in this worktree (`eslint: command not found`); pre-existing environment state unrelated to this item (no frontend files touched by CQ-009) |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |

(pending fresh-subagent review)

## How to test manually

1. `make up` (ensure Postgres/Valkey are running), `cp .env.example .env` in the worktree if no `.env` exists yet.
2. `uv run pytest backend/app/integrations -v` to see all 47 tests, or target one adapter, e.g. `uv run pytest backend/app/integrations/pricing -v`.
3. To exercise the real Valkey failure toggle (not the test fakeredis) interactively: `uv run python -c "import asyncio; from app.integrations.common.failure_toggle import set_forced_failure, is_forced_to_fail; asyncio.run(set_forced_failure('rent', True)); print(asyncio.run(is_forced_to_fail('rent')))"` then `redis-cli get integration:fail:rent` (expect `"1"`).

## Follow-ups

- CQ-010 (seed data): once real persona seed rows land in `provider_*` tables, spot-check `MockLosClient`/`MockPricingClient` etc. against them (this item's tests only use synthetic fixtures).
- CQ-011/CQ-013: construct `MockXClient(session)` from whatever `AsyncSession` you already hold; be aware `record_call` (called on every mock invocation) commits that session.
- CQ-023 (property matches): if true cashflow/DSCR-based `deal_ranking_score` is needed, it requires `quote_engine` plus rent/STR data not currently on `provider_listings` — see plan.md Decision 3.
- Frontend `make lint`/`make test` were not exercised (no frontend files changed); run `pnpm install` once before merging if CI's frontend job hasn't already validated this branch.
