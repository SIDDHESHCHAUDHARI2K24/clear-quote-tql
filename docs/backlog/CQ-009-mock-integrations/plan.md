# CQ-009 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Failure toggle backend for tests | Valkey per spec.md, but tests use an in-process `fakeredis.aioredis.FakeRedis`, not the real local Valkey. `.github/workflows/ci.yml`'s backend job starts a Postgres service but **no Redis/Valkey service**, so a real `redis.asyncio` connection would fail outright in CI. The local `clear-quote` Valkey (6379) is also a stack shared by parallel agents' sessions; a real connection risks one agent's `set_forced_failure` leaking into another's run. `backend/app/integrations/conftest.py` monkeypatches `common.failure_toggle._client` to a fresh `FakeRedis` per test (autouse, function-scoped). Production code (`failure_toggle.py`) is untouched — it always talks to `redis.asyncio` against `Settings.valkey_url`. Added `fakeredis` as a dev dependency. |
| 2 | Decision (revised after review) | `record_call` / `Mock*.__init__` session handling | Every `Mock*` class takes `session: AsyncSession` at construction (Protocols only constrain the async business methods, spec.md's method-signature table, not `__init__`) for its own provider-table reads. **Revised** (post-dev.md finding #1): `record_call` no longer reuses that session to write the audit row — it derives the caller's `AsyncEngine` from `session.bind` (unwrapping an `AsyncConnection` via `.engine` when the caller is bound to one, e.g. `db_session` in tests) and opens its own short-lived `AsyncSession` from it, insert + commit, independent of the caller. This fixes two problems the original "reuse the caller's session, `session.commit()`" design had: (a) it would commit whatever else the caller had pending, which an audit log must never do; (b) on the failure path — exactly when CQ-029's panel most wants the row — the caller's transaction is often about to roll back, which would take the audit row with it. Still avoids CQ-004's `app.core.db` module engine (pinned to `Settings.database_url`, a DB CI's Postgres service never creates) by deriving from the caller's own engine rather than a second hardcoded one. `common/tests/test_logging.py` proves both properties directly: `test_audit_row_survives_caller_rollback` (rolls back a standalone caller transaction, then checks the row from a fresh connection) and `test_provider_call_never_commits_the_callers_session` (spies on the caller session's `.commit()`, asserts it's never called). Tests' `integration_calls` rows are now real commits outside any per-test rollback, so `backend/app/integrations/conftest.py` gained an autouse `_clean_integration_calls` fixture that truncates the table after each test. Downstream (CQ-011, CQ-013) construct `MockXClient(session)` from whatever session they already hold; `record_call` never touches that session beyond reading `.bind`. |
| 3 | Decision | `PropertySearchClient.deal_ranking_score` | Computed as a simple price-relative-to-approved-price proxy (`1 - list_price/approved_purchase_price`; cheaper ranks higher), not the cashflow/DSCR ranking system-design.md's "Emulated integrations" table describes. True cashflow/DSCR ranking needs `quote_engine` (money math lives only there per AGENTS.md) plus per-listing rent/STR-revenue data that `provider_listings` (CQ-007) doesn't carry — both out of this item's scope. Filtering (70-100% of approved price, buy-box state + metro) and the empty-list-is-valid contract are implemented exactly per spec. CQ-023 (property matches) is where full cashflow/DSCR ranking, if built, belongs. |
| 4 | Decision | `LoanFileDTO` field set | Modeled from catalog §1/§2/§4/§5 field names, every field but `loan_number` optional. CQ-010 (seed data) hasn't landed, so this item's own tests build fixture `provider_los_records.payload` dicts directly (including persona 7's empty-`occupancy_type` case) rather than depending on real seed rows. |
| 5 | Decision | Adapter name strings | `los`, `pricing`, `rent`, `str`, `tax`, `insurance`, `credit`, `property_search`, `crm` — matching the module directory names, used consistently for `failure_toggle` keys, `record_call(adapter=...)`, and `ProviderUnavailableError.adapter`. |
| 6 | Decision | Latency default for the whole suite | `backend/conftest.py` gets one added line: `os.environ.setdefault("INTEGRATION_LATENCY_ENABLED", "false")`, next to its existing `APP_ENV`/`FIELD_ENCRYPTION_KEY` defaults, so the full suite stays fast. `common/tests/test_latency.py` monkeypatches the cached `Settings` instance back to `True` for its one bounds-checking test (AC3's "enabled" case). |
| 7 | Decision | `MatchStrategy` vs. `pricing.engine.StrategyType` | `property_search/schemas.py` defines its own narrower `MatchStrategy(LTR, STR)` rather than importing the engine's `StrategyType` (which also has `PRIMARY`, meaningless for property search) — keeps `integrations` decoupled from `pricing.engine` except where spec.md explicitly requires it (`PricingClient`'s `bucket_for_dscr`/`DSCRBucket`). |

No big gaps found — the spec fully reconciles method signatures, error names/codes, the rate-sheet algorithm and the OB required-field list; only infrastructure-level plumbing (session passing, test isolation) needed a decision.

## Why

CQ-011 (Temporal pipeline) and CQ-013 (pricing service) both need one stable, typed interface per emulated provider before they can be built, per system-design.md's "Emulated integrations". This item builds those 9 `Protocol`/`Mock` pairs plus the shared latency/failure/logging infrastructure they all share, entirely against CQ-007's already-merged `provider_*`/`crm_events`/`integration_calls` tables.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Settings | `backend/app/core/config.py` (add `integration_latency_min_ms`/`max_ms`/`enabled`) |
| Test defaults | `backend/conftest.py` (one line: disable latency for the suite) |
| Shared infra | `backend/app/integrations/common/{errors,latency,failure_toggle,logging}.py`, `backend/app/integrations/conftest.py` (fakeredis fixture) |
| 9 adapters | `backend/app/integrations/{los,pricing,rent,str,tax,insurance,credit,property_search,crm}/{protocol,schemas,mock}.py` |
| Tests | `backend/app/integrations/common/tests/test_{contract,latency,failure_toggle,logging}.py`; `backend/app/integrations/{los,pricing,rent,str,tax,insurance,credit,property_search,crm}/tests/test_mock.py`; `backend/app/integrations/pricing/tests/test_{validation,rate_sheet}.py` |
| Deps | `pyproject.toml` (dev: `fakeredis`), `uv.lock` |
| Docs | `.env.example` (3 lines documenting the new latency settings) |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Settings + conftest wiring | — | `core/config.py`, `backend/conftest.py` | (exercised by T3) |
| T2 | Shared `common/` infra + fakeredis test fixture | T1 | `common/{errors,latency,failure_toggle,logging}.py`, `integrations/conftest.py`, `pyproject.toml` | `common/tests/test_{latency,failure_toggle}.py` |
| T3 | LOS, Rent, STR, Tax, Insurance, Credit, CRM adapters (single-table reads/writes, same shape) | T2 | each adapter's `protocol.py`/`schemas.py`/`mock.py`/`tests/test_mock.py` | each adapter's `test_mock.py` |
| T4 | Pricing adapter (validation + rate-sheet algorithm) | T2 | `pricing/{protocol,schemas,mock}.py`, `pricing/tests/*` | `test_validation.py`, `test_rate_sheet.py`, `test_mock.py` |
| T5 | Property search adapter | T2 | `property_search/{protocol,schemas,mock}.py`, `property_search/tests/test_mock.py` | `test_mock.py` |
| T6 | Cross-adapter contract + call-log tests | T3, T4, T5 | `common/tests/test_{contract,logging}.py` | those two files |

## Wave schedule (stage 3)

Single-agent, sequential (no parallel dispatch needed for a module this self-contained): T1 → T2 → {T3, T4, T5 in any order, no shared files} → T6.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/integrations/common/tests/test_contract.py` |
| AC2 | `backend/app/integrations/*/tests/test_mock.py` (all 9 adapters) |
| AC3 | `backend/app/integrations/common/tests/test_latency.py` |
| AC4 | `backend/app/integrations/common/tests/test_failure_toggle.py` |
| AC5 | `backend/app/integrations/common/tests/test_logging.py` |
| AC6 | `backend/app/integrations/pricing/tests/test_validation.py::test_missing_occupancy` |
| AC7 | `backend/app/integrations/pricing/tests/test_rate_sheet.py` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
