# CQ-008 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Roadmap lists CQ-004 as a dependency | The engine is pure (no I/O, no DB, no FastAPI). The orchestrator started this item in parallel with CQ-004. No code under `backend/app/core/`, `backend/conftest.py`, `backend/app/main.py`, the Makefile, or pyproject tool config is touched or required to make `uv run pytest backend/app/features/pricing/engine` pass standalone. |
| 2 | Decision | Spec says `ScenarioInputs`/`ConfigSnapshot`/`QuoteComputation` are "frozen Pydantic v2 model(s)" | `pyproject.toml` currently has `dependencies = []` — pydantic is not yet a project dependency (CQ-004 is the item that adds FastAPI + pydantic-settings). Per the execution brief, this item must not edit `pyproject.toml`/add dependencies, and must stop and report instead of adding one. Since nothing in this item's scope needs pydantic's validation/serialization machinery (pure functions, no JSON boundary, no I/O), decided to implement all three as stdlib `@dataclass(frozen=True, kw_only=True)` with `__post_init__` validation. Same immutability guarantee, zero new dependency, keeps the module import-clean for `uv run pytest backend/app/features/pricing/engine` in isolation. When CQ-004/CQ-013 land pydantic as a real dependency, these can be re-expressed as pydantic models without changing `compute_quote`'s signature or field names, if desired. Logged as a deviation in `post-dev.md`. |
| 3 | Decision | `kw_only=True` for the three dataclasses | Spec lists `ScenarioInputs` fields with defaults (`hoa_monthly=0`, …) interleaved before non-default fields (`strategy`, `fico`, …) in prose order. Plain positional dataclasses forbid a required field after a defaulted one. `kw_only=True` (Python 3.12) matches how a Pydantic model is actually constructed (by keyword) and preserves the spec's documented field order without reordering. |
| 4 | Decision | `mi_factor` signature has no `strategy` parameter, but spec text says it returns `None` when `strategy != PRIMARY` | Read literally: `mi_factor(ltv_pct, fico, config)` is a pure LTV×FICO lookup with no strategy awareness. `compute_quote` is the caller that only invokes `mi_factor` when `strategy == PRIMARY`, and sets `monthly_mi = None` unconditionally for LTR/STR. This reconciles the signature (binding) with the prose (behavioural note about the overall system, not the function itself). `test_no_mi_on_investment` exercises this via `compute_quote`, not `mi_factor` directly. |
| 5 | Decision | `str_annual_rent_target` formula | Spec's formula is `total_monthly_payment × 12 / 0.80`, a literal constant, not `1 − config.str_expense_ratio`. Implemented as a hardcoded `Decimal("0.80")` per the pinned formula text, even though it numerically coincides with the default `str_expense_ratio`. If `str_expense_ratio` is ever reconfigured, this constant intentionally does not move — that's what the spec pins. |
| 6 | Decision | MI matrix, DSCR buckets, `reserves_months_*` values | Already pinned as invented-for-realism decisions in spec.md itself; implemented exactly as tabulated there (no further decision needed). |
| 7 | Decision | `ltv_pct` scale | `mi_factor(ltv_pct, ...)` and the MI band table are written on a 0–100 percentage scale ("80.01–85.00%"), not a 0–1 fraction (unlike `down_payment_pct`, `title_rate_pct`, etc., which are fractions per the `ConfigSnapshot` defaults table, e.g. `title_rate_pct: 0.007`). `QuoteComputation.ltv_pct` is therefore stored as `(1 − down_payment_pct) × 100`, rounded to 2dp. |
| 8 | Decision | Golden fixture construction | The spec's AC2–AC9 golden values come from more than one reference scenario (AC4's PITIA $1,820.87 is independent of AC5–AC9's shared $342,000/20%-down/7.5% STR scenario — confirmed by cross-checking: $342,000 × 0.80 = $273,600, whose P&I at 7.5% is exactly AC3's $1,913.05, and $2,440 / $2,704.11 ties AC6/AC7/AC8/AC9 together). Rather than force one giant fixture, `quote_engine.py` exposes small per-formula functions (`principal_and_interest`, `underwritten_str_rent`, `dscr_ratio`, `cost_segregation`, `cap_rate_pct`, `str_annual_rent_target`, `monthly_cashflow_incl_tax`, …) in addition to `compute_quote`, so each AC is tested against the exact numbers the spec pins, plus one full `compute_quote` integration test (AC14) proving the end-to-end pipeline does not round intermediate values. |

## Why

Every money number Clear Quote shows (LO preview, borrower report, PDFs) must come from one pure, fully-tested calculation module so numbers are never computed twice, never drift, and never touch a float. This item builds that module in isolation so CQ-013 (pricing service) can call it once the pipeline exists.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Engine types | `backend/app/features/pricing/engine/types.py` (new) |
| MI matrix | `backend/app/features/pricing/engine/mi_matrix.py` (new) |
| Engine | `backend/app/features/pricing/engine/quote_engine.py` (new) |
| Package markers | `backend/app/features/__init__.py`, `backend/app/features/pricing/__init__.py`, `backend/app/features/pricing/engine/__init__.py` (new, minimal) |
| Tests | `backend/app/features/pricing/engine/tests/test_golden.py`, `test_pi.py`, `test_mi_matrix.py`, `test_dscr_bucket.py`, `test_cost_segregation.py`, `test_cash_to_close.py`, `test_config_snapshot.py` (new) |
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
