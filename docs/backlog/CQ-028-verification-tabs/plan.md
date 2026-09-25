# CQ-028 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

CQ-028 ships as two units under one Kaneo task (`syqp3227euvn3i5wmyhj6p3e`), per `docs/backlog/phase-p5-p6-plan.md`:

- **CQ-028a — Verification API** (wave 2, branch `cq-028-verification-api`, slot 14): every backend piece below, T1–T9.
- **CQ-028b — Verification tabs UI** (wave 3, branch `cq-028-verification-tabs`, slot 21): the five tab pages on top of the 028a API, T10–T16.

028a writes the backend evidence in `post-dev.md`; 028b appends the UI evidence.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Paths | Routes live under `/api/v1` (spec `/api/...` → `/api/v1/...`). |
| 2 | Decision | Field edits for 1003 fields | The spec's `PUT` / `DELETE /api/applications/{id}/fields/{field_key}` is built as-is, in `sections/`. The existing `PATCH/POST …/field-values/{field_key}[/revert]` routes only accept the five pricing keys (Decimal), so they cannot set occupancy, a phone number or a DOB. `/fields` rejects those five keys with 422 and points at `/field-values`. The `/field-values` routes get activity events through a hook (#6). |
| 3 | Decision | Where the original value lives (no migration) | Domain tables stay the source of truth: the rules read them and so does everything else. The first LO edit of a 1003 field writes a provenance row in `field_values` under the key `orig:{field_key}`: `value` holds the **original** value, `source=lo_override`, `source_ref` holds the original source, and `overridden_by`/`overridden_at` are set. Later edits keep that original. Revert writes the original back to the domain column and deletes the row. LO-added rows get the marker `row:{collection}:{row_id}` (`source=lo_entry`). Both prefixes contain `:`, so they cannot collide with catalog keys; the pricing readers look up exact keys only. A migration was rejected because this wave has 8 parallel PRs and extra alembic heads would be likely. |
| 4 | Decision | Field keys | Party fields use role-prefixed catalog keys (`borrower_cell_phone`, `co_borrower_ssn`, …), so they match `flags.field_key` (`borrower_ssn`, `borrower_dob`). Application fields are `occupancy_type` and `investment_strategy`, matching Aisha's flag key `occupancy_type`. Row fields are `{collection}.{row_id}.{column}`, for example `housing_history.<uuid>.residence_months`. |
| 5 | Decision | Phone rule (AC3) | The home phone counts as **auto-copied** when it equals the old cell phone **and** no `orig:{role}_home_phone` provenance row exists (that row means the LO entered the home phone by hand). An edit to the cell phone then also moves the home phone and writes a system `field.auto_updated` event. A manually entered home phone is left alone. The existing `phone_copy` rule is the only writer of home = cell (at import, when the LOS home phone is empty). Treating an LOS home phone that happens to equal the cell phone as auto-copied is harmless. The section reports `source=formula` for an auto-copied home phone. |
| 6 | Decision | Events for `/field-values` (minimal diff in `enrichment/`) | `enrichment/router.py` (not `service.py`) calls `sections.events.record_field_event(...)` after `override_field_value` / `revert_field_value`. This adds 2 call sites and 1 import to the router, and `service.py` is left untouched. That keeps the diff apart from CQ-017's edits to `enrichment/service.py`. |
| 7 | Decision | Activity event types | `field.edited`, `field.reverted`, `field.auto_updated`, `row.added`, `row.edited`, `flag.raised`, `flag.resolved`, `ssn.revealed`, `credit.liabilities_imported`, `credit.hard_pull_requested`, `property.updated`, `document.received`, `pipeline.resume_requested`. Every payload carries `field_key` (or `collection`/`row_id`) plus a human-readable `message` for CQ-029's timeline. The actor is the staff user id, or `system` for derived changes. |
| 8 | Decision | Re-verify and resume hook | After every edit, `sections.reverify.reverify_and_maybe_resume(app_id, db, actor)` does the following. (1) Runs `verification.service.run_and_persist`. (2) If open `ob_required_field` flags exist (Aisha's flag is raised by the pricing Validate stage, not by the rules), it re-runs `validate_ob_required_fields`, which resolves them or keeps them; an `AppError` is swallowed because the flags stay as they are. (3) Writes one `flag.raised`/`flag.resolved` event per changed flag. (4) If the status is `needs_attention` and no open `blocking` flags remain (`FlagSeverity` has no `error` member, so blocking is the gate), it signals `resume`. The response carries `resume: {requested, reason}`, which the UI uses for the "All checks pass — pricing resumed" toast. |
| 9 | Decision | Resume when no workflow is running (seeded apps) | `make demo-reset` drives personas through the service functions, so seeded Aisha and Ben have **no** Temporal run and a `resume` signal gets NOT_FOUND. On NOT_FOUND the hook **starts** the pipeline (same id, `REJECT_DUPLICATE`). To make that safe, `import_from_los` gets a small guard: if the application already has parties it returns without writing anything, so it does not duplicate rows and does not overwrite the LO's occupancy fix with the LOS null. This touches one file outside the owned paths (`applications/service.py`); it is a small necessity for AC1 in the demo. If a closed run already holds the id, the hook reports `resume.requested=false, reason="workflow_closed"`. A Temporal outage is logged and reported as `reason="temporal_unavailable"`; the edit itself still succeeds. |
| 10 | Decision | DTI and reserves math | Money ratios go in a new engine module, `pricing/engine/borrower_ratios.py` (Decimal): `debt_to_income_ratio` (4 dp), `reserves_required_amount` and `asset_sufficiency`. It is a new file rather than an edit to `quote_engine.py`, to avoid an EOF conflict with the P3 lane. The pinned rule text lives in `verification/rules.py`. DTI = (liabilities + total monthly payment of the latest priced quote) / monthly income, the same formula as `dti_primary`. DTI is `null` with `dti_status="awaiting_pricing"` until a quote exists, and `"not_applicable"` for investment loans (AC8). |
| 11 | Decision | FICO bracket | 20-point brackets, `"<620"`, `"620–639"` … `"760–779"`, `"780+"` (catalog §3 examples `"780+"` and `"700–719"`). |
| 12 | Decision | Pull type and date | `representative_fico` in `field_values`: `pulled_at = updated_at`; the pull type is `hard_pull` when `source_ref == "hard_pull"` (or a `credit_pull_type` field value says `Hard_Pull`), otherwise `soft_pull`. **Contract for CQ-033:** when the hard pull lands, write `representative_fico` with `source_ref="hard_pull"`. |
| 13 | Decision | Consent summary (E11) | The Credit section's `consent` is the latest `hard_pull` consent row: `id, status, requested_at, requested_by, expires_at, decided_at, decline_reason, fico_after_pull`. `fico_after_pull` is `representative_fico` when the status is `accepted` and the pull type is hard. A `pending` row past `expires_at` is **reported** as `expired`; CQ-033 owns persisting that. |
| 14 | Decision | Hard-pull request 409 (AC5) | A second request returns 409 while a pending, unexpired request exists. The email goes to `clients.email` (the borrower-portal account email) with a link to `{PORTAL_BASE_URL}/tasks/credit-check/{consent_id}`. New setting `portal_base_url` (`PORTAL_BASE_URL`, default `http://localhost:3020`), a one-line addition to `core/config.py` and `.env.example`. `expires_at = clock.now() + 14 d`. |
| 15 | Decision | Import liabilities (AC4) | Portal applications have no `los_loan_guid`, so the endpoint returns 422 for them. Otherwise it deletes every liability **without** a `row:liabilities:*` marker, plus that row's `orig:` provenance rows, inserts the LOS liabilities, re-verifies, and returns the Credit section with the recomputed DTI. |
| 16 | Decision | County from zip | No zip→county adapter exists. The "mock lookup" is the distinct `provider_listings (zip → county)`. If the zip is not found, it falls back to the county in the request, and otherwise `null`. |
| 17 | Decision | Metros list and AC6 "Orlando" | `GET /api/v1/reference/metros?states=FL,NC` returns the distinct `provider_listings.metro` per state **merged with** a small static catalog of major metros per state (`reference/catalog.py`). The seed has no Orlando listing, yet the AC picks "Tampa and Orlando". Buy-box metros are validated against this list for the chosen states (422 otherwise). When the states change, metros from removed states are dropped. Staff **or** borrower sessions may call it; CQ-032b's wizard uses the same picker. |
| 18 | Decision | Property update | `PATCH /api/v1/applications/{id}/property` takes `address` \| `tbd` \| `recommend_matches` \| `buy_box_states` \| `buy_box_metros` \| `property_type` \| `number_of_units`. Setting an address sets `specific_address`, fills the county, sets `applications.subject_state`, and turns `recommend_matches` off. `tbd=true` clears the street, keeps city/state/zip and turns `recommend_matches` on. An explicit `recommend_matches` in the same body wins. Re-enrichment and stale marking after an address change are CQ-017/CQ-030's job. |
| 19 | Decision | Header TBD label (AC6) | The CQ-016 summary has no TBD field. 028b reads `property.tbd` from the Property section and refreshes the header after save. Adding `address_status` to the summary is left for 028b if needed (CQ-016's file). |
| 20 | Decision | SSN | Always masked in sections (`***-**-1234`). `POST …/parties/{party_id}/ssn-reveal` returns it once (`Cache-Control: no-store`) and writes `ssn.revealed`. The UI re-masks after 10 s (028b). |
| 21 | Decision | Source for imported fields | Fields from an `los` application report `encompass`; fields from a `portal` application report `default` (FieldSource has no borrower member). LO-added rows report `lo_entry`; overridden fields report `lo_override`. |
| 22 | Decision | Scope | Every route depends on `get_scoped_application` (404 out of scope, E16). |
| 23 | Decision | Documents | `PATCH …/documents/{id}` with `{received: bool}` sets or clears `received_at` (`clock.now()`), 404 if the document belongs to another application. The Assets section lists every document as the checklist. |
| 24 | Decision (review round 1, minor 2) | Clearing the primary home phone | `PUT /fields/borrower_home_phone` with an empty value returns **422** ("Home phone: cannot be empty while a cell phone is on file") while the primary borrower has a cell phone. `phone_copy` would refill it on the next verify and leave a stale `orig:` row, so the edit is refused rather than silently undone. Co-borrowers and a borrower with no cell phone can still clear it. |
| 25 | Decision (review round 1, minor 3) | Auto-copied home phone marker | Supersedes the equality test in #5. `run_and_persist` writes `field_values` key `auto:borrower_home_phone` (idempotent, `source=formula`) when `phone_copy` fires; import never copies phones. The home phone follows the cell phone only when that marker exists **and** no `orig:borrower_home_phone` row exists. An LOS home phone that equals the cell phone stays put. |
| 26 | Decision (review round 1, M1) | Concurrency | Every write route in `sections/router.py` and `verification.service.run_and_persist` take `applications.locking.lock_application` (`SELECT … FOR UPDATE` on the application row), as do `write_flag` and the re-verify hook (again after the rules commit). The pipeline's verify commits its flags and status in one transaction (`run_and_persist(commit=False)`). Migration `a7c3e9d1b2f4` (off `620ac6b6be31`) removes duplicate open flags (keeping the oldest) and adds the partial unique index `uq_flags_open_application_field_rule`. `orig:` inserts use `ON CONFLICT DO NOTHING`. |
| 27 | Decision (review round 1, minors 4, 6–8) | Resume mechanics | The workflow clears `_resume_requested` before each chain run (patch `p56-resume-reset`), so a signal received mid-chain is kept. The hook restarts a failed, terminated, cancelled or timed-out run (`ALLOW_DUPLICATE_FAILED_ONLY`); a completed run stays `workflow_closed`. While the latest `pipeline.*` event (by `created_at`) is our own `pipeline.resume_requested` and the run is still RUNNING, another edit returns `resume.reason="already_requested"` with no new signal or event. The import-once guard writes `pipeline.imported` with `skipped: true`. |

## Follow-ups (review round 1)

- **CQ-017:** the `/field-values` pricing edits (override/revert) write events but do not re-verify or resume the pipeline. They should call `sections.reverify.reverify_and_maybe_resume` like `/fields` does. Posted on the CQ-017 Kaneo task.
- **Occupancy/strategy coupling (review nit):** the coupling in `fields._couple_strategy` only covers primary ↔ investment. Edge cases (for example reverting occupancy to a null original, or a strategy cleared by the coupling whose `orig:` row stays until occupancy is investment again) are not specified. Settle the rules when 028b shows the pair.
- **Pricing-stage status window (CQ-011/CQ-013):** `validate_ob_required_fields` commits its flags, then `_fail_pricing_stage` sets `needs_attention` in a second transaction. An LO fix landing in between resolves the flag but sees a non-`needs_attention` status, so it does not resume. Fix it the way `verify_application` now works: one transaction under `lock_application`.
- **Metro ambiguity (review nit):** buy-box metros are stored as bare names (`"Portland"`), so a name shared by two chosen states (OR/ME) is ambiguous. Store `{state, metro}` pairs when CQ-032b or the matches engine needs the state.

## Why

Tabs 1–5 must show what the pipeline imported and checked, with flags inline, and every LO fix must re-run the rules and restart the pipeline automatically (spec Goal; system-design "Automation-first input model").

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Sections API (028a) | create `backend/app/features/applications/sections/{__init__,router,schemas,service,fields,provenance,events,reverify,collections,credit,property,documents,masking}.py` + `tests/` |
| Engine math (028a) | create `backend/app/features/pricing/engine/borrower_ratios.py` + `tests/test_borrower_ratios.py` |
| Reference (028a) | create `backend/app/features/reference/{__init__,router,service,catalog,schemas}.py` + `tests/` |
| Event hook (028a) | modify `backend/app/features/pricing/enrichment/router.py` (2 calls + import) |
| Import guard (028a) | modify `backend/app/features/applications/service.py` (early return when already imported; Decision #9) |
| Settings (028a) | modify `backend/app/core/config.py`, `.env.example` (`PORTAL_BASE_URL`) |
| Registry (028a) | modify `backend/app/core/registry.py` (+2 lines) |
| API client (028a) | regenerate `packages/api-client` |
| Tabs UI (028b) | `apps/lo-console/app/(staff)/applications/[id]/{borrowers,housing,credit,assets,property}/**`, `apps/lo-console/src/features/verification/**` |

## Tasks

| Task | Unit | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- | --- |
| T1 | 028a | Provenance, masking, events and field registry | — | `sections/{provenance,masking,events,fields}.py` | `test_fields.py` |
| T2 | 028a | Engine ratios | — | `engine/borrower_ratios.py` | `test_borrower_ratios.py` |
| T3 | 028a | Section read for all 5 tabs | T1, T2 | `sections/{schemas,service}.py`, `router.py` | `test_sections_read.py` (masked SSN, flags, totals, DTI gating, consent) |
| T4 | 028a | Re-verify and resume hook, `import_from_los` guard | T1 | `sections/reverify.py`, `applications/service.py` | `test_reverify.py`, `test_resolve_flag_resumes_pipeline` |
| T5 | 028a | `PUT/DELETE /fields`, SSN reveal, `/field-values` event hook | T3, T4 | `sections/router.py`, `enrichment/router.py` | `test_edit_audit_events`, `test_phone_copy_rule` |
| T6 | 028a | Collections: housing, parties, liabilities | T4 | `sections/collections.py` | `test_housing_history_flag`, `test_add_co_borrower` |
| T7 | 028a | Credit actions | T4 | `sections/credit.py`, `core/config.py` | `test_import_liabilities_keeps_manual`, `test_hard_pull_request_once` |
| T8 | 028a | Property actions, reference metros, documents | T4 | `sections/{property,documents}.py`, `features/reference/**` | `test_buy_box_metros`, `test_property_tbd_toggle`, `test_documents` |
| T9 | 028a | Registry, api-client, E2E curl | T3–T8 | `registry.py`, `packages/api-client` | E2E log in post-dev.md |
| T10 | 028b | Shared tab kit: `useSection(tab)`, `FieldRow` (value, SourceBadge, inline flag, edit and revert), `FlagList`, refresh of the tab rail badge after save, "pricing resumed" toast | 028a | `src/features/verification/shared/**` | `FieldRow.test.tsx`, `useSection.test.ts` |
| T11 | 028b | Borrowers tab: cards, SSN reveal with 10 s re-mask, add co-borrower | T10 | `…/borrowers/**` | `BorrowersTab.test.tsx` (AC7 re-mask with fake timers) |
| T12 | 028b | Housing tab: rows, total months vs 24, add prior address | T10 | `…/housing/**` | `HousingTab.test.tsx` (AC2) |
| T13 | 028b | Credit tab: FICO and bracket, liabilities, DTI (primary only), import, hard pull, three consent states | T10 | `…/credit/**` | `CreditTab.test.tsx` (AC4/AC5 states) |
| T14 | 028b | Assets tab: assets, reserves, sufficiency, employment and income (primary only), document checklist | T10 | `…/assets/**` | `VerificationTabs.gating.test.tsx` (AC8) |
| T15 | 028b | Property tab: address or TBD, toggle, two-tier buy-box picker | T10 | `…/property/**` | `e2e/property-tab.spec.ts` (AC6) |
| T16 | 028b | react-doctor, Playwright, UI evidence in post-dev.md | T11–T15 | docs | react-doctor log |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 (028a) | T1, T2 | Contracts first: provenance keys, event types, math |
| 2 (028a) | T3, T4 | Read model and the hook every edit uses |
| 3 (028a) | T5, T6, T7, T8 | Separate files; each calls T4 |
| 4 (028a) | T9 | api-client after every route exists |
| 5 (028b) | T10 | Shared kit before the tabs |
| 6 (028b) | T11–T15 | One folder per tab, no shared files |
| 7 (028b) | T16 | Verification |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 Aisha resolve → resume → Priced | `sections/tests/test_resume_pipeline.py::test_resolve_flag_resumes_pipeline` (Temporal time-skipping, real worker, API `PUT /fields/occupancy_type`); `test_resume_starts_pipeline_when_no_run` (seeded-style app); E2E curl on slot 14 |
| AC2 Ben housing ≥ 24 clears; shorter keeps with months | `test_collections.py::test_housing_history_flag` |
| AC3 phone copy rule | `test_fields_api.py::test_phone_copy_rule` |
| AC4 import liabilities keeps manual, DTI updates | `test_credit.py::test_import_liabilities_keeps_manual` |
| AC5 one pending consent, one email, 409 | `test_credit.py::test_hard_pull_request_once`; Mailpit check in E2E; UI state in 028b `CreditTab.test.tsx` |
| AC6 buy-box metros; TBD → address turns recommend off | `test_property.py::test_buy_box_metros`, `test_property_tbd_toggle`; `reference/tests/test_metros.py`; 028b `e2e/property-tab.spec.ts` |
| AC7 edit and revert events; SSN reveal event | `test_fields_api.py::test_edit_audit_events`, `test_ssn_reveal_writes_event`; `enrichment/tests/test_field_value_events.py`; 028b re-mask test |
| AC8 primary shows employment, income, DTI; investment no DTI | `test_sections_read.py::test_dti_primary_only`, `test_assets_employment_primary_only`; 028b `VerificationTabs.gating.test.tsx` + react-doctor |

## Progress

- [x] T1 provenance, masking, events, fields
- [x] T2 engine ratios
- [x] T3 section read
- [x] T4 re-verify and resume, import guard
- [x] T5 field edits, SSN reveal, field-values hook
- [x] T6 collections
- [x] T7 credit actions
- [x] T8 property, metros, documents
- [x] T9 registry, api-client, E2E
- [ ] T10–T16 (028b)
