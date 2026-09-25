# CQ-012 Verification rules

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-007 |
| Kaneo task | CQ-012 in Kaneo (task id `zaj9chc35lv1o16bf8hu4v18`) |
| Branch | `cq-012-verification-rules` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

The 1003 checks that broke past builds (uncopied phone, unchecked "No co-applicant") fix themselves silently, and the checks that need a human (thin housing history, bad SSN/DOB, insufficient assets, high DTI) show up as a flag with the exact field and rule that failed. When this is done, the tabs' green-check/flag-count UI (CQ-028) and the pipeline's Verifying → NeedsAttention gate (CQ-011) both have something real to read.

## Scope

1003 verification rules — phone copy, no-co-applicant, 24-month housing history, SSN/DOB format, assets vs. cash-to-close + reserves, DTI (primary only) — as pure functions, plus the service that persists their results into `flags`/`field_values`/`application_parties` and the shared `write_flag` helper other stages (pricing validation) reuse.

## Out of scope

- The `flags`/`field_values` table schemas (CQ-007) — this item only writes to them.
- Wiring rule evaluation into the Temporal "Verify" activity (CQ-011).
- The OB-required-field validation that raises `PricingValidationError` (CQ-009's `PricingClient`, called from CQ-013's pricing/enrichment service) — see the persona 7 note below; that is a different stage, not a 1003 rule.
- Rendering flags in the verification tabs (CQ-028) or gating the Send button (CQ-019/CQ-020).
- DTI computation for investment loans (design scopes DTI to primary only).

## References

- `docs/design/system-design.md` — "Application status machine", "LO Console" tab table (rows 1–4), Decisions log #14.
- `docs/design/data-field-catalog.md` — §1 (`no_co_applicant_check`, phone fields), §2 (housing history), §3 (`asset_sufficiency_check`), overrides O11, O12; "Why previous builds failed" list, items 1–2.
- `docs/backlog/CQ-007-data-model/spec.md` — `flags`, `field_values`, `application_parties`, `housing_history`, `assets`, `employment`, `liabilities`, `settings` (`reserves_months_primary`/`_investment`).

## Module layout

```
backend/app/features/applications/verification/
  rules.py     pure rule functions + evaluate_rules()
  schemas.py   VerificationContext, RuleResult
  service.py   run_and_persist(), write_flag() (shared helper)
  tests/
```

## Rule engine (pure, no I/O)

```python
# schemas.py
class RuleResult(BaseModel):
    rule_id: str
    tab: ApplicationTab
    field_key: str
    severity: FlagSeverity
    passed: bool
    message: str
    auto_fixed: bool = False
    fix_value: Any | None = None

class VerificationContext(BaseModel):
    occupancy: Occupancy
    parties: list[PartySnapshot]           # from application_parties
    housing_history: list[HousingSnapshot] # from housing_history, ordered by sequence
    assets_total: Decimal
    liabilities_total: Decimal
    monthly_income: Decimal
    reserves_months: int                   # settings, by occupancy
    latest_scenario: ScenarioSnapshot | None  # None until a scenario is priced

# rules.py
def evaluate_rules(context: VerificationContext) -> list[RuleResult]: ...
```

`evaluate_rules` is a pure function: given the same `VerificationContext` it always returns the same `list[RuleResult]`, with no DB session, no clock, no network. `service.run_and_persist(application_id: uuid.UUID, db: AsyncSession) -> VerificationRunResult` assembles the context, calls `evaluate_rules`, applies auto-fixes back onto `application_parties`, writes non-auto-fixed failing results as `flags` rows (via `write_flag`), and resolves any previously-raised flag whose rule now passes (via `resolve_flag`) — supporting the design's "LO fixes → resume" loop (`NeedsAttention -> Verifying: LO resolves`). **`run_and_persist` does not write `activity_events` rows.** CQ-011 owns exactly one `activity_events` row per completed pipeline stage (its own spec.md AC5); `VerificationRunResult` (rule results, auto-fixes actually applied, flags raised, flags resolved) carries everything the caller needs to build that one row itself, whether the caller is CQ-011's `verify_application` activity or CQ-013's pricing service. Rules whose required input is missing (no `latest_scenario` yet) are skipped, not failed.

`service.write_flag(db, application_id, tab, field_key, rule, severity) -> Flag` is the shared helper: it upserts a `flags` row (unresolved if one doesn't already exist for that `(application_id, field_key, rule)`) and is the same function CQ-013's OB-required-field validation stage calls for persona 7 (see below) — CQ-012 owns and tests this helper; CQ-013 owns calling it from the pricing/validate stage.

## Rules

| Rule id | Inputs | Tab | field_key | Outcome | Severity |
| --- | --- | --- | --- | --- | --- |
| `phone_copy` | primary party's `cell_phone`, `home_phone` | `borrowers` | `borrower_home_phone` | Auto-fix: if `home_phone` empty and `cell_phone` set, copy it | `info` (no `flags` row) |
| `no_co_applicant` | `has_co_borrower` (derived: does a `co_borrower` party row exist) | `borrowers` | `no_co_applicant_check` | Auto-fix: if no co-borrower party, set `no_co_applicant_check = true` | `info` (no `flags` row) |
| `housing_history_24mo` | `housing_history` rows, ordered by `sequence` | `housing` | `current_residence_years` | Flag if summed `residence_years*12 + residence_months` across rows < 24 and no prior address covers the gap | `blocking` |
| `ssn_format` | party `ssn` (checked pre-encryption, at input time) | `borrowers` | `borrower_ssn` | Flag if not exactly 9 digits (after stripping `-`) | `blocking` |
| `dob_format` | party `dob` | `borrowers` | `borrower_dob` | Flag if missing, not a valid date, or not in the past | `blocking` |
| `assets_vs_ctc_reserves` | `assets_total`, `latest_scenario.total_cash_to_close`, `reserves_months`, `latest_scenario.total_monthly_payment` | `assets` | `total_verified_assets` | Skipped if `latest_scenario is None`. Flag if `assets_total < total_cash_to_close + reserves_months * total_monthly_payment` | `blocking` |
| `dti_primary` | `liabilities_total`, `monthly_income`, `latest_scenario.total_monthly_payment`, `occupancy` | `credit` | `dti_ratio` | Only runs when `occupancy == primary` and `latest_scenario` is set. Flag if `(liabilities_total + total_monthly_payment) / monthly_income > 0.45` | `warning` |

**Decision — reserves.** The design says "reserves required" but never states a month count. `settings.reserves_months_primary = 2`, `settings.reserves_months_investment = 6` (the latter matches common DSCR-investor guidance). Config, not hardcoded, so Admin (Tier C) can change it without a migration.

**Decision — DTI threshold.** Not specified anywhere in the source docs. 45% back-end DTI, `warning` severity (visible on the Credit tab, does not block pipeline or Send) — a conservative, commonly-used conforming ceiling, chosen because this is a demo default an Admin can retune, not an underwriting commitment.

**Two run times.** `housing_history_24mo`, `ssn_format`, `dob_format`, `phone_copy`, `no_co_applicant` run at the pipeline's Verify stage (CQ-011), before any scenario exists. `assets_vs_ctc_reserves` and `dti_primary` need a priced scenario, so they self-skip at Verify and are re-run by CQ-013's pricing service every time a scenario is (re)computed — `evaluate_rules` is called both times with the same signature; only `VerificationContext.latest_scenario` differs.

## Persona coverage

- **Persona 8 (Ben Ford, 14 months at current address, no prior address on file)** — `housing_history_24mo` fails: `14 < 24` months, no prior row. `service.run_and_persist` writes a `flags` row (`tab=housing`, `field_key=current_residence_years`, `rule=housing_history_24mo`, `severity=blocking`). This is a CQ-012 rule end to end; tested directly here.
- **Persona 7 (Aisha Coleman, missing occupancy in the LOS record)** — **this is not a CQ-012 rule.** Her application reaches the pipeline's Validate stage (after Verify/Enrich succeed) where CQ-013's pricing/enrichment service calls `PricingClient.get_priced_products` (CQ-009) and catches `PricingValidationError(missing_fields=["Occupancy", ...])`; that stage calls this item's `service.write_flag(db, application_id, tab=ApplicationTab.pricing, field_key="occupancy_type", rule="ob_required_field", severity=FlagSeverity.blocking)` and the pipeline moves the application to `NeedsAttention` with the message "Cannot price: missing Occupancy" (system-design's exact wording). CQ-012's responsibility ends at providing and unit-testing `write_flag`; wiring it into the Validate stage is CQ-013/CQ-011's.

## Acceptance criteria

- [ ] AC1 — Rule tests pass; personas 7 and 8 raise their flags. *(roadmap exit check — persona 8 via a CQ-012 rule directly; persona 7 via `write_flag` called with the same parameters the Validate stage will use, since wiring that stage is CQ-013/CQ-011's scope)*
- [ ] AC2 — `evaluate_rules(context)` is provably pure: called twice with an identical `VerificationContext` (no DB, no mocks) returns equal `list[RuleResult]`.
- [ ] AC3 — `phone_copy` and `no_co_applicant` never produce a `flags` row; after `run_and_persist`, the party's `home_phone == cell_phone` and `no_co_applicant_check == True` when no co-borrower exists.
- [ ] AC4 — `ssn_format`/`dob_format` raise `blocking` flags on a malformed SSN (8 digits) and an invalid DOB (future date), and pass on well-formed input.
- [ ] AC5 — `assets_vs_ctc_reserves` and `dti_primary` are skipped (return no `RuleResult` at all, not a failing one) when `latest_scenario is None`, and evaluate correctly once one is supplied.
- [ ] AC6 — `write_flag` upserts: calling it twice with the same `(application_id, field_key, rule)` leaves exactly one unresolved `flags` row, not two.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Fixture-based | `pytest backend/app/features/applications/verification/tests/test_personas.py::test_persona_8_housing_flag` and `::test_persona_7_write_flag` |
| AC2 | Unit (pure) | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_evaluate_rules_is_pure` |
| AC3 | Integration (test DB) | `pytest backend/app/features/applications/verification/tests/test_service.py::test_auto_fix_rules` |
| AC4 | Unit | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_ssn_dob_format` |
| AC5 | Unit | `pytest backend/app/features/applications/verification/tests/test_rules.py::test_pricing_stage_rules_skip_without_scenario` |
| AC6 | Integration (test DB) | `pytest backend/app/features/applications/verification/tests/test_service.py::test_write_flag_upserts` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: reserves = 2 months PITIA (primary) / 6 months PITIA (investment), stored in `settings`.
- Decision: DTI warning threshold = 45% back-end, `warning` severity (non-blocking).
- Do not implement the Validate-stage wiring for persona 7 here — only `write_flag` and its test double. If CQ-013/CQ-011 aren't done yet when this item ships, that's expected; note it in `handoff.md` rather than reaching into those items' scope.
