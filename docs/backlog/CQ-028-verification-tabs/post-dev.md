# CQ-028 — Post-development notes

CQ-028 ships in two units. **CQ-028a** (this section, backend) owns every backend AC. **CQ-028b** (UI) appends its evidence below.

## Summary (CQ-028a)

The verification-tab API lives under `/api/v1/applications/{id}/…`:

- **Section reads** for borrowers, housing, credit, assets and property. Each field comes back as `{field_key, value, source, overridden, original_value}`, and each tab carries its open flags plus a summary: housing months, FICO bracket, pull type, DTI (primary only), the E11 consent summary, reserves and sufficiency, employment and income (primary only), the document checklist, and TBD/recommend/buy-box.
- **Edits:** field edits and reverts (`PUT/DELETE /fields/{key}`), row adds and edits for `housing_history`, `parties` and `liabilities`, and SSN reveal.
- **Actions:** import liabilities, the hard-pull consent request with its borrower email, property/buy-box `PATCH`, `PATCH` a document received, and `GET /reference/metros`.

After every edit, a re-verify hook re-runs the CQ-012 rules. It also re-validates OB-required fields when needed, logs `flag.raised`/`flag.resolved`, and resumes the CQ-011 workflow: it signals a running workflow, or starts one for a seeded application that has none. The `/field-values` pricing routes now write activity events too. All money ratios live in `pricing/engine/borrower_ratios.py`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Field edits reuse the CQ-013/CQ-017 override endpoints | The spec's own `PUT/DELETE /fields/{field_key}` handles 1003 fields. `/field-values` stays the path for the five pricing keys and gained events | `/field-values` only accepts five Decimal pricing keys, so it cannot set occupancy, phones or a DOB (plan #2) |
| "Resume … from its failed stage" | Signals `resume` to a running workflow. If none exists (seeded demo apps), it **starts** the pipeline, and `import_from_los` became import-once | demo-reset has no Temporal runs; without the guard, a started run would duplicate rows and overwrite the fix (plan #9) |
| "If no `error` flags remain" | Gate on `blocking` flags | `FlagSeverity` has no `error` (plan #8) |
| Metros "from the provider metro list" | Provider metros merged with a small static catalog | AC6 picks Orlando, which has no seeded listing (plan #17) |
| County from zip via mock lookup | Distinct `provider_listings.county` for the zip, falling back to the county sent in the request | No zip→county adapter exists (plan #16) |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 Aisha resolve → resume → Priced | ✅ backend | `test_resume_pipeline.py::test_resolve_flag_resumes_pipeline` (time-skipping Temporal, real worker; `PUT /fields/occupancy_type` → flags `[]`, `resume.reason=resumed`, workflow result `priced`, quotes > 0, events `field.edited`, `flag.resolved`, `pipeline.resume_requested`, then `pipeline.priced`). `test_resume_starts_pipeline_when_no_run` (seeded-style app: `started` → priced, still 1 party). **E2E slot 14** (real API + worker): `AC1 before: needs_attention ['Cannot price: missing Occupancy']` → `PUT … 200 flags [] resume {'requested': True, 'reason': 'started'}` → `/summary` status `priced`, quotes: 3 |
| AC2 Ben housing | ✅ backend | `test_collections.py::test_housing_history_flag` (20 months keeps the flag "Only 20 months…"; 24 clears it and resumes). E2E: 14 → 20 (flag kept, `blocking_flags_remain`) → 38 (flags `[]`, `started`) → `priced` |
| AC3 phone copy | ✅ backend | `test_fields_api.py::test_phone_copy_rule`, `test_phone_rule_via_party_patch` |
| AC4 import liabilities | ✅ backend | `test_credit.py::test_import_liabilities_keeps_manual` (imported row reset 999 → 410, manual row kept, primary DTI 0.2839 → 0.2250). E2E Tom Brandt: `[('Manual Card','55.00',True), ('Wells Fargo','410.00',False)]`, `dti_status not_applicable` (investment) |
| AC5 hard pull once | ✅ backend (UI state → 028b) | `test_credit.py::test_hard_pull_request_once` (201 pending, expires +14 d, 1 outbox row, link `/tasks/credit-check/{id}`, second → 409). `test_expired_request_allows_a_new_one`, `test_consent_fico_after_hard_pull` (E11). E2E: `201 pending`, `409 CONFLICT`, Mailpit to Tom: exactly 1 "Please authorize a credit check for your loan"; the plain-text part carries `http://localhost:3020/tasks/credit-check/<id>` |
| AC6 buy-box + TBD | ✅ backend (header/Playwright → 028b) | `test_property.py::test_buy_box_metros`, `test_property_tbd_toggle`; `reference/tests/test_metros.py`. E2E Kathleen: FL + Tampa, Orlando stored; address set → `tbd False, recommend_matches False`, county `Polk` |
| AC7 edit/revert/SSN events | ✅ backend (10 s re-mask → 028b) | `test_fields_api.py::test_edit_audit_events`, `test_ssn_reveal_writes_event`, `test_ssn_edit_event_is_masked`, `test_field_values_routes_write_events`. E2E: masked `***-**-1006`, reveal 200 with 9 digits, `Cache-Control: no-store` |
| AC8 DTI/income gating | ✅ backend (component test + react-doctor → 028b) | `test_sections_read.py::test_dti_primary_only`, `test_assets_employment_primary_only` |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed tests | `make test` | 540 passed (backend), 32 passed (seed); frontend packages green |
| Lint / types | `make lint` | ruff, ruff format, mypy (360 files), eslint, tsc and prettier all clean |
| New unit tests | `uv run pytest backend/app/features/applications/sections backend/app/features/reference backend/app/features/pricing/engine/tests/test_borrower_ratios.py` | 46 passed |
| E2E (slot 14) | real API :8114 + `make worker` (queue `cq-s14`) + Mailpit, curl-style script | all AC lines above |
| Frontend | n/a in 028a | — |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| High | SSN/DOB originals were stored in plain JSONB provenance | Fixed: `provenance.seal/unseal` (Fernet, same key as `EncryptedString`); `test_sensitive_original_is_encrypted_and_revert_restores` |
| Medium | A blank housing state or zip returned 500 (NOT NULL) | Fixed: required parsers → 422; `test_blank_housing_state_is_422` |
| Medium | Occupancy → primary cleared the strategy silently, and a revert lost it | Fixed: the strategy is cleared with provenance + event and restored on investment; `test_occupancy_strategy_coupling` |
| Medium | Strategy could be set on a primary loan | Fixed: 422 |
| Low | "Pricing resumed" was logged even if the Temporal call later failed | Fixed: `pipeline.resume_failed` event plus `resume.reason=temporal_unavailable`; `test_resume_failure_is_logged` |
| Test infra | A session-scoped second Temporal worker in the sections tests broke CQ-011's workflow tests in the same run | Fixed: a function-scoped env + real worker in `test_resume_pipeline.py` |

## How to test manually

1. `bash scripts/worktree-env.sh 14`, `make demo-reset`, then from the repo root `uv run uvicorn app.main:app --port 8114` and `make worker`.
2. Sign in as the manager. Then `PUT /api/v1/applications/<aisha>/fields/occupancy_type {"value":"investment"}` and poll `/summary` until the status is `priced`.
3. `POST …/<tom>/credit/hard-pull-request` twice gives 201, then 409. Mailpit shows one email.

## Follow-ups

- **028b:** the header TBD label needs `property.tbd` from the Property section (the summary has no TBD field; plan #19). Show the "All checks pass — pricing resumed" toast when `resume.requested` is true.
- **CQ-033:** write `representative_fico` with `source_ref="hard_pull"` after the pull (plan #12), and persist `expired` (the section already reports it).
- **CQ-017/CQ-030:** an address change does not re-enrich or mark quotes stale. That belongs to them.
- `PORTAL_BASE_URL` (default `http://localhost:3020`) is a new setting; set it per environment.
