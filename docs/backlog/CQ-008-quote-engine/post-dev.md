# CQ-008 — Post-development notes

## Summary

Built the pure `quote_engine` module at `backend/app/features/pricing/engine/`: `types.py`
(`ScenarioInputs`, `ConfigSnapshot`, `QuoteComputation`, `StrategyType`, `DSCRBucket`),
`mi_matrix.py` (MI rate table + `mi_factor`), and `quote_engine.py` (`compute_quote` plus one
small function per formula — P&I, PITIA components, cash-to-close, qualifying rent, DSCR,
cashflow, cap rate, cost segregation — all Decimal, unrounded internally, rounded exactly once
at output). 28 tests across 7 files pass, including all spec-pinned golden values to the cent.
No I/O, no DB, no new dependency; runs standalone with `uv run pytest backend/app/features/pricing/engine`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` are "frozen Pydantic v2 model(s)" | `@dataclass(frozen=True, kw_only=True)` (stdlib) | `pyproject.toml` has `dependencies = []` — pydantic is not yet a project dependency (CQ-004 adds it). Per the execution brief, this item must not add a dependency and must stop and report instead if one is truly needed. Nothing in this pure-function item needs pydantic's validation/serialization machinery, so a frozen dataclass gives the same immutability with zero new dependency. `kw_only=True` (Python 3.12) also resolves the spec's field ordering (defaulted fields interleaved before required ones), which a plain positional dataclass can't express. Logged as plan.md Decision 2–3. |
| `mi_factor(ltv_pct, fico, config)` — no `strategy` param, but "returns None when ... strategy != PRIMARY" | `mi_factor` is a pure LTV x FICO lookup with no strategy awareness; `compute_quote` only calls it when `strategy == PRIMARY` and hardcodes `monthly_mi = None` for LTR/STR | Reconciles the binding signature with the prose. `test_no_mi_on_investment` exercises this via `compute_quote`. Logged as plan.md Decision 4. |

No other deviations — all formulas, config defaults, MI matrix and DSCR bucket values match spec.md exactly.

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_golden.py` → `10 passed` |
| AC2 | Pass | `test_golden.py::test_pi_225000_at_7_125` → PASSED (asserts `1515.87`) |
| AC3 | Pass | `test_golden.py::test_pi_273600_at_7_500` → PASSED (asserts `1913.05`) |
| AC4 | Pass | `test_golden.py::test_str_annual_rent_target` → PASSED (asserts `27313.05`) |
| AC5 | Pass | `test_golden.py::test_str_underwritten_rent` → PASSED (asserts `2440.00`) |
| AC6 | Pass | `test_golden.py::test_dscr_ratio` → PASSED (asserts `0.90`, `BELOW_1_00`) |
| AC7 | Pass | `test_golden.py::test_cost_segregation_342k` → PASSED (asserts `24275.78`) |
| AC8 | Pass | `test_golden.py::test_cap_rate` → PASSED (asserts `6.42`) |
| AC9 | Pass | `test_golden.py::test_cashflow_incl_tax_benefit` → PASSED (asserts `1758.87`) |
| AC10 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_mi_matrix.py` → `5 passed` (`test_mi_ltv95_fico700_applies`, `test_no_mi_at_80_ltv`, `test_no_mi_on_investment`) |
| AC11 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_dscr_bucket.py` → `2 passed` (boundaries 0.99/1.00/1.24/1.25 parametrized) |
| AC12 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_cash_to_close.py` → `2 passed` (`test_cash_to_close_with_credit`, `test_cash_to_close_formula`) |
| AC13 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_config_snapshot.py` → `2 passed` (`test_config_snapshot_defaults`, `test_config_snapshot_frozen`) |
| AC14 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_golden.py::test_rounding_full_precision_internal` → PASSED (asserts `24275.78`, explicitly `!= 24276.00`) |
| AC15 | Pass | `uv run ruff check backend/app/features/pricing/engine/` → `All checks passed!`; `uv run mypy backend/app/features/pricing/engine/` → `Success: no issues found in 11 source files` |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Engine unit tests | `uv run pytest backend/app/features/pricing/engine -q` | `28 passed in 0.02s` |
| Full backend tests (no collisions with CQ-004's placeholder) | `uv run pytest backend -q` | `29 passed in 0.02s` |
| Ruff (lint) | `uv run ruff check backend/app/features/pricing/engine/` | `All checks passed!` |
| Ruff (format) | `uv run ruff format --check backend/app/features/pricing/engine/` | `11 files already formatted` |
| Mypy (item scope) | `uv run mypy backend/app/features/pricing/engine/` | `Success: no issues found in 11 source files` |
| Mypy (full backend/app, sanity) | `uv run mypy backend/app` | `Success: no issues found in 14 source files` |
| Ruff (full backend, sanity) | `uv run ruff check backend` | `All checks passed!` |

`make lint` / `make test` were not run as such — the Makefile is CQ-004's territory and doesn't yet
target this module; the commands above are their `uv`-level equivalents for this item's tree, matching
the spec's own test-plan commands.

## Review findings (stage 6)

_(left for the fresh-subagent reviewer)_

## How to test manually

1. `cd backend && uv run pytest app/features/pricing/engine -v` (or from repo root:
   `uv run pytest backend/app/features/pricing/engine -v`) — no DB, no services required.
2. `uv run python3` and call `compute_quote(...)` directly with a `ScenarioInputs`/`ConfigSnapshot`
   pair to inspect a `QuoteComputation`; e.g. construct a `StrategyType.PRIMARY` scenario and confirm
   every investment-only field (`qualifying_rent`, `dscr_ratio`, `cap_rate_pct`, cost-seg fields, …)
   is `None`.

## Follow-ups

- CQ-013 (pricing service) is the intended caller of `compute_quote`; it owns mapping
  `applications.occupancy`/`applications.strategy` onto `StrategyType`, and the two-pass DSCR
  re-pricing loop that calls `bucket_for_dscr` to compare assumed vs. computed buckets.
- If real MGIC/Radian MI rate-card values become available, swap `DEFAULT_MI_MATRIX` in
  `mi_matrix.py` — `mi_factor`'s signature does not need to change.
- If/when pydantic lands as a real project dependency (CQ-004), `ScenarioInputs`/`ConfigSnapshot`/
  `QuoteComputation` could be re-expressed as pydantic v2 models without changing `compute_quote`'s
  signature or field names, per spec's original intent — not done here per this item's
  no-new-dependency constraint (see Deviations above).
- `docs/backlog/README.md`'s CQ-008 row was intentionally left at "To Do" — this item's brief
  explicitly excludes editing that file; the orchestrator should flip it to "In Review".
