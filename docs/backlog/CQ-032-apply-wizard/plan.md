# CQ-032 — Implementation plan

CQ-032 is split into two units (phase-p5-p6-plan.md, wave table):

- **CQ-032a Apply API** (wave 2, branch `cq-032-apply-api`, slot 18): every backend AC. This plan was written by 032a.
- **CQ-032b Apply wizard UI** (wave 3, branch `cq-032-apply-wizard`, slot 22): the four-tab wizard at `/apply`, built on the contract in "Per-tab data contract" below.

## Decisions & questions (stage 1)

Plan-level decisions that apply: E1 (drafts table, consent columns, `applications.source`), E2 (`core/clock.now()`), E3 (`core/storage`), E14 (portal source skips import; deterministic mock credit for wizard applicants), E15 (`least_loaded_lo_id`), E16 (404 for out-of-scope).

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Routes | Decided: `POST /api/v1/portal/applications` (create or return the open draft, always 200), `GET /api/v1/portal/applications/{draft_id}`, `PATCH /api/v1/portal/applications/{draft_id}/draft`, `POST /api/v1/portal/applications/{draft_id}/submit`, `POST /api/v1/portal/applications/{draft_id}/documents` (multipart), `DELETE /api/v1/portal/applications/{draft_id}/documents/{document_id}`. `{id}` is always the **draft** id: before submit there is no application. The DELETE is an addition so the wizard can remove a wrong upload. |
| 2 | Decision | Borrower isolation | Decided: every `{draft_id}` route loads the draft with `borrower_account_id = signed-in account`; anything else (another borrower's draft, unknown id) is 404 (E16 style). |
| 3 | Decision | Autosave semantics | Decided: `PATCH` replaces that tab's data wholesale (the UI always sends the full tab), runs that tab's validation and returns `field_errors` plus `tab_valid`. It never rejects the save for a validation failure (only for a malformed body: unknown tab, non-object data, >64 KB). `income.documents` is server-managed: whatever the client sends there is ignored and the stored list kept. `email` in tab 1 is also ignored (read-only, always the account email). |
| 4 | Decision | Resume (AC3) | Decided: after every save the server recomputes `current_tab` = the first tab (in order `you`, `property`, `income`, `consent`) that does not validate; when all four validate it is `consent`. `tabs.<tab>.complete` says which tabs pass. The UI opens at `current_tab`. |
| 5 | Decision | Validation home | Decided: pydantic models per tab in `portal/apply/validation.py` (one module shared by autosave and submit). Cross-tab rules take a context: tab 3's income rule reads tab 2's occupancy; tab 4's name rule reads tab 1's name; tab 2's metro rule reads the known metro list (`provider_listings` distinct `metro`/`state`). Pydantic messages are rewritten to plain text (`"This field is required."` etc.). |
| 6 | Decision | "Income required for primary" | Decided: for `occupancy = primary`, `employer_name`, `years_employed`, `monthly_income` (> 0) and `monthly_debts` (≥ 0) are required. For LTR/STR they are optional and ignored at submit. `liquid_assets` (≥ 0) is required for everyone. |
| 7 | Decision | Prior address rule | Decided: `prior_address` is required when `residence_years * 12 + residence_months < 24` (AC2: 14 months → required). The spec asks only for presence; the pipeline's own `housing_history_24mo` rule still flags a short combined history for the LO. |
| 8 | Decision | Age rule | Decided: DOB must give age ≥ 18 on `core/clock.now()` and ≤ 120 (the upper bound only catches typos). Applies to the co-borrower too. |
| 9 | Decision | Occupancy → model | Decided: tab 2 `occupancy` is `primary` / `ltr` / `str` (the three UI choices). Submit maps them to `applications.occupancy` (`primary` / `investment`) and `applications.strategy` (`None` / `ltr` / `str`), the same columns `import_from_los` and the seed write. |
| 10 | Decision | Down payment preference | Decided: allowed values per catalog §5: primary `0.03, 0.05, 0.10, 0.15, 0.20`; LTR/STR `0.15, 0.20, 0.25`. Stored at submit as `field_values.down_payment_pct` (source `lo_entry`, `source_ref = "borrower_portal"`; no `FieldSource` value exists for borrower-entered data and adding one would touch the shared `SourceBadge` map). `auto_price` keeps pricing the system-design default set (20% / 25%) exactly as it does for an LOS import, so AC1's "default quotes" hold; the LO reprices at the borrower's preference in the Quote Builder (CQ-018). Logged as a follow-up. |
| 11 | Decision | Property location for pricing | Decided: enrichment needs `state`, `county` and `zip` (tax by state+county, rent/STR by zip). With an address, the borrower gives street/city/state/zip; `county` is looked up from `provider_listings` by zip, else the only `provider_tax_rates` county for that state. TBD: `address_status = tbd`, `buy_box_states`/`buy_box_metros` from tab 2, `recommend_matches = true`, and `city/state/zip/county` resolved from the first metro's first `provider_listings` row (the seed does the same for TBD personas: the market's representative zip). `property_type = single_family`, `number_of_units = 1` (the wizard does not ask). `applications.subject_state` is the property state. |
| 12 | Decision | Soft pull at submit (E14) | Decided: the LOS import pulls soft credit; the wizard applicant has no LOS loan number and no seeded report. `MockCreditClient.pull_credit` gains a deterministic fallback for keys from `portal_credit_key(application_id)` (`PORTAL-<12 hex>`): when no seeded row exists, it synthesizes a report from a SHA-256 of the key (scores 680–799; soft pull fills Experian only, hard pull fills all three plus `middle_score`), still logging the integration call. Submit calls it with `SOFT_PULL` and writes `field_values.representative_fico` (source `credit_bureau`), exactly like `import_from_los`. CQ-033 reuses the same key for the hard pull. Small necessity outside owned files (`integrations/credit/mock.py`), logged. |
| 13 | Decision | Pipeline changes | Decided: none needed. The foundation already skips import for `source = portal`; with decisions 11 and 12, verify → enrich → validate → price → draft run on the locally written rows. Proven by `test_submitted_tampa_str_reaches_priced` (Temporal time-skipping) and the slot-18 E2E with a real worker. |
| 14 | Decision | Parties, housing, employment, assets | Decided: mirror `import_from_los`: `application_parties` (borrower; co-borrower when added; `ssn_encrypted` via `EncryptedString`, `email` = account email for the borrower, `no_co_applicant_check = not has_co_borrower`), `housing_history` (sequence 0 current, 1 prior), one `employment` row (primary, or any occupancy when an employer was given), one `liabilities` row for the self-reported monthly debts when > 0 (`creditor_name = "Self-reported debts"`, `account_type = "self_reported"`, balance 0), one `assets` row (`account_type = "liquid"`, `institution = "Borrower reported"`) for liquid assets. |
| 15 | Decision | Source badge "Borrower portal" | Decided: the badge is `applications.source = portal` (foundation enum); list/workspace UIs label it "Borrower portal". Parties/housing rows have no per-row source column, so nothing else is needed. |
| 16 | Decision | LO assignment (AC5) | Decided: `applications.lo_id = least_loaded_lo_id(db)` (fewest active applications, ties alphabetical). If the borrower's client has no other active application, `clients.assigned_lo_id` moves to the same LO so the LO sees the client too. Events: `application.submitted` (actor `borrower`) and `application.assigned` (actor `system`, payload `lo_id`, `lo_name`, `rule = "least_loaded"`). No LO at all → 409 "No loan officer is available". |
| 17 | Decision | Workflow start | Decided: same call as `applications/router.py` (`application-{id}`, `REJECT_DUPLICATE`, `APPLICATION_PIPELINE_TASK_QUEUE`) via the `get_temporal_client` dependency, **after** the application commit. If Temporal is unreachable the submit still succeeds (the application exists in Intake, the error is logged and `pipeline_started = false` is returned); the LO can re-trigger with `POST .../pipeline/start`. |
| 18 | Decision | Consent row (AC6) | Decided: one `consents` row per submit, new `ConsentType.APPLICATION = "application"` (migration off `3b55187d53d7`, `ALTER TYPE consent_type ADD VALUE`), `status = accepted`, `text_version = "apply-v1"`, `text_hash = sha256(consent text)`, `typed_name`, `ip` from `auth.common.client_ip` (the socket peer, the same helper the login rate limits use; trusting `X-Forwarded-For` behind the Railway proxy lands there once, CQ-035, rather than as an unverified header here), `user_agent`, `at = decided_at = requested_at = now()`. The consent text is served in the draft response (`consent.text`, `consent.version`) so the UI shows exactly what is hashed. |
| 19 | Decision | Uploads before submit | Decided: uploads are keyed by the draft: stored at `drafts/{draft_id}/documents/{uuid}{ext}` and listed in `data.income.documents`. At submit each object is copied to `applications/{application_id}/documents/{uuid}{ext}` (spec path), a `documents` row is created (`doc_type` `pay_stub`/`w2`/`bank_statement`, `received_at = now`) and the draft copy is deleted. After submit, uploads return 409 (editing after submit is out of scope). |
| 20 | Decision | Upload limits (AC7) | Decided: extension `.pdf/.jpg/.jpeg/.png` **and** matching magic bytes (`%PDF`, `\xFF\xD8\xFF`, `\x89PNG`) else 415 `"Only PDF, JPG and PNG files are accepted."`; more than 10 MB (10 × 1024 × 1024 bytes) → 413 `"Files must be 10 MB or smaller."`; empty → 422. At most 20 documents per draft. |
| 21 | Decision | LO email (AC5) | Decided: subject `New application from {First Last}`, a short table-based body (borrower, occupancy/strategy, price, location) via `send_email(..., application_id=...)`, sent **after** the application commits (SMTP sends immediately, so a rolled-back submit must not email anyone); its outbox row commits right after. |
| 22 | Decision | Submit idempotency | Decided: submit on an already-submitted draft returns 409 with the existing `application_id` in `details`. Submit with invalid tabs returns 422 with `details.field_errors` per tab and `details.first_invalid_tab`. |
| 23 | Decision | New dependency | Decided: `python-multipart` added to `pyproject.toml`/`uv.lock` (FastAPI needs it for `UploadFile`/`Form`; nothing in the backend took multipart before). Small necessity, logged. |
| 24 | Decision | Schema test | Decided: `backend/tests/test_schema.py`'s pinned `ConsentType` value set gains `application` (one-line necessity outside owned files). |
| 25 | Decision | SSN in drafts (review round 1, major 1) | Decided: the plain SSN never reaches `application_drafts.data`. On a tab-1 PATCH the server moves `ssn` (and `co_borrower.ssn`) into a Fernet token (`core/encryption.encrypt_str`, the same key as `EncryptedString`) stored as `ssn_encrypted` inside the JSON, plus `ssn_last4`. No migration: the ciphertext lives in the JSON. Responses never carry `ssn` or `ssn_encrypted`: each person block returns `ssn_last4` and `ssn_set: true`. A PATCH that omits `ssn` (or sends it blank) keeps the stored one; a malformed `ssn` is not stored, clears the stored one and reports `"SSN must be 9 digits."`. Client-sent `ssn_encrypted` / `ssn_last4` / `ssn_set` are ignored. Submit decrypts into `application_parties.ssn_encrypted` (`EncryptedString`), then scrubs `ssn_encrypted` from the closed draft (`ssn_last4` stays). `core/encryption.py` gained `encrypt_str`/`decrypt_str` (small necessity outside owned files). |
| 26 | Decision | Upload body bounds (review round 1, major 2 + minor 4) | Decided: `portal/apply/upload_guard.py` `UploadBodyLimitMiddleware` (pure ASGI, registered in `main.py` inside CORS) runs before routing, auth and parsing on `POST /api/v1/portal/applications/{id}/documents`: no `Content-Length` → 411 `LENGTH_REQUIRED`; `Content-Length` > 10 MB + 64 KB multipart overhead → 413 `FILE_TOO_LARGE`; a byte counter cuts off a body that runs past its declared length → 413. The route parses the multipart body by hand (`request.form(max_files=1)`), only after auth, draft ownership, the open-draft check and the 20-document cap pass. Two files, or a malformed body → 422 `"Upload one file at a time."`. The OpenAPI request body is unchanged (declared via `openapi_extra`). |
| 27 | Decision | Several applications per borrower (review round 1, minor 6) | Decided: a borrower may submit several portal applications (they may buy several properties); after a submit, `POST /portal/applications` opens a new draft. At most one submit per borrower per 10 minutes (`auth/otp/rate_limit.hit`, key `rl:borrower:apply_submit:{account_id}`) → 429 `RATE_LIMITED`. The limit is checked after validation, but the counter ticks only once the application commits, so a 422, a 409 "no LO available" or a storage failure never locks the borrower out (one open draft per borrower plus the draft row lock keep two submits from racing past the check). |
| 28 | Decision | Borrower metros list (review round 1, major 3) | Decided: `GET /api/v1/portal/applications/metros` (borrower session) returns `{states: [{state, metros: [...]}]}`, both sorted, from `service.known_metros` (distinct `provider_listings` state/metro): exactly the list the `buy_box_metros` rule accepts. Independent of CQ-028a's staff-side `/reference/metros`. |
| 29 | Decision | Submit ordering (review round 1, minors 1-2) | Decided: the uploads are copied just before the application commit; any failure from the copy through the commit deletes the copies (no orphaned objects). The workflow starts right after that commit. The LO email and its outbox commit come next, wrapped so a failure is logged and never skips the pipeline or turns a committed submit into a 500. |
| 30 | Decision | Request-validation 422s (review round 1 nit) | Decided: a global `RequestValidationError` handler (`core/errors.py`) returns FastAPI's usual `{"detail": [...]}` minus each error's `input` and `ctx`, so a malformed body never echoes an SSN back. Small necessity outside owned files. |

No big gaps: nothing raised in Kaneo.

## Why

A borrower must be able to apply on their own and have the application priced by the same automation as an imported loan (spec Goal). 032a delivers everything server-side so 032b only builds screens.

## Per-tab data contract (for CQ-032b)

The draft's `data` is `{ "you": {...}, "property": {...}, "income": {...}, "consent": {...} }`. The UI PATCHes one tab at a time with the **whole tab object**. Every field is optional on save (partial data is saved as-is); the rules below are what validation reports in `field_errors`. Money and decimal fields are **strings** (e.g. `"450000"`, `"0.25"`) and the UI never computes money. Error keys are dotted paths inside the tab, e.g. `current_address.zip`, `co_borrower.ssn`.

### Tab 1 `you`

| Field | Type | Rule / error text |
| --- | --- | --- |
| `first_name`, `last_name` | string, 1–100 | required |
| `email` | — | read-only; not stored in tab data. Shown from the response's `email` (account email) |
| `cell_phone` | string | required; 10 digits after stripping non-digits → `"Enter a 10-digit phone number."` |
| `dob` | `YYYY-MM-DD` string only | required; anything else (a number, a datetime, `04/12/1988`) → `"Enter a date as YYYY-MM-DD."`; `"You must be at least 18 years old."` (age ≥ 18, ≤ 120) |
| `ssn` | string, **write-only** | required once; 9 digits (dashes/spaces allowed) → `"SSN must be 9 digits."`. **Never returned** (decision 25): the draft comes back with `ssn_last4` (e.g. `"6789"`) and `ssn_set: true` instead. Once `ssn_set` is true the UI shows a masked `•••-••-6789` and **omits** `ssn` from later PATCHes (omitted or blank keeps the stored one); send `ssn` again only when the borrower types a new one |
| `ssn_last4`, `ssn_set` | response only | server-written; ignored on PATCH (same for `co_borrower`) |
| `marital_status` | `married` \| `unmarried` \| `separated` | required |
| `dependents_count` | integer 0–20 | required |
| `current_address` | `{street, city, state, zip}` | all required; `state` 2 letters (upper-cased), `zip` 5 digits |
| `housing_status` | `own` \| `rent` \| `rent_free` | required |
| `residence_years` | integer 0–99 | required |
| `residence_months` | integer 0–11 | required |
| `prior_address` | `{street, city, state, zip, residence_years, residence_months}` \| null | required when `residence_years*12 + residence_months < 24` (ignored otherwise) → error on `prior_address`: `"Add your prior address (you've lived at your current address under 2 years)."` |
| `prior_housing_status` | `own` \| `rent` \| `rent_free` | optional, default `rent`: housing status at the prior address (written to `housing_history` sequence 1) |
| `has_co_borrower` | boolean | default false; when false any `co_borrower` block is ignored (not validated, not written) |
| `co_borrower` | `{first_name, last_name, email?, cell_phone, dob, ssn, marital_status, dependents_count}` \| null | required when `has_co_borrower`; same rules as the borrower (`email` optional, must look like an email); `ssn` is write-only and comes back as `ssn_last4` + `ssn_set` exactly like the borrower's |

Free text (address `street`/`city`, `employer_name`, `typed_name`, metro names, co-borrower `email`) is capped at 200 characters → `"Use 200 characters or fewer."`.

### Tab 2 `property`

| Field | Type | Rule / error text |
| --- | --- | --- |
| `occupancy` | `primary` \| `ltr` \| `str` | required (labels: "I'll live there", "Long-term rental", "Short-term rental") |
| `has_property` | boolean | required ("Do you have a property in mind?") |
| `address` | `{street, city, state, zip}` | required when `has_property` |
| `buy_box_states` | string[] (2-letter) | used when `!has_property` |
| `buy_box_metros` | string[] (metro names) | when `!has_property`: at least one → `"Choose at least one metro."`; each must be a known metro inside a chosen state → `"Choose a metro from the list."`. The picker loads `GET /api/v1/portal/applications/metros` (borrower session; decision 28) → `{states: [{state: "FL", metros: ["Davenport", "Tampa"]}, ...]}`: states for the first tier, that state's metros for the second |
| `target_price` | decimal string | required, > 0 → `"Enter a price greater than 0."` |
| `down_payment_pct` | decimal string | required; primary `0.03 / 0.05 / 0.10 / 0.15 / 0.20`, LTR/STR `0.15 / 0.20 / 0.25` → `"Choose one of the listed down payments."` |

### Tab 3 `income`

| Field | Type | Rule / error text |
| --- | --- | --- |
| `employer_name` | string | required for primary |
| `years_employed` | decimal string 0–99 | required for primary |
| `monthly_income` | decimal string | required for primary and > 0 → `"Monthly income is required for a home you'll live in."`; ≥ 0 otherwise |
| `monthly_debts` | decimal string ≥ 0 | required for primary |
| `liquid_assets` | decimal string ≥ 0 | required for everyone |
| `documents` | `[{id, doc_type, filename, content_type, size_bytes, uploaded_at}]` | **server-managed**, filled by the upload endpoint; ignored on PATCH |

Any negative number → `"Must be 0 or more."`. Money fields (price, income, debts, assets) must be under 100,000,000 (column precision).

### Tab 4 `consent`

| Field | Type | Rule / error text |
| --- | --- | --- |
| `soft_pull_authorized` | boolean (JSON `true`/`false` only: `"true"` or `1` fail) | must be true → `"Check this box to continue."` |
| `contact_consent` | boolean | must be true |
| `terms_accepted` | boolean | must be true |
| `typed_name` | string | must equal tab 1 `first_name + " " + last_name`, case-insensitive, whitespace collapsed → `"Type your full name exactly as entered on step 1."` |

### Responses

`ApplyDraftOut` (POST create, GET, and inside PATCH):

```
{ id, email, current_tab: "you"|"property"|"income"|"consent",
  tabs: { you: {complete: bool}, property: {...}, income: {...}, consent: {...} },
  data: {...}, submitted_application_id: uuid|null,
  consent: { version: "apply-v1", text: "..." },
  created_at, updated_at }
```

- `PATCH .../draft` body `{tab, data}` → `{ draft: ApplyDraftOut, tab, tab_valid, field_errors: {path: message} }`. `field_errors` also lists "required" for fields not yet filled, so the UI shows errors only for touched fields (or all of them on "Next").
- `POST .../submit` (no body) → `{ application_id, draft_id, status: "intake", assigned_lo_name, pipeline_started }`. 422 → `error.details: {field_errors: {tab: {path: msg}}, first_invalid_tab}`; 409 if already submitted (`error.details.application_id`); 429 `RATE_LIMITED` for a second submit by the same borrower within 10 minutes (decision 27).
- `GET /api/v1/portal/applications/metros` → `{states: [{state, metros}]}` (decision 28).
- Every error body has the app-wide shape `{"error": {code, message, details}}`, except a malformed request body (wrong JSON types, unknown tab), which is FastAPI's `{"detail": [{type, loc, msg}]}` without `input`/`ctx` (decision 30).
- Cross-field rules (prior address, co-borrower required, down payment option, metro, primary income) are checked once that tab's field-level rules pass, so a tab with several problems may reveal one of these on the next save.
- `POST .../documents` multipart `file` (one), `doc_type` (`pay_stub`|`w2`|`bank_statement`) → the new document entry (201). 413 (`FILE_TOO_LARGE`, also before auth when `Content-Length` is over the cap) / 411 (`LENGTH_REQUIRED`: send a `Content-Length`, which `fetch` with `FormData` does) / 415 (`UNSUPPORTED_FILE_TYPE`) / 422 (bad or missing `doc_type`, no file, two files, 20 documents already) / 409 (after submit).
- `DELETE .../documents/{document_id}` → 204.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Apply API (032a) | create `backend/app/features/portal/apply/{router,schemas,service,validation,documents,templates,consent_text}.py`, `tests/**` |
| Consent type (032a) | modify `backend/app/features/borrower/consent/models.py` (`ConsentType.APPLICATION`); create `alembic/versions/*_cq032_consent_type_application.py` |
| Mock credit (032a) | modify `backend/app/integrations/credit/mock.py` (portal key fallback, decision 12) |
| Registry / client (032a) | `core/registry.py` one line; regenerated `packages/api-client` |
| Wizard UI (032b) | `apps/borrower-portal/src/app/(portal)/apply/**`, `src/features/apply/**`, e2e specs |

## Tasks

| Task | Unit | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- | --- |
| T1 | 032a | Per-tab validation models | — | `apply/validation.py` | `tests/test_validation.py` (`test_apply_tab_validation` + age, SSN, price, metro, down payment, numbers, consent name) |
| T2 | 032a | Draft create/get/autosave + resume tab | T1 | `apply/{router,schemas,service}.py` | `tests/test_drafts.py` (create-or-return, isolation 404, autosave errors never block, resume at first incomplete tab, email read-only) |
| T3 | 032a | Consent type + migration | — | consent model, migration | `tests/test_submit.py::test_submit_records_consent`; `alembic heads` = 1 |
| T4 | 032a | Mock credit portal fallback | — | `integrations/credit/mock.py` | `tests/test_portal_credit.py` |
| T5 | 032a | Document upload (draft) | T2 | `apply/documents.py`, router | `tests/test_documents.py::test_document_upload_limits` |
| T6 | 032a | Submit: application graph, assignment, email, consent, docs, workflow start | T1–T5 | `apply/service.py`, `templates.py` | `tests/test_submit.py` (`test_ssn_encrypted_at_rest`, `test_submit_assigns_lo_and_emails`, `test_submit_records_consent`, docs in checklist, TBD metros, 422/409) |
| T7 | 032a | AC1 pipeline proof | T6 | `tests/test_submit_pipeline.py` | `test_submitted_tampa_str_reaches_priced` (time-skipping Temporal, real worker) |
| T8 | 032a | api-client, registry, E2E (slot 18) | T6 | registry line, `packages/api-client` | post-dev E2E log |
| T9 | 032b | Wizard shell: stepper, tab unlock, autosave 1 s, resume | T8 | `(portal)/apply/**`, `src/features/apply/**` | `ApplyWizard.validation.test.tsx`, `e2e/apply-wizard-resume.spec.ts` |
| T10 | 032b | Tabs 1–4 forms, uploads, confirmation | T9 | `src/features/apply/tabs/**` | Vitest per tab; `e2e/apply-wizard-to-priced.spec.ts` |
| T11 | 032b | a11y (labels, `aria-describedby`), react-doctor | T10 | same | AC8 evidence |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 (032a) | T1, T3, T4 | Contracts, migration, adapter first; no shared files |
| 2 (032a) | T2, T5 | Draft endpoints, then uploads on the draft (both touch `router.py`: done sequentially by one worker) |
| 3 (032a) | T6, T7, T8 | Submit needs everything above; api-client last |
| 4 (032b, phase wave 3) | T9 → T10 → T11 | UI on the merged API contract |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | 032a: `tests/test_submit_pipeline.py::test_submitted_tampa_str_reaches_priced` (Temporal time-skipping, real worker) + slot-18 E2E with `make worker`; 032b: `e2e/apply-wizard-to-priced.spec.ts` |
| AC2 | 032a: `tests/test_validation.py::test_apply_tab_validation` (primary without income fails tab 3; 14 months requires prior address) + `tests/test_drafts.py::test_autosave_returns_field_errors_without_blocking`; 032b: `ApplyWizard.validation.test.tsx` |
| AC3 | 032a: `tests/test_drafts.py::test_resume_returns_first_incomplete_tab` (tab 3 values restored, `current_tab = income`); 032b: `e2e/apply-wizard-resume.spec.ts` |
| AC4 | 032a: `tests/test_submit.py::test_ssn_encrypted_at_rest` (raw column ≠ digits, decrypts to digits); masked display is CQ-028b (pending re-check) |
| AC5 | 032a: `tests/test_submit.py::test_submit_assigns_lo_and_emails` + E2E Mailpit check |
| AC6 | 032a: `tests/test_submit.py::test_submit_records_consent` |
| AC7 | 032a: `tests/test_documents.py::test_document_upload_limits` (11 MB → 413, `.exe` → 415, PDF → 201 and a `documents` row after submit) |
| AC8 | 032b: react-doctor + axe evidence |

## Progress

- [x] T1 validation
- [x] T2 drafts
- [x] T3 consent type + migration
- [x] T4 mock credit fallback
- [x] T5 documents
- [x] T6 submit
- [x] T7 AC1 pipeline test
- [x] T8 api-client, registry, E2E
- [ ] T9–T11 (CQ-032b)
