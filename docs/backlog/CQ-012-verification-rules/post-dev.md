# CQ-012 — Post-development notes

## Summary

Built the 1003 verification rule engine as three files under
`backend/app/features/applications/verification/`: `schemas.py`
(`PartySnapshot`, `HousingSnapshot`, `ScenarioSnapshot`, `RuleResult`,
`VerificationContext`), `rules.py` (7 pure rule functions + `evaluate_rules()`,
no DB/clock/network), and `service.py` (`_build_context`, `write_flag`,
`run_and_persist`). `phone_copy` and `no_co_applicant` self-heal silently
(`info` severity, never a `flags` row); `housing_history_24mo`, `ssn_format`
and `dob_format` raise `blocking` flags; `assets_vs_ctc_reserves` (`blocking`)
and `dti_primary` (`warning`, primary-only) self-skip until a scenario is
priced. `write_flag` is a plain upsert on `(application_id, field_key, rule)`
and is the exact function CQ-013's OB-required-field validation stage will
call for persona 7. 17 new tests, all passing; `ruff`/`ruff format`/`mypy`
clean on `backend/`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `VerificationContext` schema stub (illustrative) has no clock field | Added `as_of: date` | `dob_format` needs "not in the past"; AC2 requires `evaluate_rules` to be pure (same input → same output, no clock read inside it). `service._build_context` reads `date.today()` once and puts it on the context. See plan.md decision #3. |
| `ScenarioSnapshot`/`PartySnapshot`/`HousingSnapshot` field shapes not pinned | Defined minimally: `ScenarioSnapshot(total_cash_to_close, total_monthly_payment)`, `PartySnapshot(role, cell_phone, home_phone, ssn, dob)`, `HousingSnapshot(sequence, residence_years, residence_months)` | Spec names these types but doesn't pin their fields (unlike `RuleResult`); each carries exactly what its rules read. |
| — | `ssn_format`/`dob_format` scoped to the primary (`BORROWER`-role) party only | `write_flag`'s upsert key has no party discriminator, and the catalog treats `borrower_ssn`/`borrower_dob` as primary-borrower-specific fields (distinct from `co_borrower_ssn`; no `co_borrower_dob` exists). See plan.md decision #1. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_personas.py::test_persona_8_housing_flag backend/app/features/applications/verification/tests/test_personas.py::test_persona_7_write_flag -v` — both pass. |
| AC2 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_evaluate_rules_is_pure -v` — pass. |
| AC3 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_service.py::test_auto_fix_rules -v` — pass (asserts `home_phone == cell_phone`, `no_co_applicant_check is True`, and no `flags` row for either field). |
| AC4 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_ssn_dob_format -v` — pass (8-digit SSN and future DOB both fail `blocking`; well-formed input passes). |
| AC5 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_pricing_stage_rules_skip_without_scenario -v` — pass (asserts the rule ids are absent from the result list, not present-and-failing). |
| AC6 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_service.py::test_write_flag_upserts -v` — pass (two calls, one unresolved row). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| New tests (isolated) | `uv run pytest backend/app/features/applications/verification -q` | 17 passed |
| Full backend suite | `uv run pytest backend -q` | 102 passed (85 pre-existing + 17 new), 1 pre-existing deprecation warning unrelated to this item |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 118 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 118 source files |
| `make lint` (backend portion) | `make lint` | Backend (ruff/ruff format/mypy) all clean. The `pnpm -r run lint` step fails in this worktree with `eslint: command not found` / `node_modules missing` — pre-existing local environment state (no `pnpm install` has been run in this worktree; this item touches no frontend file). Not this item's regression. |
| CI | `gh run watch` on push | See below |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |

(Empty — stage 6 review is done afterwards by a fresh subagent that did not write this code.)

## How to test manually

1. `cp .env.example .env` (gitignored; needed for `backend/conftest.py`/`app.core.config` to load).
2. `make up` (stack must be running; Postgres etc.).
3. `uv run pytest backend/app/features/applications/verification -v` — exercises all 17 new tests, including the two persona tests (Ben Ford / Aisha Coleman) against the real (test) database via `alembic upgrade head`.
4. `uv run pytest backend -q` — full backend suite, confirms no regressions.

## Follow-ups

- `write_flag`/`run_and_persist` never auto-resolve a previously-raised flag once its rule later passes (plan.md decision #8). Not required by any AC here; whoever wires the Verify stage's re-run path (CQ-011) or a future item should decide whether re-running `run_and_persist` on an already-flagged application should resolve stale flags.
- `service._latest_scenario_snapshot` exists so `run_and_persist` is correct even for a re-verification pass on an already-priced application, but at the only wiring this item currently supports (CQ-011's Verify stage, before any scenario exists) it always resolves to `None`; CQ-013's own pricing service is expected to call `evaluate_rules` directly with a freshly-computed `ScenarioSnapshot` per spec.md's "Two run times" section, not through `run_and_persist`.
- Wiring `run_and_persist` into the Temporal Verify activity is CQ-011's scope; wiring `write_flag` into the OB-required-field validation stage (persona 7) is CQ-013's scope. Neither exists in the codebase yet as of this item's completion — expected per spec.md's explicit note not to reach into that scope.
