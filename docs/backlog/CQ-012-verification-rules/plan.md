# CQ-012 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `ssn_format`/`dob_format` say "party `ssn`"/"party `dob`" generically, but `write_flag`'s upsert key `(application_id, field_key, rule)` has no party discriminator, and the fixed `field_key`s are `borrower_ssn`/`borrower_dob` | These two rules run on the primary (`role == BORROWER`) party only, like `phone_copy`/`no_co_applicant`. The data-field-catalog treats `borrower_ssn`/`borrower_dob` as distinct fields from `co_borrower_ssn` (no `co_borrower_dob` exists at all) — CQ-012's rule table names the primary-borrower field, not a per-party check. If a co-borrower's SSN/DOB needs validating, that is a future item's rule with its own `field_key`. |
| 2 | Decision | Spec: "`ssn_format`... party `ssn` (checked pre-encryption, at input time)" | `application_parties.ssn_encrypted` is a SQLAlchemy `TypeDecorator` (`EncryptedString`) that decrypts transparently on read — `party.ssn_encrypted` already yields plaintext to Python code whether read fresh off a newly-constructed row or round-tripped through Postgres. `PartySnapshot.ssn = party.ssn_encrypted` reconciles the "pre-encryption" note (the rule never touches ciphertext) without needing a second, undecrypted code path. |
| 3 | Decision | `evaluate_rules` must be a pure function (AC2: identical input → identical output, no clock), but `dob_format` needs "not in the past", which requires *a* clock | Add `VerificationContext.as_of: date` (not shown in the spec's illustrative schema stub) so the clock read happens once, in `service._build_context` (`date.today()`), and `evaluate_rules` stays deterministic given a fixed context — two calls with the same context (same `as_of`) return equal lists per AC2 regardless of wall-clock time. |
| 4 | Decision | `VerificationContext.latest_scenario: ScenarioSnapshot` needs `total_cash_to_close`/`total_monthly_payment`, but `scenarios` (CQ-007) stores only `inputs`/`config_snapshot` JSON — the *computed* PITIA/CTC live on `quotes.computed` (CQ-008's `QuoteComputation`, one row per priced option) | `service._latest_scenario_snapshot` reads the application's most-recently-priced `Quote` (`scenarios.application_id → quotes.scenario_id`, ordered by `priced_at` desc) and maps `computed["cash_to_close"]`/`computed["total_monthly_payment"]` onto `ScenarioSnapshot`'s spec-pinned field names. This reads already-computed money numbers — no new arithmetic — so it doesn't violate "money math lives only in `quote_engine`". At the Verify stage (CQ-011, this item's only current caller of `run_and_persist`) no `Quote` exists yet, so this always resolves to `None` there; it exists so `run_and_persist` is also correct for a future re-verification pass on an already-priced application. |
| 5 | Decision | `assets_total`/`liabilities_total`/`monthly_income` sourcing isn't spelled out beyond "assets"/"liabilities"/"employment" tables | `assets_total = SUM(assets.verified_amount)`, `liabilities_total = SUM(liabilities.monthly_payment)` (already pinned by `credit/models.py`'s own docstring), `monthly_income = SUM(employment.monthly_income)` — all scoped to the application, matching the "Assets & income" tab's combined-household framing. |
| 6 | Decision | `reserves_months` source | `settings.reserves_months_primary` when `application.occupancy == PRIMARY`, else `settings.reserves_months_investment` — both already seeded by CQ-007's `seed_settings_defaults` migration (2 / 6). |
| 7 | Decision | `RuleResult` (spec-pinned fields only: no `party_id`) needs to tell `run_and_persist` *which* `application_parties` row to auto-fix | Not needed: `phone_copy`/`no_co_applicant` only ever act on the primary party, so `run_and_persist` re-queries that one row (`role == BORROWER`) once and applies a `rule_id → attribute name` lookup (`phone_copy → home_phone`, `no_co_applicant → no_co_applicant_check`) directly, without adding fields to the pinned schema. |
| 8 | Decision | Should a flag auto-resolve once its rule later passes (e.g. after the LO fixes the underlying data)? | Out of scope for this item — no AC requires it, and the spec's rule table only says `run_and_persist` "writes non-auto-fixed failing results as `flags` rows"; it does not mention resolving passing ones. `write_flag` itself is a pure upsert-when-called helper (AC6). Flagged as a follow-up in `handoff.md` for whoever wires the Verify stage's re-run path (CQ-011) or a later item. |
| 9 | Decision | `dti_primary` division by `monthly_income == 0` is undefined by the spec's formula | Treated as failing (flagged, not skipped and not a crash) with a distinct message — `occupancy == primary` with `$0` income is itself a data problem worth surfacing, not a reason to hide the DTI check. |
| 10 | Decision | Local `.env` (same issue CQ-008 hit) | Copied `.env.example` → `.env` (gitignored) so `backend/conftest.py` (imported by every test) can build `Settings()`. No secrets committed. |

## Why

Past builds broke on exactly two kinds of 1003 defects: silent-fixable ones (uncopied phone, unchecked "No co-applicant") and ones that need a human (thin housing history, bad SSN/DOB, insufficient assets, high DTI). This item is the pure rule engine plus the persistence service that turns those checks into `flags`/`field_values`/`application_parties` writes, and the one shared `write_flag` helper CQ-013's pricing-validation stage also calls (persona 7). Without it, CQ-011's Verify→NeedsAttention gate and CQ-028's tab flag counts have nothing real to read.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Schemas | `backend/app/features/applications/verification/schemas.py` (new) |
| Rules (pure) | `backend/app/features/applications/verification/rules.py` (new) |
| Service (I/O) | `backend/app/features/applications/verification/service.py` (new) |
| Tests | `backend/app/features/applications/verification/tests/test_rules.py`, `test_service.py`, `test_personas.py` (new) |
| Backlog docs | `docs/backlog/CQ-012-verification-rules/plan.md`, `post-dev.md`, `handoff.md` (this item's own docs) |
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
