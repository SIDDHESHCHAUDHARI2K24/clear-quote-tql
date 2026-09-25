# CQ-012 — Post-development notes

## Summary

Built the 1003 verification rule engine as three files under
`backend/app/features/applications/verification/`: `schemas.py`
(`PartySnapshot`, `HousingSnapshot`, `ScenarioSnapshot`, `RuleResult`,
`VerificationContext`), `rules.py` (7 pure rule functions + `evaluate_rules()`,
no DB/clock/network), and `service.py` (`_build_context`, `write_flag`,
`resolve_flag`, `run_and_persist`). `phone_copy` and `no_co_applicant`
self-heal silently (`info` severity, never a `flags` row); `housing_history_24mo`,
`ssn_format` and `dob_format` (both borrower and co-borrower, distinct
`field_key`s) raise `blocking` flags; `assets_vs_ctc_reserves` (`blocking`)
and `dti_primary` (`warning`, primary-only) self-skip until a scenario is
priced. `write_flag`/`resolve_flag` are a plain upsert/resolve pair on
`(application_id, field_key, rule)`; `write_flag` is the exact function
CQ-013's OB-required-field validation stage will call for persona 7.
`run_and_persist` returns a `VerificationRunResult` (rule results, auto-fixes
applied, flags raised, flags resolved) and writes no `activity_events` itself
— that's CQ-011's job, one row per pipeline stage. 31 tests total (17
original + 14 from the review-round-1 fixes below), all passing;
`ruff`/`ruff format`/`mypy` clean on `backend/`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `VerificationContext` schema stub (illustrative) has no clock field | Added `as_of: date` | `dob_format` needs "not in the past"; AC2 requires `evaluate_rules` to be pure (same input → same output, no clock read inside it). `service._build_context` reads `date.today()` once and puts it on the context. See plan.md decision #3. |
| `ScenarioSnapshot`/`PartySnapshot`/`HousingSnapshot` field shapes not pinned | Defined minimally: `ScenarioSnapshot(total_cash_to_close, total_monthly_payment)`, `PartySnapshot(role, cell_phone, home_phone, ssn, dob)`, `HousingSnapshot(sequence, residence_years, residence_months)` | Spec names these types but doesn't pin their fields (unlike `RuleResult`); each carries exactly what its rules read. |
| `run_and_persist(...) -> list[RuleResult]`, "logs an `activity_events` row per auto-fix and per flag raised" | `run_and_persist(...) -> VerificationRunResult`; writes no `activity_events` | Review round 1, finding 1 (MAJOR) — CQ-011 owns one `activity_events` row per pipeline stage; this item's own per-rule rows would break CQ-011 spec.md AC5's exact row count. `spec.md` line ~71 updated (orchestrator-authorised). See plan.md decision #11. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_personas.py::test_persona_8_housing_flag backend/app/features/applications/verification/tests/test_personas.py::test_persona_7_write_flag -v` — both pass. |
| AC2 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_evaluate_rules_is_pure -v` — pass. |
| AC3 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_service.py::test_auto_fix_rules -v` — pass (asserts `home_phone == cell_phone`, `no_co_applicant_check is True`, no `flags` row for either field, and — post review-round-1 — `run_result.auto_fixed` names both rules and `run_result.flags_raised == []`). |
| AC4 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_ssn_dob_format -v` — pass (8-digit SSN and future DOB both fail `blocking`; well-formed input passes). |
| AC5 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_rules.py::test_pricing_stage_rules_skip_without_scenario -v` — pass (asserts the rule ids are absent from the result list, not present-and-failing). |
| AC6 | Pass | `uv run pytest backend/app/features/applications/verification/tests/test_service.py::test_write_flag_upserts -v` — pass (two calls, one unresolved row). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| New tests (isolated) | `uv run pytest backend/app/features/applications/verification -q` | 31 passed (17 original + 14 from review-round-1 fixes) |
| Full backend suite | `uv run pytest backend -q` | 116 passed (85 pre-existing + 31 verification), 1 pre-existing deprecation warning unrelated to this item |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 118 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 118 source files |
| `make lint` (backend portion) | `make lint` | Backend (ruff/ruff format/mypy) all clean. The `pnpm -r run lint` step fails in this worktree with `eslint: command not found` / `node_modules missing` — pre-existing local environment state (no `pnpm install` has been run in this worktree; this item touches no frontend file). CI (which does run `pnpm install --frozen-lockfile`) confirms the frontend job is unaffected — see below. |
| CI | `git push -u origin cq-012-verification-rules`; `gh run list --repo SIDDHESHCHAUDHARI2K24/clear-quote-tql --branch cq-012-verification-rules`; `gh run watch 36101066349 --repo SIDDHESHCHAUDHARI2K24/clear-quote-tql --exit-status` | Commit `e751ff5` pushed to `origin/cq-012-verification-rules`. Run id **36101066349** (workflow `CI`) — both jobs green: `frontend` (pnpm install, lint, typecheck, prettier --check, test) passed in 27s; `backend` (ruff check, ruff format --check, mypy, pytest) passed in 45s. `gh run watch --exit-status` exited 0. |

## Review findings (stage 6)

Reviewed by a fresh subagent that did not write this code, against `spec.md`, `plan.md`, `AGENTS.md`, `docs/design/system-design.md`, and the consuming items' specs (`CQ-011-temporal-pipeline`, `CQ-013-pricing-service`).

### Commands re-run

| Command | Result |
| --- | --- |
| `uv run pytest backend/app/features/applications/verification -v` | 17 passed |
| `uv run pytest backend -q` | 102 passed, 1 pre-existing warning |
| `uv run ruff check backend` | All checks passed |
| `uv run ruff format --check backend` | 118 files already formatted |
| `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 118 source files |
| `pnpm install` (worktree had no `node_modules`) | Installed cleanly, no changes committed |
| `make lint` (full, incl. frontend) | All green: ruff, ruff format, mypy, eslint (4 workspaces), tsc (4 workspaces), prettier --check |
| `gh run view 36101066349 --log` | CI green; log shows `test_personas.py`, `test_rules.py`, `test_service.py` actually collected and run; `102 passed, 1 warning in 3.62s` |
| `gh run view 36101149689 --log` | CI green; same verification tests present; `102 passed, 1 warning in 12.89s` |
| `git merge-tree --write-tree phase-p0-p1 HEAD` | Clean (single tree hash printed, no conflict markers) — merges cleanly against the branch CQ-009 is landing on top of |

All post-dev.md claims verified independently; no discrepancies found between the log and re-run output.

### Findings

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | major | `backend/app/features/applications/verification/service.py:224-258` | `run_and_persist` writes its own `activity_events` row (`verification.auto_fixed` / `verification.flag_raised`) per rule outcome, in addition to whatever stage-level row CQ-011's `verify_application` activity logs. `no_co_applicant` auto-fires whenever no co-borrower party exists, and `application_parties.no_co_applicant_check` defaults to `False` with nothing else in the codebase setting it true (`backend/app/features/applications/models.py:104`) — so this fires for every single-borrower persona, including CQ-011's "none"-defect happy-path personas (Marcus Hale, Kathleen, Priya, Daniel, Sam Reed, Grace, Luis). Once CQ-011 wires `run_and_persist` into `verify_application`, `docs/backlog/CQ-011-temporal-pipeline/spec.md` AC5 ("Exactly one `activity_events` row per completed stage... Marcus Hale happy path (6 rows)") will fail: the Verify stage alone will produce CQ-011's own `pipeline.verified` row plus this item's extra `verification.auto_fixed` row(s). This is directed by this item's own `spec.md:71` ("logs an `activity_events` row per auto-fix and per flag raised"), which conflicts with CQ-011 `spec.md`'s literal AC5 count — the conflict is not logged as a `Decision` in `plan.md`. | Log a `Decision:` in `plan.md` flagging the cross-item conflict for CQ-011 to reconcile before it starts (e.g. drop the per-rule `activity_events` writes from `run_and_persist` and let the CQ-011 activity log the one pinned row per stage, or get CQ-011's AC5 revised to account for `verification.*` rows). Do not leave both specs' literal wording standing as-is. |
| 2 | minor | `docs/backlog/CQ-012-verification-rules/plan.md:16`, `post-dev.md:66`, `docs/backlog/CQ-012-verification-rules/handoff.md` | Flags never auto-resolve once a rule that previously failed later passes (plan.md decision #8). Confirmed this does **not** break CQ-011's `verifying → ready_to_price` gate — that transition is derived from the freshly-returned `list[RuleResult]` each run, not from querying the `flags` table (`docs/backlog/CQ-011-temporal-pipeline/spec.md` activity table, `verify_application` row). But re-reading CQ-011's actual spec text end to end, no item currently takes ownership of clearing stale `flags` rows either, so once CQ-028 renders per-tab flag counts, a fixed-then-resumed application (e.g. Ben Ford after his housing history is corrected) will keep showing a permanently unresolved `blocking` flag despite reaching `priced` — at odds with `system-design.md:110` ("flags list the field and the rule that failed") and the `NeedsAttention --> Verifying: LO resolves` loop (`system-design.md:79`). Separately, the claimed mitigation ("Flagged as a follow-up in handoff.md", plan.md decision #8; repeated in post-dev.md's Follow-ups) is not actually present — `handoff.md` is still the unfilled template. | Record the actual follow-up in `handoff.md` (not just plan.md/post-dev.md), and raise a Kaneo comment so whoever picks up CQ-011/CQ-028 explicitly decides who resolves stale flags — today nobody does. |
| 3 | minor | `backend/app/features/applications/verification/rules.py:122-161`; decision at `plan.md:9` | `ssn_format`/`dob_format` validate only the primary (`BORROWER`-role) party. `data-field-catalog.md` §1 does define `co_borrower_ssn` (masked) as a real field (though no `co_borrower_dob`), and `system-design.md:114` (Binding per `AGENTS.md`) describes the Borrowers tab as covering "Borrower and co-borrower: name, SSN (masked), DOB... validates formats" — format validation for the whole tab, not primary only. Persona 6 (Tom & Lisa Brandt, has a co-borrower) has no LOS defect today so this gap isn't exercised by any test/persona, but a malformed co-borrower SSN would currently pass through undetected. | Log this as a `Decision:`/Kaneo comment for a future item (co-borrower SSN format rule with its own `field_key`, e.g. `co_borrower_ssn`) rather than leaving it as a silently-narrowed scope call. |
| 4 | minor | `backend/app/features/applications/verification/service.py:54-75` | `_latest_scenario_snapshot` (reads `Quote.computed` JSON and maps `cash_to_close`/`total_monthly_payment` onto `ScenarioSnapshot`) is never exercised by any test — no test constructs a real `Quote` row with a `computed` JSON blob and calls it or `run_and_persist` against an application that already has a priced `Quote`. All purity/AC5 tests build `ScenarioSnapshot` directly, bypassing this mapping code entirely. This is the one part of the module coupled to CQ-008/CQ-013's future `Quote.computed` JSON shape (flat keys assumed); a shape mismatch there would raise `KeyError` at runtime with zero current test coverage. | Add an integration test that inserts a `Quote` row with a realistic `computed` dict and asserts `_latest_scenario_snapshot`/`run_and_persist` reads it correctly. |
| 5 | minor | `backend/app/features/applications/verification/rules.py:100-119,164-190,193-226` | No test exercises the exact-boundary cases the spec calls out: `housing_history_24mo` at exactly 24 months, `assets_vs_ctc_reserves` at `assets_total == required`, `dti_primary` at exactly `0.45`. Code inspection confirms all three resolve correctly (`>=`/`<=` used, matching the spec's `<`/`>` framing), so this is a coverage gap, not a bug. | Add boundary-value test cases for all three rules. |
| 6 | minor | `backend/app/features/applications/verification/service.py:88-99` vs. `tests/test_rules.py::test_ssn_dob_format` | The DB-backed path (decrypting `ApplicationParty.ssn_encrypted` in `_build_context`, per plan.md decision #2) is never tested with a malformed SSN/DOB through `run_and_persist`; only the pure-unit test exercises the format logic, using hand-built `PartySnapshot`s. AC4 is technically satisfied, but the encrypted-column round-trip → flag path has no integration coverage. | Add an integration test with a malformed SSN/DOB on a real `ApplicationParty` row, asserting `run_and_persist` raises the expected flag. |

No critical findings. Money math: confirmed Decimal-only throughout `rules.py`/`service.py`; all CTC/PITIA numbers are read from `Quote.computed` (CQ-008 output), never recomputed. `write_flag`/`run_and_persist` signatures match `docs/backlog/CQ-011-temporal-pipeline/spec.md` and `docs/backlog/CQ-013-pricing-service/spec.md`'s usage exactly (positional `db, application_id` then `tab, field_key, rule, severity`; at the time of this review, `run_and_persist(application_id, db) -> list[RuleResult]` — the signature changed to `-> VerificationRunResult` in the round-1 fix below).

## Review round 1 fixes

All 6 findings addressed; orchestrator decisions and implementation in plan.md decisions #11–#16.

| # | Severity | Fix |
| --- | --- | --- |
| 1 | major | `run_and_persist` no longer writes `activity_events`. Added `service.VerificationRunResult` (dataclass: `rule_results`, `auto_fixed`, `flags_raised`, `flags_resolved`) as its new return type. `spec.md` line ~71 updated (orchestrator-authorised). Test: `test_run_and_persist_writes_no_activity_events`. |
| 2 | minor | Added `service.resolve_flag(db, application_id, field_key, rule) -> Flag \| None`; `run_and_persist` calls it for every non-auto-fixed, non-`info` `RuleResult` that passed. Tests: `test_run_and_persist_resolves_flag_once_rule_passes` (raise → fix → resolve, same row), `test_run_and_persist_leaves_flag_open_when_still_failing` (unchanged failure stays open). Real follow-up recorded in `handoff.md` (Handoff 1) — not just claimed this time. |
| 3 | minor | `ssn_format`/`dob_format` now validate every `BORROWER`/`CO_BORROWER` party present, with distinct `field_key`s (`borrower_ssn`/`co_borrower_ssn`, `borrower_dob`/`co_borrower_dob`). Tests: `test_ssn_dob_format_validates_co_borrower_with_distinct_field_keys` (pure), `test_ssn_dob_validate_co_borrower_with_distinct_field_keys` (DB-backed, Tom & Lisa Brandt-shaped fixture). |
| 4 | minor | Added `test_latest_scenario_snapshot_reads_quote_computed` (direct, real `Quote.computed` blob) and `test_run_and_persist_evaluates_pricing_rules_against_real_quote` (through `run_and_persist`). |
| 5 | minor | Added boundary tests: `test_housing_history_24mo_boundary_exactly_24_months_passes`/`_boundary_23_months_fails`; `test_assets_vs_ctc_reserves_boundary_exactly_equal_passes`/`_boundary_one_cent_short_fails`; `test_dti_primary_boundary_exactly_45_percent_passes`/`_boundary_just_over_45_percent_fails`. |
| 6 | minor | Added `test_run_and_persist_flags_malformed_ssn_via_db_decrypt_roundtrip`: real `ApplicationParty` row, `db.refresh()` forces the actual `EncryptedString` decrypt, then asserts `run_and_persist` raises the flag. |

### Commands re-run after the fixes

| Command | Result |
| --- | --- |
| `uv run pytest backend/app/features/applications/verification -q` | 31 passed |
| `uv run pytest backend -q` | 116 passed, 1 pre-existing warning |
| `uv run ruff check backend` | All checks passed |
| `uv run ruff format --check backend` | All files formatted |
| `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 118 source files |

## How to test manually

1. `cp .env.example .env` (gitignored; needed for `backend/conftest.py`/`app.core.config` to load).
2. `make up` (stack must be running; Postgres etc.).
3. `uv run pytest backend/app/features/applications/verification -v` — exercises all 17 new tests, including the two persona tests (Ben Ford / Aisha Coleman) against the real (test) database via `alembic upgrade head`.
4. `uv run pytest backend -q` — full backend suite, confirms no regressions.

## Follow-ups

Recorded for real in `handoff.md` (Handoff 1), not just here:

- CQ-011's `verify_application` activity must build its own `activity_events` row(s) from `run_and_persist`'s returned `VerificationRunResult` — CQ-012 no longer writes any itself (review round 1, finding 1).
- CQ-013's pricing service should call `write_flag`/`resolve_flag` symmetrically (raise on fail, resolve on pass) when it re-runs `evaluate_rules` after a scenario is (re)computed, the same way `run_and_persist` now does — otherwise a DTI/assets flag that clears on a later pricing pass won't resolve.
- `service._latest_scenario_snapshot` exists so `run_and_persist` is correct even for a re-verification pass on an already-priced application, but at the only wiring this item currently supports (CQ-011's Verify stage, before any scenario exists) it always resolves to `None` there; CQ-013's own pricing service is expected to call `evaluate_rules` directly with a freshly-computed `ScenarioSnapshot` per spec.md's "Two run times" section, not through `run_and_persist`.
- Wiring `run_and_persist` into the Temporal Verify activity is CQ-011's scope; wiring `write_flag` into the OB-required-field validation stage (persona 7) is CQ-013's scope. Neither exists in the codebase yet as of this item's completion — expected per spec.md's explicit note not to reach into that scope.
