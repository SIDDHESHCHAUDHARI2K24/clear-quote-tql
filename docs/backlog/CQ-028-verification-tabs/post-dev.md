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

## Review round 1 (PR #20 stage-6 findings)

| Severity | Finding | Resolution | Evidence |
| --- | --- | --- | --- |
| Major M1 | Concurrent edits created duplicate open flags; `MultipleResultsFound` then made every edit and the pipeline's verify return 500 | (a) `applications/locking.lock_application` (`SELECT … FOR UPDATE`) at the start of all 13 write routes; (b) the same lock in `run_and_persist` and again in the re-verify hook; (c) migration `a7c3e9d1b2f4` (off `620ac6b6be31`, one head) deletes duplicate open flags (keeping the oldest) and adds the partial unique index `uq_flags_open_application_field_rule`; (d) `orig:` insert is `ON CONFLICT DO NOTHING` | `test_concurrency.py::test_concurrent_edits_leave_one_open_flag`, `::test_concurrent_first_edits_write_one_orig_row` (real separate sessions; both failed before the fix: 2 open flags, then a 500 `UniqueViolation`) |
| Minor 1 | Revert re-ran the normalising parser | `Column.load` converts types only (ISO date, Decimal, enum) | `test_edit_rules.py::test_revert_restores_the_exact_original` (dashed SSN, padded surname, DOB), `::test_revert_restores_typed_values` |
| Minor 2 | Clearing the primary home phone was silently refilled by `phone_copy` | 422 with a field message while a cell phone exists (plan #24) | `::test_clearing_primary_home_phone_is_rejected`, `::test_clearing_home_phone_allowed_without_cell` |
| Minor 3 | "Auto-copied" was guessed by equality | `auto:borrower_home_phone` marker written when `phone_copy` fires; checked with no `orig:` row (plan #25) | AC3 tests kept; `::test_los_home_phone_equal_to_cell_does_not_follow`, `::test_reverted_home_phone_follows_the_cell_again` |
| Minor 4 | A resume signal that arrived mid-chain was lost | `_resume_requested` is cleared before each chain run, behind `workflow.patched("p56-resume-reset")` | `workflows/tests/test_resume_during_chain.py` (hangs with the old reset point, passes now) |
| Minor 5 | `/field-values` edits don't re-verify or resume | Follow-up for CQ-017 (plan.md), Kaneo comment on `lky9qv864ao119rajk7ujqd8` | — |
| Minor 6 | A failed run was a dead end | Failed/terminated/cancelled/timed-out runs are restarted with `ALLOW_DUPLICATE_FAILED_ONLY`; completed stays `workflow_closed` | `test_collections.py::test_resume_restarts_failed_run` |
| Minor 7 | The import guard wrote a misleading `pipeline.imported` | `ImportResult.skipped=True`, so the event carries `skipped: true` | `test_resume_pipeline.py::test_resume_starts_pipeline_when_no_run`; E2E Aisha event list |
| Minor 8 | Duplicate `pipeline.resume_requested` event and signal | Under the lock, skipped while the latest `pipeline.*` event is our pending resume (`reason="already_requested"`) | `test_collections.py::test_resume_is_not_repeated_while_pending`; E2E second edit |
| Nit | `require_any_session` skipped the user-exists check | Reuses `get_current_staff` / `get_current_borrower` | `reference/tests/test_metros.py::test_metros_rejects_session_of_deleted_user` |
| Nit | Borrower email in the `credit.hard_pull_requested` payload | Removed | `test_credit.py::test_hard_pull_request_once`; E2E payload |
| Nit | Private helpers imported from `verification.service` | Renamed public: `latest_scenario_snapshot`, `setting_int` | lint |
| Nit | Occupancy/strategy edge cases; metro ambiguity | Logged as follow-ups in plan.md | — |

**Self-review of this round (code-review skill), all fixed:**

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | The pending-resume check sorted on `at`, which comes from two clocks (`CLOCK_NOW` vs the worker's wall clock) | Now sorts on `created_at` (DB clock) |
| Medium | A pending resume never expired, so a run terminated before it handled the signal blocked every later resume | "Already requested" applies only while the run is still RUNNING; a closed run is restarted. The third step of `test_resume_is_not_repeated_while_pending` covers it |
| Medium | The pipeline's verify set `needs_attention` in a second transaction after the lock was released, so an LO fix landing in between left the application stuck | `run_and_persist(commit=False)` in `verify_application`: flags and status commit together under the lock |
| Low | `write_flag` callers outside the rules (the OB validator, the DSCR loop) could hit the new unique index | `write_flag` itself takes the application lock |
| Low | Existing auto-copied home phones had no `auto:` marker | The migration backfills markers with the old heuristic (home = cell, no `orig:` row); new rows get them from `phone_copy` |

Open (follow-up): the pricing Validate stage commits its OB flags, then sets `needs_attention` in `_fail_pricing_stage` in a separate transaction, so a narrow window of the same kind remains there (CQ-011/CQ-013 code).

Also in this round: merged `phase-p5-p6` twice (CQ-030's per-test worker and `db_lock`, then CQ-032). `real_temporal` now depends on `bind_activities_to_test_session`, holds `db_lock` for each API request and before the worker exits, and `db_lock` is re-exported from the sections conftest. `summary/tests/test_tab_states_flags` used two identical open flags, which the new index forbids, so it now uses two field keys.

**Verification (round 1):** `make lint` clean. `uv run pytest backend` 720 passed (after merging CQ-032), `seed` 32 passed, `pnpm -r run test` all green. Sections + workflow tests ran 3× in a row with no flakes (102 passed each time). E2E on slot 14 (`make demo-reset`, API :8114 and `make worker` on `cq-s14`):
- AC1: Aisha `needs_attention ['Cannot price: missing Occupancy']` → `PUT occupancy_type` 200, flags `[]`, resume `started`. A second edit gave `already_requested`. She reached `priced` with 3 quotes. Events: `…resume_requested, pipeline.imported (skipped=true), verified, enriched×3, priced`. No duplicate open flags in the DB.
- AC5: Tom `201 pending` → `409 CONFLICT`. Mailpit shows exactly one "Please authorize a credit check for your loan" email. The event payload has no email.

## How to test manually

1. `bash scripts/worktree-env.sh 14`, `make demo-reset`, then from the repo root `uv run uvicorn app.main:app --port 8114` and `make worker`.
2. Sign in as the manager. Then `PUT /api/v1/applications/<aisha>/fields/occupancy_type {"value":"investment"}` and poll `/summary` until the status is `priced`.
3. `POST …/<tom>/credit/hard-pull-request` twice gives 201, then 409. Mailpit shows one email.

## Follow-ups

- **028b:** the header TBD label needs `property.tbd` from the Property section (the summary has no TBD field; plan #19). Show the "All checks pass — pricing resumed" toast when `resume.requested` is true.
- **CQ-033:** write `representative_fico` with `source_ref="hard_pull"` after the pull (plan #12), and persist `expired` (the section already reports it).
- **CQ-017/CQ-030:** an address change does not re-enrich or mark quotes stale. That belongs to them.
- `PORTAL_BASE_URL` (default `http://localhost:3020`) is a new setting; set it per environment.

## CQ-028b — Verification tabs UI (this section)

### Summary (CQ-028b)

Built the five verification tabs (`apps/lo-console/src/app/(staff)/applications/[id]/{borrowers,housing,credit,assets,property}/page.tsx`) on top of 028a's API, plus a shared kit at `apps/lo-console/src/features/verification/shared/` (`useSection`, `FieldRow`, `FlagList`, `runSectionAction`, API wrappers, `formatFieldValue`/`formatDtiRatio`). Every field edit and revert goes through one pattern regardless of tab — `PUT`/`DELETE /fields/{field_key}` using the field's own `field_key` (plan.md decision #29: `fields.py`'s `resolve_field` parses application, party and row keys alike, so the row-collection endpoints are only needed to add a new row). Occupancy and investment strategy render on the **Property** tab, inside a "Loan" card, not Borrowers (decision #28: that's the only tab the section API actually returns them on). One sub-agent per tab (Borrowers, Housing, Credit, Assets); the coordinator built the shared kit, the Property tab, and the cross-tab gating test.

### Deviations from spec (028b)

| Spec said | Built | Why |
| --- | --- | --- |
| "...removes the TBD label in the header" (AC6) | The TBD label lives on the **Property tab** itself (`property-tbd-label` testid in `AddressOrTbdForm`), not CQ-016's global sticky header | The header's `ApplicationSummaryResponse` has no `address_status`/TBD field, and adding one is a backend change outside 028b's "no backend edits" scope (plan.md decision #30) |
| AC7 "SSN reveal re-masks after 10 s" listed under the Playwright test plan | Covered by a Vitest test with fake timers (`SsnField.test.tsx`) instead, per plan.md's own task table (T11: "AC7 re-mask with fake timers") | A real 10s wait in a Playwright spec is slow and flaky; the plan already designated a fake-timers unit test for this, and the coordinator's prompt and plan.md disagreed on which — plan.md (the item's own binding plan) wins |

### Acceptance evidence (stage 7, UI half)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 Aisha resolve → resume → toast → Priced; leaves "Needs your attention" | ✅ | `e2e/lo-console/aisha-occupancy-resume.spec.ts` (real API :8121 + `make worker` on slot 21): sets Occupancy on the Property tab's Loan card, toast "All checks pass — pricing resumed" shown, header reaches "Priced" within 60 s (real Temporal chain), then the dashboard's "Needs your attention" no longer lists her (CQ-025 AC5) |
| AC2 Ben housing ≥ 24 clears; shorter keeps with months | ✅ | `HousingTab.test.tsx`: 20-month fixture shows the shortfall and no "met" claim; 24+-month fixture shows the requirement met |
| AC3 phone copy rule | ✅ | Covered at the API level (028a); the UI surfaces the field/flag generically via `FieldRow` — no bespoke phone-copy UI needed |
| AC4 import liabilities keeps manual, DTI updates | ✅ | `CreditTab.test.tsx`: "Import liabilities" applies the returned section; DTI-as-percent assertions cover the primary-persona recompute |
| AC5 hard pull once; consent states | ✅ | `CreditTab.test.tsx`: success path applies `data.section`; 409 shows a message containing "already pending"; all four E11 consent-state texts (pending/accepted/declined/expired) render |
| AC6 buy-box metros; TBD → address turns recommend off, removes TBD label | ✅ | `e2e/lo-console/property-tab.spec.ts` (Kathleen McReynolds, real stack): two-tier picker (states → metros scoped to `GET /reference/metros?states=FL`), swaps Davenport for Tampa landing on [Tampa, Orlando]; entering an address removes the TBD label and unchecks Recommend matches; county shows "Polk" (zip lookup). `PropertyTab.test.tsx` (4 unit tests) covers the same logic against mocks |
| AC7 edit/revert/SSN events; 10 s re-mask | ✅ | `SsnField.test.tsx` (fake timers): reveal shows raw digits, `vi.advanceTimersByTime(10000)` re-masks. `FieldRow.test.tsx` covers the generic edit/revert/flag-highlight UI every tab reuses |
| AC8 DTI/income gating | ✅ | `VerificationTabs.gating.test.tsx` (coordinator-owned, cross-tab): primary shows DTI as a percent and employment/income; investment shows neither, reading straight off `dti_applicable`/`income_applicable` (never inferred client-side). `npx react-doctor -y --blocking error`: 0 errors, score 88/100 |

### Test log (stage 5, UI half)

| Check | Command | Result |
| --- | --- | --- |
| Frontend unit tests (whole `apps/lo-console`) | `npx vitest run` (from `apps/lo-console/`) | 154 passed (36 files), including 45 new verification-tab tests |
| Types | `npx tsc --noEmit -p .` (from `apps/lo-console/`) | clean, 0 errors |
| Lint | `pnpm -r run lint`, `pnpm -r run typecheck` | clean across all 4 workspace packages |
| Format | `pnpm exec prettier --check` (verification/, both e2e specs, this doc) | clean |
| react-doctor | `npx react-doctor -y --blocking error` (from `apps/lo-console/`) | 0 errors (exit 0); 2 pre-existing warnings in CQ-016 files this item doesn't own (`DefaultTabRedirect.tsx`, `WorkspaceProvider.tsx`); score 88/100 "Great" (started at 75/100 before this item's own fixes below) |
| E2E (slot 21) | `make demo-reset`; API `PYTHONPATH=backend uv run uvicorn app.main:app --port 8121` (note: `uv run --directory backend ...` from the worker guide broke `.env` discovery here — `Settings` failed 16 required-field validation errors; `PYTHONPATH=backend` from the repo root works, matching the guide's own alternative form); `make worker`; LO console + borrower portal (global-setup needs the portal for its own persona logins) on 3121/3221; `LO_BASE_URL=http://localhost:3121 PORTAL_BASE_URL=http://localhost:3221 npx playwright test e2e/lo-console/property-tab.spec.ts e2e/lo-console/aisha-occupancy-resume.spec.ts --project=lo-console` | both passed (2/2) |

### Review findings (stage 6, UI half)

A fresh subagent ran `code-review` (low effort) against the staged diff. Findings and resolutions:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `FieldRow`'s `draftToValue` did `Number(draft)` for `kind="number"` with no validation; a non-numeric entry (e.g. "abc") produces `NaN`, and `JSON.stringify(NaN)` serializes to `null` — an invalid entry would silently save as a field-clear instead of an error. Affects `dependents_count`, `residence_years`/`residence_months` | Fixed: throws `"Enter a number."` instead, caught by `FieldRow`'s existing error UI (editor stays open, no save). New test: `FieldRow.test.tsx` "rejects a non-numeric 'number' draft..." |
| Major | Same bug, concrete instance: `PropertyDetailsForm`'s `number_of_units` input did `Number(units)` unvalidated | Fixed: validates before calling `patchProperty`, shows "Units: enter a number." on failure instead of silently clearing the field |
| Minor | `fieldBySuffix` (row-field lookup by column suffix) was byte-for-byte duplicated in `AssetsTab.tsx`, `CreditTab.tsx` and `HousingTab.tsx` | Moved to `shared/api.ts`, exported from the shared kit; all three tabs now import it |
| Minor (noted, not fixed) | The per-record `onSave`/`onRevert` closure (`runSectionAction(() => putField(...))`, throw-on-error, `applyResult`) is near-identical across `AssetsTab`/`CreditTab`/`HousingTab`/`PropertyTab` and could be one shared hook | Left as-is: each tab's closure captures a different collection/kind, and factoring it out would be a larger refactor than this item's scope justifies; logged here as a real follow-up, not a correctness issue |

**Coordinator's own fixes on top of react-doctor** (beyond code-review's findings, all with tests still green after):
- 4 `react-doctor/no-array-index-as-key` warnings (Assets/Credit/Housing row lists): row records (`asset`/`employment`/`liability`/`housing_history` kinds) always carry a real UUID `id` per `service.py`'s `_row_record` — switched `key={record.id ?? \`asset-${index}\`}` to `key={record.id as string}` in all four spots.
- 1 `react-doctor/no-adjust-state-on-prop-change` in `SsnField.tsx` (re-masking when the field's value changes underneath a reveal): rewritten using React's own "adjust state during render" pattern (compare against a previous value in **state**, not a ref) instead of a `useEffect` keyed on `field.value`.
- That render-time rewrite's first version used a **ref** for the previous-value comparison, which react-doctor correctly flagged as `no-ref-current-in-render` (mutating `ref.current` during render is unsafe under concurrent rendering) — switched to `useState` instead, and dropped an unnecessary imperative `clearTimeout` call from the render path (the reveal timer is already cleared by the next `reveal()` call regardless).
- `react-doctor/no-high-complexity-react-function` in `FieldRow.tsx`: extracted the per-`kind` editor markup into a small `FieldRowEditor` sub-component (same JSX, no behavior change).
- Score went 75 → 80 (after array-key + adjust-state-on-prop-change fixes) → 88 (after the ref-in-render + complexity fixes), 0 errors throughout after the last two fixes.

**A real production bug found while writing the AC1 E2E spec (not from code-review or react-doctor):** the first `aisha-occupancy-resume.spec.ts` run showed the header stuck on "Needs attention" for 60 s even though the DB had her `priced` within ~6 seconds of the edit. Root cause: `WorkspaceProvider` (CQ-016) only keeps polling `.../summary` while `last_pipeline_stage` is non-null; a freshly-**started** run (Aisha's seeded application has no prior Temporal run, plan.md #9) reports `last_pipeline_stage: null` until its first activity commits, a few hundred ms to ~1s later. `useSection`'s `applyResult` called `refetchWorkspace()` exactly once, immediately after the edit — almost always before that first activity commits — saw `null`, and `WorkspaceProvider` correctly (by its own contract) treated `null` as terminal and never started polling. The header would then stay wrong until a manual reload, for every LO fix that starts a fresh pipeline run, not just in the test. Fixed in `useSection.ts`: when `resume.requested` is true, schedule three additional delayed `refetchWorkspace()` calls (1.5 s, 4 s, 8 s) to bridge the race until `WorkspaceProvider`'s own 3 s interval takes over once it observes a non-null stage. New fake-timers test in `useSection.test.tsx` locks in the bridge's timing and cleanup-on-unmount.

### How to test manually (028b, slot 21)

1. `bash scripts/worktree-env.sh 21`, `make demo-reset`.
2. From the repo root: `PYTHONPATH=backend uv run uvicorn app.main:app --port 8121`, `make worker`, `pnpm --filter @cq/lo-console exec next dev -p 3121`, `pnpm --filter @cq/borrower-portal exec next dev -p 3221`.
3. Sign in as `jordan.lee@clearquote-demo.test` (Aisha's LO). Open her application's Property tab, edit Occupancy to "Investment", Save — the toast appears and the header reaches "Priced" within about a minute.
4. Sign in as `morgan.reyes@clearquote-demo.test` (Kathleen's LO). Open her Property tab: swap the buy-box metros, then enter a specific address and confirm the TBD label disappears and Recommend matches turns off.
