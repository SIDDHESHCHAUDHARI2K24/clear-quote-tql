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

**Resolved in review round 1** (see "Review findings resolution" below): the Pydantic-v2 deviation,
the `ltv_pct` scale, and the `str_annual_rent_target` hardcoded constant have all been reverted to
match spec.md (spec.md itself was also amended for the latter two, with orchestrator authorisation).

| Spec said | Built | Why |
| --- | --- | --- |
| `mi_factor(ltv_pct, fico, config)` — no `strategy` param, but "returns None when ... strategy != PRIMARY" | `mi_factor` is a pure LTV x FICO lookup with no strategy awareness; `compute_quote` only calls it when `strategy == PRIMARY` and hardcodes `monthly_mi = None` for LTR/STR | Reconciles the binding signature with the prose. `test_no_mi_on_investment` exercises this via `compute_quote`. Logged as plan.md Decision 4. Unchanged by review round 1. |

No other deviations — all formulas, config defaults, MI matrix and DSCR bucket values match spec.md
exactly (spec.md's own text for `ltv_pct` scale and `str_annual_rent_target` was updated to match the
engine, per orchestrator authorisation, rather than the engine deviating from spec).

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
| AC10 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_mi_matrix.py` → `8 passed` (`test_mi_ltv95_fico700_applies`, `test_no_mi_at_80_ltv`, `test_no_mi_on_investment`, plus round-1 LTV-out-of-range tests) |
| AC11 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_dscr_bucket.py` → `2 passed` (boundaries 0.99/1.00/1.24/1.25 parametrized) |
| AC12 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_cash_to_close.py` → `2 passed` (`test_cash_to_close_with_credit`, `test_cash_to_close_formula`) |
| AC13 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_config_snapshot.py` → `2 passed` (`test_config_snapshot_defaults`, `test_config_snapshot_frozen`; frozen now asserted via `pydantic.ValidationError` post round-1) |
| AC14 | Pass | `uv run pytest backend/app/features/pricing/engine/tests/test_golden.py::test_rounding_full_precision_internal` → PASSED (asserts `24275.78`, explicitly `!= 24276.00`) |
| AC15 | Pass | `uv run ruff check backend` → `All checks passed!`; `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (full `make lint` scope, post-merge) → `Success: no issues found in 36 source files` |

## Test log (stage 5)

**Round 1 (pre-review, pre-merge — historical):**

| Check | Command | Result |
| --- | --- | --- |
| Engine unit tests | `uv run pytest backend/app/features/pricing/engine -q` | `28 passed in 0.02s` |
| Full backend tests (no collisions with CQ-004's placeholder) | `uv run pytest backend -q` | `29 passed in 0.02s` |
| Ruff (lint) | `uv run ruff check backend/app/features/pricing/engine/` | `All checks passed!` |
| Ruff (format) | `uv run ruff format --check backend/app/features/pricing/engine/` | `11 files already formatted` |
| Mypy (item scope) | `uv run mypy backend/app/features/pricing/engine/` | `Success: no issues found in 11 source files` |

**Round 2 (post-merge, post-review-fixes — current):** `phase-p0-p1` merged in first (clean, brings
CQ-004's pydantic/conftest.py). `make lint`'s actual mypy scope now runs, since `backend/app/core`,
`backend/conftest.py`, `backend/tests`, `backend/scripts` all exist.

| Check | Command | Result |
| --- | --- | --- |
| Engine unit tests | `uv run pytest backend/app/features/pricing/engine -q` | `41 passed in 0.03s` |
| Golden tests only | `uv run pytest backend/app/features/pricing/engine/tests/test_golden.py -v` | `11 passed` — all 8 spec-pinned golden values still correct to the cent |
| Full backend collection (no import errors from the merge) | `uv run pytest backend --collect-only -q` | `57 tests collected` |
| Ruff (lint, whole backend, as `make lint`) | `uv run ruff check backend` | `All checks passed!` |
| Ruff (format, whole backend) | `uv run ruff format --check backend` | `36 files already formatted` |
| Mypy (whole backend, as `make lint`) | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | `Success: no issues found in 36 source files` |

`make lint` itself was not invoked (it also runs `pnpm -r run lint`/`typecheck`/`prettier`, outside this
item's scope and untouched by this change); the `uv`-level commands above are its backend-relevant
lines, run verbatim as `make lint` defines them.

Needed a local `.env` (`cp .env.example .env`, gitignored, not committed) for `backend/conftest.py` to
import at collection time — see plan.md Decision 14.

## Review findings (stage 6)

Reviewed by a fresh subagent that did not write this code. Scope: `git diff d166cf1...HEAD`
(the commit this branch was cut from, before CQ-004 merged into `phase-p0-p1`).

**Merge check.** `git merge-tree --write-tree phase-p0-p1 HEAD` wrote a tree cleanly
(`3dd95ebaec052a9027b5dc90570378d504eac03f`, exit 0, no conflict markers) — this branch
merges into current `phase-p0-p1` (post-CQ-004) without conflicts. Not merged, per instructions.

**Commands re-run**

| Command | Result |
| --- | --- |
| `uv run pytest backend/app/features/pricing/engine -v` | 28 passed |
| `uv run pytest backend -q` | 29 passed (no collisions with CQ-004) |
| `uv run ruff check backend/app/features/pricing/engine/` | All checks passed! |
| `uv run ruff format --check backend/app/features/pricing/engine/` | 11 files already formatted |
| `uv run mypy backend/app/features/pricing/engine/` | Success: no issues found in 11 source files |
| `git merge-tree --write-tree phase-p0-p1 HEAD` | Clean merge, no conflicts |
| Independent Decimal re-derivation of AC2–AC9 golden values (own script, not the engine) | All match to the cent: 1515.87, 1913.05, 27313.05, 2440.00, 0.90, 24275.78, 6.42, 1758.87 |
| Non-golden spot checks: primary 95% LTV/FICO 700 with MI, LTR 25% down, STR 15% down — P&I/PITIA/LTV/MI/CTC/DSCR independently recomputed and compared to `compute_quote` output | All match; PRIMARY scenario confirmed to carry `None` for every rent/DSCR/cashflow/cost-seg field |
| `grep -rn "float(\|round(" backend/app/features/pricing/engine` (excluding `.quantize(..., ROUND_HALF_UP)` and test helpers) | No float literals/casts; no bare `round()` outside `.quantize` helpers |
| `make lint` / `make test` | Not runnable — Makefile targets don't exist yet (CQ-002/CQ-003 territory), consistent with post-dev's own note; used `uv`-level equivalents above instead |

**Findings**

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | Major | `backend/app/features/pricing/engine/types.py:41-157` | `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` are frozen stdlib `@dataclass`, not the "frozen Pydantic v2 model(s)" spec.md's Public API section pins. The stated justification (pydantic not yet a project dependency) was true on `d166cf1` but is stale on the merge target: `phase-p0-p1` already has `pydantic-settings` (which pulls in pydantic) as a real dependency, and pydantic is directly imported in `backend/app/core/config.py` (`from pydantic import field_validator`) and `backend/app/features/system/schemas.py` (`from pydantic import BaseModel`), both already merged via CQ-004. CQ-013 (pricing service/API layer) will need pydantic models to expose these types through FastAPI request/response bodies and OpenAPI (`packages/api-client` is generated from the OpenAPI schema); plain dataclasses give none of `.model_dump()`/JSON schema/validation, so CQ-013 will have to wrap or rewrite these types — the unplanned cost the spec's Pydantic pin was meant to avoid. | Re-express the three types as frozen Pydantic v2 models (`model_config = ConfigDict(frozen=True)`) now that the dependency genuinely exists, or raise this back as a `needs-input` decision before merge rather than carrying the now-stale deviation forward. |
| 2 | Minor | `backend/app/features/pricing/engine/mi_matrix.py:86-101` | `mi_factor` silently returns `None` for `ltv_pct` above the top tabulated band (>97%), identical to the "no MI needed" case for `ltv_pct <= 80`. A PRIMARY loan at, e.g., 99% LTV would get a quote with `monthly_mi = None`, understating PITIA/CTC. No test covers this range. | Raise (or otherwise flag) on out-of-range LTV instead of silently treating it as "no MI required," or explicitly document/assert the product's max LTV is 97%. |
| 3 | Minor | `backend/app/features/pricing/engine/types.py:122-123` | `QuoteComputation.ltv_pct` is on a 0–100 scale while every other `*_pct` field in `ScenarioInputs`/`ConfigSnapshot` (`down_payment_pct`, `title_rate_pct`, `str_expense_ratio`, `investor_marginal_tax_rate`, …) is a 0–1 fraction. This matches spec's own wording for `mi_factor`'s threshold ("`ltv_pct <= 80`") but is an inconsistent scale inside the same result object — a real footgun for CQ-009/CQ-013 consumers who may assume all `*_pct` fields share one scale. The scale is documented on the internal `ltv_pct()` helper function's docstring (`quote_engine.py:48-50`) but not on the `QuoteComputation.ltv_pct` field itself. | Add an explicit field-level docstring/comment on `QuoteComputation.ltv_pct` calling out the 0–100 scale (the field name itself is spec-pinned, so it can't be renamed). |
| 4 | Minor | `backend/app/features/pricing/engine/quote_engine.py:169-172` | `str_annual_rent_target` hardcodes `Decimal("0.80")` rather than deriving from `config.str_expense_ratio`, per spec's literal formula text (already logged as plan.md Decision 5). Correct today since the two values coincide (both 0.20/0.80), but the constant lives outside `ConfigSnapshot` even though it's conceptually the same knob — a future change to `str_expense_ratio` alone would silently stop matching this formula's implicit assumption, in tension with the "quotes are reproducible from their snapshot" principle (the formula no longer reads from the snapshot at all). Not a bug against the pinned spec text as written. | Confirm with the spec owner whether `0.80` should in fact read `1 - config.str_expense_ratio`; if the literal is truly intentional, say so explicitly in spec.md next to the formula so it doesn't look like a copy-paste of the default. |
| 5 | Minor | `backend/app/features/pricing/engine/tests/` | No test exercises `ScenarioInputs.__post_init__`'s validation (e.g. `market_rent_ltr` required for LTR and must be `None` for PRIMARY/STR, and the STR/PRIMARY equivalents) even though this is real validation logic CQ-013 will rely on to catch malformed inputs early. | Add `test_scenario_inputs_validation.py` with `pytest.raises(ValueError)` cases for each strategy's required/forbidden field. |
| 6 | Minor | `backend/app/features/pricing/engine/tests/test_golden.py`, `test_cost_segregation.py` | `land_value_allocation`, `depreciable_building_basis`, `accelerated_basis_amount` and `break_even_rent_ltr` are never asserted through the actual `compute_quote()` orchestration path — only via the standalone `cost_segregation()` function, which bypasses `compute_quote`'s tuple-unpacking/field-wiring and rounding. Manually verified during this review that `compute_quote` wires all four correctly for the shared $342,000 STR golden scenario (68,400.00 / 273,600.00 / 68,400.00 / matches `total_monthly_payment`), so this is a coverage gap, not a bug — but a future refactor could silently reorder the tuple unpack without a test catching it. | Extend `test_full_scenario_matches_all_pinned_golden_values` to assert these four fields too. |

No critical findings. AC1–AC15 all independently re-verified as met (tests pass, ruff/mypy clean,
golden values re-derived by hand). Primary-loan field suppression (rule in AGENTS.md: primary
never shows rent/DSCR/cashflow/cost-seg/PPP) holds — verified directly on a non-golden PRIMARY
scenario, not just by reading the code.

## Review findings resolution (round 1)

Orchestrator reviewed the findings above and directed fixes for all six (CHANGES REQUESTED). All
implemented in this branch, TDD, all 8 golden tests still passing to the cent throughout.

| # | Severity | Resolution |
| --- | --- | --- |
| 1 | Major | Merged `phase-p0-p1` into this branch first (clean, brings CQ-004's pydantic dependency). `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` are now `pydantic.BaseModel` subclasses with `model_config = ConfigDict(frozen=True)`, per spec.md. Cross-field validation moved to `@model_validator(mode="after")`. See plan.md Decision 9. |
| 2 | Minor | `compute_quote` now raises `LtvOutOfRangeError(ValueError)` (defined in `quote_engine.py`) when `strategy == PRIMARY` and `ltv_pct > 0.97`, instead of silently falling through to `monthly_mi = None`. `mi_factor` itself is unchanged (still a pure lookup) — the guard lives at the orchestration level, where the "conventional financing caps at 97%" business rule actually belongs. See plan.md Decision 12. |
| 3 | Minor | `ltv_pct` (both `QuoteComputation.ltv_pct` and `mi_factor`'s parameter) is now a 0–1 fraction, matching every other `*_pct` field. `mi_factor` converts to the 0–100 scale internally before comparing against `DEFAULT_MI_MATRIX`. spec.md updated (orchestrator-authorised). See plan.md Decision 11. |
| 4 | Minor | `str_annual_rent_target` now takes `str_expense_ratio` and computes `total_payment * 12 / (1 - str_expense_ratio)`, reading `config.str_expense_ratio` from `compute_quote`, instead of a hardcoded `0.80`. spec.md updated (orchestrator-authorised); new test with a non-default ratio (0.25) proves the formula actually moves. See plan.md Decision 10. |
| 5 | Minor | Added `tests/test_scenario_inputs_validation.py` — 9 tests covering every strategy's required/forbidden field (LTR requires `market_rent_ltr` and forbids `str_gross_annual_revenue`; STR the reverse; PRIMARY forbids both; one positive-construction test per strategy). |
| 6 | Minor | `test_full_scenario_matches_all_pinned_golden_values` (test_golden.py) now asserts `land_value_allocation`, `depreciable_building_basis`, `accelerated_basis_amount` and `break_even_rent_ltr` through the real `compute_quote()` path, closing the coverage gap. |

Net: 41 tests now pass (was 28), all 8 golden values still exact to the cent (re-verified in the
Test log below), `ruff`/`mypy` clean on the whole `backend/` tree (not just this item's subtree, since
`make lint`'s actual scope is now reachable post-merge).

## Round 2 (re-review of `4ffad0e`/`baba4b8`)

Re-reviewed by a fresh subagent that did not write the fixes. Verified each round-1 resolution
against the actual diff, not just the plan.md/post-dev.md prose.

**Commands re-run**

| Command | Result |
| --- | --- |
| `uv run ruff check backend` | All checks passed! |
| `uv run ruff format --check backend` | 36 files already formatted |
| `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (full `make lint` mypy scope) | Success: no issues found in 36 source files |
| `uv run pytest backend -q` | 57 passed |
| `uv run pytest backend/app/features/pricing/engine -v` | 41 passed |
| `git merge-tree --write-tree origin/phase-p0-p1 HEAD` (current tip `8696af9`, post-CQ-006) | Clean merge, no conflicts (`bc99187...`) |
| Independent Decimal re-derivation of AC2/AC3 P&I and `str_annual_rent_target` at both the default and a non-default `str_expense_ratio` (own script, not the engine) | All match: `1515.87`, `1913.05`, default `27313.05`, `str_expense_ratio=0.25` → `29133.92` (matches the new `test_str_annual_rent_target_non_default_expense_ratio`) |
| Independent recompute of a primary 95% LTV / FICO 700 scenario against the new fraction-scale API (`ltv_pct=0.9500`, not `95.00`) | P&I/MI/PITIA all match `compute_quote`'s output |
| Construct a primary scenario at 99% LTV | `LtvOutOfRangeError` raised, message names both the actual and max LTV |
| Construct primary scenarios at exactly 97% LTV, and LTR/STR scenarios with an equivalent >97% "LTV" | Neither raises — cap is PRIMARY-only, as decided |
| Mutate a `ConfigSnapshot` field after construction | Raises `pydantic.ValidationError` (frozen), not `dataclasses.FrozenInstanceError` |
| Construct an LTR `ScenarioInputs` missing `market_rent_ltr` | Raises `pydantic.ValidationError` (a `ValueError` subclass), matching `test_scenario_inputs_validation.py` |

**Finding-by-finding verification**

| # | Round 1 severity | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Major | Resolved | `types.py` now defines `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` as `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True)`; `pydantic`/`pydantic-settings` confirmed present in `pyproject.toml`/`uv.lock` post-merge. Matches spec.md's binding Public API exactly. |
| 2 | Minor | Resolved | `quote_engine.py` defines `LtvOutOfRangeError(ValueError)` and `compute_quote` raises it for `strategy == PRIMARY and ltv > 0.97`, before any MI/payment math runs. Confirmed by direct construction above; `test_ltv_over_97_percent_on_primary_raises`/`_at_97_percent_..._does_not_raise`/`_on_investment_does_not_raise` cover the boundary and the strategy gate. |
| 3 | Minor | Resolved | `ltv_pct` is a 0–1 fraction everywhere (`ltv_pct()` helper, `QuoteComputation.ltv_pct`, `mi_factor`'s parameter); `QuoteComputation.ltv_pct` now carries an inline comment stating the scale explicitly (the original ask was for the field itself to be documented, not just the helper function — done). `mi_factor` converts to 0–100 internally before the band lookup; spec.md's own text updated to `ltv_pct <= 0.80`/`> 0.80` consistently. |
| 4 | Minor | Resolved | `str_annual_rent_target(total_payment, str_expense_ratio)` now computes `total_payment * 12 / (1 - str_expense_ratio)` and `compute_quote` passes `config.str_expense_ratio`; spec.md's formula line updated to match. `test_str_annual_rent_target_non_default_expense_ratio` (ratio 0.25 → $29,133.92) independently re-derived above and matches — proves the formula genuinely reads the snapshot now, closing the reproducibility-principle tension flagged in round 1. |
| 5 | Minor | Resolved | New `tests/test_scenario_inputs_validation.py`, 9 tests, one per required/forbidden field per strategy plus one valid-construction test per strategy; all pass. |
| 6 | Minor | Resolved | `test_full_scenario_matches_all_pinned_golden_values` (`test_golden.py`) now asserts `land_value_allocation == 68400.00`, `depreciable_building_basis == 273600.00`, `accelerated_basis_amount == 68400.00` and `break_even_rent_ltr == 2704.11` directly through `compute_quote()`, closing the coverage gap exactly as directed. Confirmed by reading the committed test file, not just re-deriving the values by hand. |

**New (round 2) observations — informational, not blocking**

- **CI has no run to check for this branch.** `gh run list --repo SIDDHESHCHAUDHARI2K24/clear-quote-tql --branch cq-008-quote-engine` returns empty. Root cause: this branch's merge commit (`4ffad0e`) merged `phase-p0-p1` at `cf32afd` (01:12:42), which predates CQ-006 adding `.github/workflows/ci.yml` to `phase-p0-p1` (landed at `8696af9`, 01:23:51). Since GitHub Actions runs whatever workflow file exists at the pushed commit, and `cq-008-quote-engine`'s `HEAD` has no `.github/workflows/ci.yml` at all (`git show HEAD:.github/workflows/ci.yml` → does not exist), no CI job has ever been scheduled for this branch — not a failure, there is simply nothing to run. `git merge-tree --write-tree origin/phase-p0-p1 HEAD` (current tip) is still a clean, conflict-free merge. I ran the exact `backend` job steps from `ci.yml` locally (`ruff check`/`ruff format --check`/`mypy` with the identical path list/`pytest backend`) and all pass. Recommend the branch pick up current `phase-p0-p1` (or merge as-is and let the resulting `phase-p0-p1` push run CI) rather than waiting on a run that cannot start on this exact commit.

**Verdict: no critical/major findings remain open.** All 6 round-1 findings resolved and independently re-verified against the actual code (not just the prose). Ready to merge on the engine's own merits; the CI-gap above is a branch-freshness housekeeping item, not a defect in this item's code.

## How to test manually

1. `cp .env.example .env` (if not already present — needed for `backend/conftest.py` to import; see
   Follow-ups). Then `cd backend && uv run pytest app/features/pricing/engine -v` (or from repo root:
   `uv run pytest backend/app/features/pricing/engine -v`) — no DB, no services actually contacted.
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
- `docs/backlog/README.md`'s CQ-008 row was intentionally left at "To Do" — this item's brief
  explicitly excludes editing that file; the orchestrator should flip it to "In Review".
- A fresh clone/worktree needs a local `.env` (`cp .env.example .env`) before any `backend/` pytest
  run, including this item's — `backend/conftest.py` (CQ-004) is auto-collected for anything under
  `backend/` and reads `Settings()` at import time. No actual DB/Redis/etc. connection is required
  for this item's own tests (`create_async_engine` is lazy); see plan.md Decision 14.
