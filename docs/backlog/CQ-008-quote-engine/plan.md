# CQ-008 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Roadmap lists CQ-004 as a dependency | The engine is pure (no I/O, no DB, no FastAPI). The orchestrator started this item in parallel with CQ-004. No code under `backend/app/core/`, `backend/conftest.py`, `backend/app/main.py`, the Makefile, or pyproject tool config is touched or required to make `uv run pytest backend/app/features/pricing/engine` pass standalone. |
| 2 | Decision (superseded — see #9) | Spec says `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` are "frozen Pydantic v2 model(s)" | ~~`pyproject.toml` currently has `dependencies = []` — pydantic is not yet a project dependency... implement as stdlib dataclasses instead~~. This was true when the branch was cut from `d166cf1`, but the review (post-dev.md finding 1) caught that it went stale once `phase-p0-p1` merged CQ-004, which lands `pydantic-settings` (and pydantic) as a real dependency. Reverted to actual frozen Pydantic v2 models in decision #9 below. |
| 3 | Decision (superseded — see #9) | `kw_only=True` for the three dataclasses | No longer applicable — Pydantic models take keyword args natively, so the interleaved default/required field order from spec.md needs no `kw_only` workaround. |
| 4 | Decision | `mi_factor` signature has no `strategy` parameter, but spec text says it returns `None` when `strategy != PRIMARY` | Read literally: `mi_factor(ltv_pct, fico, config)` is a pure LTV×FICO lookup with no strategy awareness. `compute_quote` is the caller that only invokes `mi_factor` when `strategy == PRIMARY`, and sets `monthly_mi = None` unconditionally for LTR/STR. This reconciles the signature (binding) with the prose (behavioural note about the overall system, not the function itself). `test_no_mi_on_investment` exercises this via `compute_quote`, not `mi_factor` directly. Unchanged by review round 1. |
| 5 | Decision (superseded — see #10) | `str_annual_rent_target` formula | ~~Hardcoded `Decimal("0.80")` per the pinned formula text, not `1 − config.str_expense_ratio`~~. Review (finding 4) flagged this as a footgun: a reconfigured `str_expense_ratio` would silently stop matching the formula, in tension with "quotes are reproducible from their snapshot." Orchestrator authorised deriving from config instead — see decision #10. |
| 6 | Decision | MI matrix, DSCR buckets, `reserves_months_*` values | Already pinned as invented-for-realism decisions in spec.md itself; implemented exactly as tabulated there (no further decision needed). |
| 7 | Decision (superseded — see #11) | `ltv_pct` scale | ~~0–100 percentage scale, e.g. `95.00`~~. Review (finding 3) flagged the inconsistency with every other `*_pct` field being a 0–1 fraction. Orchestrator authorised switching to a 0–1 fraction — see decision #11. |
| 8 | Decision | Golden fixture construction | The spec's AC2–AC9 golden values come from more than one reference scenario (AC4's PITIA $1,820.87 is independent of AC5–AC9's shared $342,000/20%-down/7.5% STR scenario — confirmed by cross-checking: $342,000 × 0.80 = $273,600, whose P&I at 7.5% is exactly AC3's $1,913.05, and $2,440 / $2,704.11 ties AC6/AC7/AC8/AC9 together). Rather than force one giant fixture, `quote_engine.py` exposes small per-formula functions (`principal_and_interest`, `underwritten_str_rent`, `dscr_ratio`, `cost_segregation`, `cap_rate_pct`, `str_annual_rent_target`, `monthly_cashflow_incl_tax`, …) in addition to `compute_quote`, so each AC is tested against the exact numbers the spec pins, plus one full `compute_quote` integration test (AC14) proving the end-to-end pipeline does not round intermediate values. Unchanged by review round 1. |

### Review round 1 (orchestrator-directed fixes, post-`cd5d1eb` review)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 9 | Decision | Re-adopt Pydantic v2 for the three model types (finding 1, MAJOR) | Merged `phase-p0-p1` into this branch first (clean merge, brings CQ-004's `pydantic`/`pydantic-settings`/`conftest.py`). `ScenarioInputs`, `ConfigSnapshot`, `QuoteComputation` are now `pydantic.BaseModel` subclasses with `model_config = ConfigDict(frozen=True)`, exactly as spec.md pins. `ScenarioInputs`'s cross-field validation moved from `__post_init__` to a `@model_validator(mode="after")` raising `ValueError` (pydantic wraps this in `pydantic.ValidationError`, itself a `ValueError` subclass in v2, so `pytest.raises(ValueError)`-style assertions still work). Frozen-mutation now raises `pydantic.ValidationError` (`frozen_instance`), not `dataclasses.FrozenInstanceError`; `test_config_snapshot_frozen` updated accordingly. New `test_scenario_inputs_validation.py` covers every strategy's required/forbidden field (finding 5). |
| 10 | Decision | `str_annual_rent_target` reads `config.str_expense_ratio` (finding 4) | `str_annual_rent_target(total_payment, str_expense_ratio)` now computes `total_payment * 12 / (1 - str_expense_ratio)` instead of a hardcoded `/ 0.80`. At the default `str_expense_ratio = 0.20` this is still `/ 0.80` and reproduces AC4's golden $27,313.05 unchanged. Added `test_str_annual_rent_target_non_default_expense_ratio` (ratio 0.25 → $29,133.92) proving the formula actually reads the config now. spec.md's formula line updated (orchestrator-authorised edit to this item's own spec.md). |
| 11 | Decision | `ltv_pct` is now a 0–1 fraction (finding 3) | `QuoteComputation.ltv_pct` and `mi_factor`'s `ltv_pct` parameter are 0–1 fractions (e.g. `0.95`), matching every other `*_pct` field. `mi_factor` converts internally (`ltv_pct * 100`) before comparing against `DEFAULT_MI_MATRIX`'s own 0–100-scale band bounds (left as-is — still readable against spec.md's percentage table). Rounded to 4dp (`_LTV_PRECISION = Decimal("0.0001")`) rather than 2dp, to keep the same display precision as the old "2dp of percent" rule (e.g. `0.8750` == 87.50%). spec.md's MI-matrix section updated (orchestrator-authorised). |
| 12 | Decision | `LtvOutOfRangeError` for primary LTV > 97% (finding 2) | `mi_factor` itself is unchanged (a pure lookup; still returns `None` for an LTV above its tabulated bands — now documented as relying on the caller's guard). `compute_quote` raises `LtvOutOfRangeError(ValueError)` (defined in `quote_engine.py`) when `strategy == PRIMARY` and `ltv_pct > 0.97`, before computing MI or anything else, rather than silently returning `monthly_mi = None` for an out-of-range primary loan. Does not apply to LTR/STR (no conventional-MI concept there). Tests: `test_ltv_over_97_percent_on_primary_raises`, `test_ltv_at_97_percent_on_primary_does_not_raise` (97% itself is the max, not out of range), `test_ltv_over_97_percent_on_investment_does_not_raise`. |
| 13 | Decision | `compute_quote`-level assertions for cost-seg sub-fields and break-even rent (finding 6) | `test_full_scenario_matches_all_pinned_golden_values` (test_golden.py) now also asserts `land_value_allocation`, `depreciable_building_basis`, `accelerated_basis_amount` and `break_even_rent_ltr` through the real `compute_quote` orchestration path, not just the standalone `cost_segregation()` function — closing the coverage gap the review found (tuple-unpacking/field-wiring order was previously only manually verified, not tested). |
| 14 | Decision | Local `.env` needed post-merge | `backend/conftest.py` (CQ-004) is auto-collected by pytest for anything under `backend/`, and imports `app.core.config.get_settings()` at module load time, which requires every `Settings` field to be present. Running even `uv run pytest backend/app/features/pricing/engine` now needs a local `.env` (copied from `.env.example`) to exist — gitignored, not committed, no actual DB/Redis/etc. connection is made since `create_async_engine` is lazy. Flagged as a follow-up for whoever next clones this branch cold. |

## Why

Every money number Clear Quote shows (LO preview, borrower report, PDFs) must come from one pure, fully-tested calculation module so numbers are never computed twice, never drift, and never touch a float. This item builds that module in isolation so CQ-013 (pricing service) can call it once the pipeline exists.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Engine types | `backend/app/features/pricing/engine/types.py` (new) |
| MI matrix | `backend/app/features/pricing/engine/mi_matrix.py` (new) |
| Engine | `backend/app/features/pricing/engine/quote_engine.py` (new) |
| Package markers | `backend/app/features/__init__.py`, `backend/app/features/pricing/__init__.py`, `backend/app/features/pricing/engine/__init__.py` (new, minimal) |
| Tests | `backend/app/features/pricing/engine/tests/test_golden.py`, `test_pi.py`, `test_mi_matrix.py`, `test_dscr_bucket.py`, `test_cost_segregation.py`, `test_cash_to_close.py`, `test_config_snapshot.py`, `test_scenario_inputs_validation.py` (new, review round 1) |
| Backlog | `docs/backlog/CQ-008-quote-engine/plan.md`, `post-dev.md` (this item's own docs) |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Package scaffolding + `types.py` (enums, `ScenarioInputs`, `ConfigSnapshot`, `QuoteComputation`) | — | `__init__.py`×3, `types.py` | `test_config_snapshot.py` |
| T2 | `mi_matrix.py` table + `mi_factor` | T1 | `mi_matrix.py` | `test_mi_matrix.py` |
| T3 | `quote_engine.py`: P&I, PITIA, cash-to-close formulas | T1 | `quote_engine.py` | `test_pi.py`, `test_cash_to_close.py` |
| T4 | `quote_engine.py`: qualifying rent, DSCR, cashflow, cap rate, cost seg, `bucket_for_dscr` | T1, T2, T3 | `quote_engine.py` | `test_dscr_bucket.py`, `test_cost_segregation.py` |
| T5 | `compute_quote` orchestration + single-point rounding | T1–T4 | `quote_engine.py` | `test_golden.py` |
| T6 | Golden tests (AC1–AC9, AC14) | T5 | `test_golden.py` | — |
| T7 | Lint/type clean-up | T1–T6 | all | `ruff check`, `mypy` |

## Wave schedule (stage 3)

Single-agent, sequential (no parallel dispatch needed — one small module, TDD in order T1→T7).

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `pytest .../tests/test_golden.py` (whole file) |
| AC2 | `test_golden.py::test_pi_225000_at_7_125` |
| AC3 | `test_golden.py::test_pi_273600_at_7_500` |
| AC4 | `test_golden.py::test_str_annual_rent_target` |
| AC5 | `test_golden.py::test_str_underwritten_rent` |
| AC6 | `test_golden.py::test_dscr_ratio` |
| AC7 | `test_golden.py::test_cost_segregation_342k` |
| AC8 | `test_golden.py::test_cap_rate` |
| AC9 | `test_golden.py::test_cashflow_incl_tax_benefit` |
| AC10 | `test_mi_matrix.py::test_mi_ltv95_fico700_applies`, `::test_no_mi_at_80_ltv`, `::test_no_mi_on_investment` |
| AC11 | `test_dscr_bucket.py::test_dscr_bucket_boundaries` |
| AC12 | `test_cash_to_close.py::test_cash_to_close_with_credit`, `::test_cash_to_close_formula` |
| AC13 | `test_config_snapshot.py::test_config_snapshot_defaults`, `::test_config_snapshot_frozen` |
| AC14 | `test_golden.py::test_rounding_full_precision_internal` |
| AC15 | `ruff check backend/app/features/pricing/engine/`, `mypy backend/app/features/pricing/engine/` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
