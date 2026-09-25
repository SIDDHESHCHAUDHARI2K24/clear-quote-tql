# CQ-012 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision (superseded — see #11) | `ssn_format`/`dob_format` say "party `ssn`"/"party `dob`" generically, but `write_flag`'s upsert key `(application_id, field_key, rule)` has no party discriminator, and the fixed `field_key`s are `borrower_ssn`/`borrower_dob` | ~~These two rules run on the primary (`role == BORROWER`) party only~~. Review round 1 (finding 3) pointed out `system-design.md:114` (binding) describes the Borrowers tab format validation as covering "Borrower and co-borrower" together, and the catalog does define `co_borrower_ssn`. Reversed — see decision #11: both parties are now validated, with distinct field_keys, which also resolves the "no party discriminator" problem this decision worried about. |
| 2 | Decision | Spec: "`ssn_format`... party `ssn` (checked pre-encryption, at input time)" | `application_parties.ssn_encrypted` is a SQLAlchemy `TypeDecorator` (`EncryptedString`) that decrypts transparently on read — `party.ssn_encrypted` already yields plaintext to Python code whether read fresh off a newly-constructed row or round-tripped through Postgres. `PartySnapshot.ssn = party.ssn_encrypted` reconciles the "pre-encryption" note (the rule never touches ciphertext) without needing a second, undecrypted code path. |
| 3 | Decision | `evaluate_rules` must be a pure function (AC2: identical input → identical output, no clock), but `dob_format` needs "not in the past", which requires *a* clock | Add `VerificationContext.as_of: date` (not shown in the spec's illustrative schema stub) so the clock read happens once, in `service._build_context` (`date.today()`), and `evaluate_rules` stays deterministic given a fixed context — two calls with the same context (same `as_of`) return equal lists per AC2 regardless of wall-clock time. |
| 4 | Decision | `VerificationContext.latest_scenario: ScenarioSnapshot` needs `total_cash_to_close`/`total_monthly_payment`, but `scenarios` (CQ-007) stores only `inputs`/`config_snapshot` JSON — the *computed* PITIA/CTC live on `quotes.computed` (CQ-008's `QuoteComputation`, one row per priced option) | `service._latest_scenario_snapshot` reads the application's most-recently-priced `Quote` (`scenarios.application_id → quotes.scenario_id`, ordered by `priced_at` desc) and maps `computed["cash_to_close"]`/`computed["total_monthly_payment"]` onto `ScenarioSnapshot`'s spec-pinned field names. This reads already-computed money numbers — no new arithmetic — so it doesn't violate "money math lives only in `quote_engine`". At the Verify stage (CQ-011, this item's only current caller of `run_and_persist`) no `Quote` exists yet, so this always resolves to `None` there; it exists so `run_and_persist` is also correct for a future re-verification pass on an already-priced application. |
| 5 | Decision | `assets_total`/`liabilities_total`/`monthly_income` sourcing isn't spelled out beyond "assets"/"liabilities"/"employment" tables | `assets_total = SUM(assets.verified_amount)`, `liabilities_total = SUM(liabilities.monthly_payment)` (already pinned by `credit/models.py`'s own docstring), `monthly_income = SUM(employment.monthly_income)` — all scoped to the application, matching the "Assets & income" tab's combined-household framing. |
| 6 | Decision | `reserves_months` source | `settings.reserves_months_primary` when `application.occupancy == PRIMARY`, else `settings.reserves_months_investment` — both already seeded by CQ-007's `seed_settings_defaults` migration (2 / 6). |
| 7 | Decision | `RuleResult` (spec-pinned fields only: no `party_id`) needs to tell `run_and_persist` *which* `application_parties` row to auto-fix | Not needed: `phone_copy`/`no_co_applicant` only ever act on the primary party, so `run_and_persist` re-queries that one row (`role == BORROWER`) once and applies a `rule_id → attribute name` lookup (`phone_copy → home_phone`, `no_co_applicant → no_co_applicant_check`) directly, without adding fields to the pinned schema. |
| 8 | Decision (superseded — see #12) | Should a flag auto-resolve once its rule later passes (e.g. after the LO fixes the underlying data)? | ~~Out of scope for this item~~. Review round 1 (finding 2) confirmed no other item takes ownership of clearing stale `flags` either, and the claimed "flagged as a follow-up in handoff.md" mitigation wasn't actually written there — orchestrator directed implementing it here. See decision #12. |
| 9 | Decision | `dti_primary` division by `monthly_income == 0` is undefined by the spec's formula | Treated as failing (flagged, not skipped and not a crash) with a distinct message — `occupancy == primary` with `$0` income is itself a data problem worth surfacing, not a reason to hide the DTI check. |
| 10 | Decision | Local `.env` (same issue CQ-008 hit) | Copied `.env.example` → `.env` (gitignored) so `backend/conftest.py` (imported by every test) can build `Settings()`. No secrets committed. |

### Review round 1 fixes (orchestrator-directed, post-`92762a4` review)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 11 | Decision | Finding 1 (MAJOR): `run_and_persist` wrote its own `activity_events` row per auto-fix/flag, on top of CQ-011's own one-row-per-stage `verify_application` logging — `no_co_applicant` auto-fires for every single-borrower persona, so CQ-011 spec.md AC5's exact-row-count assertion (Marcus Hale: 6 rows) would break once wired | `run_and_persist` no longer writes `activity_events` at all. It now returns `service.VerificationRunResult` (`rule_results`, `auto_fixed`, `flags_raised`, `flags_resolved` — a plain dataclass, not the pure `schemas.py` types, since it holds ORM `Flag` rows) instead of a bare `list[RuleResult]`, so CQ-011's `verify_application` activity (or CQ-013's pricing service) can build whatever single stage-level `activity_events` row it needs from that. `spec.md` line ~71 updated (orchestrator-authorised) to match. |
| 12 | Decision | Finding 2: flags never auto-resolved once their rule passes again; the claimed handoff.md follow-up didn't exist | Added `service.resolve_flag(db, application_id, field_key, rule) -> Flag \| None`: resolves the existing unresolved row for that key if one exists, no-ops otherwise. `run_and_persist` now calls it for every non-auto-fixed, non-`info`-severity `RuleResult` that passed, alongside `write_flag` for the ones that still fail. Tested both directions: `test_run_and_persist_resolves_flag_once_rule_passes` (raise → fix data → resolve, same row, not duplicated) and `test_run_and_persist_leaves_flag_open_when_still_failing` (unchanged failure stays open across two runs). A real follow-up is now recorded in `handoff.md` (see Handoff 1) instead of being merely claimed. |
| 13 | Decision | Finding 3: `ssn_format`/`dob_format` validated the primary party only, but `system-design.md:114` (binding) describes Borrowers-tab format validation as covering the co-borrower too, and the catalog defines `co_borrower_ssn` | Reversed decision #1: both rules now iterate `context.parties` and emit one `RuleResult` per `BORROWER`/`CO_BORROWER` party present, with distinct `field_key`s (`borrower_ssn`/`co_borrower_ssn`, `borrower_dob`/`co_borrower_dob` — `co_borrower_dob` isn't in the catalog but is needed for the same reason `borrower_dob` is, per orchestrator direction). Same `rule_id` for both (`ssn_format`/`dob_format`); `write_flag`'s upsert key stays unambiguous because `field_key` now differs per party. Tested in both `test_rules.py` (pure) and `test_service.py` (DB-backed, Tom & Lisa Brandt-shaped co-borrower fixture). |
| 14 | Decision | Finding 4: `_latest_scenario_snapshot` had no test constructing a real `Quote.computed` blob | Added `test_latest_scenario_snapshot_reads_quote_computed` (direct) and `test_run_and_persist_evaluates_pricing_rules_against_real_quote` (through `run_and_persist`, proving `assets_vs_ctc_reserves`/`dti_primary` actually evaluate instead of self-skipping once a `Quote` row exists). |
| 15 | Decision | Finding 5: no boundary-value tests for the three inequality rules | Added exact-boundary tests: `housing_history_24mo` at 24 months (passes) and 23 months (fails); `assets_vs_ctc_reserves` at `assets_total == required` (passes) and one cent short (fails); `dti_primary` at exactly 0.45 (passes, per spec's `> 0.45` framing) and just over (fails). |
| 16 | Decision | Finding 6: the DB-backed decrypt path was never exercised with a malformed SSN, only the pure unit test | Added `test_run_and_persist_flags_malformed_ssn_via_db_decrypt_roundtrip`: constructs a real `ApplicationParty` with `ssn_encrypted="12345678"`, calls `db.refresh(party)` to force `EncryptedString.process_result_value` (the actual decrypt) to run, then asserts `run_and_persist` raises the `blocking` flag. |

## Why

Past builds broke on exactly two kinds of 1003 defects: silent-fixable ones (uncopied phone, unchecked "No co-applicant") and ones that need a human (thin housing history, bad SSN/DOB, insufficient assets, high DTI). This item is the pure rule engine plus the persistence service that turns those checks into `flags`/`field_values`/`application_parties` writes, and the one shared `write_flag` helper CQ-013's pricing-validation stage also calls (persona 7). Without it, CQ-011's Verify→NeedsAttention gate and CQ-028's tab flag counts have nothing real to read.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Schemas | `backend/app/features/applications/verification/schemas.py` (new) |
| Rules (pure) | `backend/app/features/applications/verification/rules.py` (new) |
| Service (I/O) | `backend/app/features/applications/verification/service.py` (new; review round 1 added `VerificationRunResult`, `resolve_flag`, removed `activity_events` writes) |
| Tests | `backend/app/features/applications/verification/tests/test_rules.py`, `test_service.py`, `test_personas.py` (new) |
| Backlog docs | `docs/backlog/CQ-012-verification-rules/plan.md`, `post-dev.md`, `handoff.md`, `spec.md` (line ~71, orchestrator-authorised edit — see decision #11) |
| Local env | `.env` (new, gitignored, copied from `.env.example`; not committed) |

`backend/app/features/applications/verification/models.py` (`Flag`, `FieldValue`) is CQ-007's — read, not modified.

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | `schemas.py`: `PartySnapshot`, `HousingSnapshot`, `ScenarioSnapshot`, `RuleResult`, `VerificationContext` | — | `schemas.py` | (exercised by T2/T3 tests) |
| T2 | `rules.py`: 7 pure rule functions + `evaluate_rules()` | T1 | `rules.py` | `test_rules.py` |
| T3 | `service.py`: `_build_context`, `_latest_scenario_snapshot`, `write_flag`, `run_and_persist` | T1, T2 | `service.py` | `test_service.py`, `test_personas.py` |
| T4 | Lint/type clean-up | T1–T3 | all | `ruff check`, `mypy` |

## Wave schedule (stage 3)

Single-agent, sequential (one small module, no frontend/contract dependency, nothing else can consume this yet) — T1 → T2 → T3 → T4, TDD within each.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `pytest backend/app/features/applications/verification/tests/test_personas.py::test_persona_8_housing_flag` and `::test_persona_7_write_flag` |
| AC2 | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_evaluate_rules_is_pure` |
| AC3 | `pytest backend/app/features/applications/verification/tests/test_service.py::test_auto_fix_rules` |
| AC4 | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_ssn_dob_format` |
| AC5 | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_pricing_stage_rules_skip_without_scenario` |
| AC6 | `pytest backend/app/features/applications/verification/tests/test_service.py::test_write_flag_upserts` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
