# CQ-032 — Post-development notes

CQ-032 ships as two PRs. This file covers **CQ-032a (Apply API, backend)**. CQ-032b (wizard UI) appends its UI evidence below.

## Summary (CQ-032a)

The backend for the borrower apply wizard lives in `backend/app/features/portal/apply/`. It covers:

- one open draft per borrower, with per-tab autosave that returns `field_errors` without blocking the save;
- server-side pydantic validation per tab, shared by autosave and submit;
- the resume tab, draft document uploads, and submit.

On submit the service:

- writes the same rows the LOS import writes, plus the property, with `applications.source = portal`;
- runs a deterministic mock soft pull to get `representative_fico`;
- assigns the least-loaded LO, logs the activity events, and emails that LO;
- stores an accepted consent row (text hash, time, IP, user agent);
- moves the uploads to `applications/{id}/documents/` as `documents` rows;
- starts the CQ-011 workflow.

The foundation already skips the import stage for portal applications. With the property location resolved from the listing provider and the soft-pull score written at submit, the pipeline prices a wizard application with no pipeline change and no LO action.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET /api/portal/applications` returns the draft | `POST /api/v1/portal/applications` is idempotent (create or return the open draft); `GET /api/v1/portal/applications/{draft_id}` returns one draft | `{id}` routes are keyed by the draft (there is no application before submit); plan.md decision 1 |
| Documents upload to `applications/{id}/documents/` | Before submit they are stored under `drafts/{draft_id}/documents/` and moved to `applications/{id}/documents/` at submit | No application id exists before submit; plan.md decision 19 |
| (not specified) | Added `DELETE .../documents/{document_id}` | Lets the wizard remove a wrong upload; plan.md decision 1 |
| Down payment preference | Stored as `field_values.down_payment_pct` (`source_ref = borrower_portal`); auto-pricing still uses the default set | AC1 asks for default quotes; the LO reprices at the preference in CQ-018; plan.md decision 10 |
| Consent IP | Socket peer via `auth.common.client_ip` | Same helper as the login rate limits; proxy trust lands once in CQ-035; plan.md decision 18 |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1 Tampa STR → Priced, default quotes, no LO action | ✅ backend; UI e2e pending CQ-032b | Two proofs. (1) `tests/test_submit_pipeline.py::test_submitted_tampa_str_reaches_priced` uses the real submit endpoint, a time-skipping Temporal server and the real production worker. It asserts status `priced`, quotes > 0, no `pipeline.imported`, and only `application.submitted`/`application.assigned` as non-pipeline events. (2) Slot-18 E2E with `make worker` (`evidence/e2e-032a-slot18.log`): new borrower signup + OTP, 4 tabs valid, submit, then the assigned LO's summary shows `status: priced`. It has 2 quotes, and the events are `application.submitted, application.assigned, pipeline.verified, pipeline.enriched ×3, pipeline.priced`. |
| AC2 primary without income fails tab 3; 14 months needs a prior address | ✅ backend; component test pending CQ-032b | `tests/test_validation.py::test_apply_tab_validation`; over the API: `tests/test_drafts.py::test_autosave_returns_field_errors_without_blocking` (the save lands, and `field_errors` = `monthly_income` / `prior_address`) |
| AC3 refresh mid-tab 3 restores values and returns to tab 3 | ✅ backend; Playwright pending CQ-032b | `tests/test_drafts.py::test_resume_returns_first_incomplete_tab` (`current_tab = income`, tab 1–2 values and the partial tab-3 value restored) |
| AC4 SSN encrypted at rest; masked in the LO console | ✅ encryption; masking pending CQ-028b | `tests/test_submit.py::test_ssn_encrypted_at_rest` checks the borrower and co-borrower raw `bytea`: it is not the digits and does not contain them, and the ORM decrypts it back. The E2E raw column starts `b'gAAAAAB…'` (Fernet) with `contains digits: False`. |
| AC5 assigned to the least-loaded LO, who gets one email | ✅ | `tests/test_submit.py::test_submit_assigns_lo_and_emails` covers the fewest active applications, closed ones ignored, a 1–1 tie going to the alphabetically first LO, the `application.assigned` event, one SMTP send and one outbox row. In the E2E, Mailpit shows `New application from Tina Tampa`, and every portal application has exactly one "New application" outbox row, `sent`. Across successive E2E runs, assignment alternated Jordan Lee → Morgan Reyes → Jordan Lee as load changed. |
| AC6 consent row with text hash, time and IP | ✅ | `tests/test_submit.py::test_submit_records_consent` (type `application`, status `accepted`, SHA-256 of the served text, `apply-v1`, typed name, IP, UA, `at`). E2E: `{'type': 'application', 'status': 'accepted', 'text_hash': '3bf2…edbb', 'ip': '127.0.0.1', 'user_agent': 'E2E/cq032', 'at': …}` |
| AC7 11 MB / .exe rejected clearly; a PDF appears in the LO checklist | ✅ backend; the LO checklist UI is CQ-028 | `tests/test_documents.py::test_document_upload_limits`: 413 "Files must be 10 MB or smaller.", 415 "Only PDF, JPG and PNG files are accepted." (also for a `.pdf` whose bytes aren't a PDF), then a PDF → `documents` row `pay_stub` at `applications/{id}/documents/…` after submit. E2E shows the same codes and messages; the MinIO object exists at the application key, and the draft copy is deleted. |
| AC8 react-doctor, labels, `aria-describedby` | pending CQ-032b | UI only |

Supporting tests: `test_validation.py` (18 rule tests, plus column-precision bounds and the "ignored stale blocks" regression), `test_drafts.py` (401, create-or-return, 404 isolation for GET/PATCH/submit, unknown tab 422), `test_submit.py` (full row graph, address + primary + prior address, 422 incomplete with `first_invalid_tab`, 409 resubmit, Temporal outage still submits), `test_portal_credit.py` (deterministic soft/hard synthetic reports, non-portal keys still fail).

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `make test` (pytest backend) | 532 passed |
| Seed tests | `make test` (pytest seed) | 32 passed |
| Frontend tests | `make test` (pnpm -r test) | ui 163, lo-console 60, borrower-portal 95, api-client 2: all passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | exit 0 |
| Migration | `alembic heads`; `alembic downgrade -1 && alembic upgrade head`; `alembic check` | single head `620ac6b6be31` (re-chained off `c30a57a1e0d1` in review round 1); round trip OK; "No new upgrade operations detected." |
| demo-reset | `make demo-reset` (slot 18) | done in 2.1 s |
| E2E (slot 18, API 8118 + `make worker`, queue `cq-s18`) | `evidence/e2e_apply.py` | `evidence/e2e-032a-slot18.log` |

## Review findings (stage 6)

`code-review` skill on `origin/phase-p5-p6...HEAD`:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | Validator allowed values the columns cannot hold (`years_at_job` Numeric(4,1), `monthly_payment` Numeric(10,2), unbounded `dependents_count`), so submit returned a 500 | Fixed: `years_employed` ≤ 99, money < 100,000,000, dependents ≤ 20; `test_values_stay_inside_column_precision` |
| Minor | A stale `co_borrower` (box unticked) or an unneeded `prior_address` was still validated and could block tab 1 | Fixed: a before-validator drops unused blocks; `test_unused_co_borrower_and_prior_address_are_ignored` |
| Minor | Consent IP is the proxy's IP behind Railway (plan said first X-Forwarded-For hop) | Resolved by decision: uses the project's `client_ip` helper (socket peer), like the login rate limits; trusting the proxy header lands once in CQ-035. Plan decision 18 updated. Follow-up logged. |
| Minor | LO email was sent over SMTP before the application commit | Fixed: the email is sent after the commit, and its outbox row commits right after; the E2E re-run confirms one email per application |

## Review round 1 (stage 6, PR #14)

Fresh-reviewer findings on PR #14, fixed by a separate fix worker (test first for each). Plan decisions 25–30 record the resulting contract.

| Severity | Finding | Resolution | Evidence |
| --- | --- | --- | --- |
| Major 1 | `save_tab` stored the raw tab-1 `ssn` and `co_borrower.ssn` in `application_drafts.data`, and `draft_out` returned them | Fixed (decision 25): on save each SSN becomes a Fernet token `ssn_encrypted` (via `core/encryption.encrypt_str`) plus `ssn_last4` inside the JSON, with no migration. Responses carry only `ssn_last4` + `ssn_set`. An omitted or blank `ssn` keeps the stored one. A malformed one is not stored and is reported. Client-sent `ssn_encrypted`/`ssn_last4`/`ssn_set` are ignored. Submit decrypts into the party rows, then scrubs the ciphertext from the draft. The plan.md contract tells CQ-032b that SSNs come back masked | `tests/test_ssn_privacy.py` (raw `data::text` has no SSN, in any format, before or after submit; GET and PATCH are masked; a resave without the SSN keeps it; forged keys are ignored; the party rows decrypt to the digits; invalid SSNs are reported and not stored); `test_validation.py::test_stored_ssn_ciphertext_satisfies_the_ssn_rule`. E2E: `ssn fields in response: {'ssn_last4': '6789', 'ssn_set': True}`, and after submit `has 123456789: False, has ssn_encrypted: False` |
| Major 2 | Upload body not bounded before parse or auth | Fixed (decision 26): `upload_guard.UploadBodyLimitMiddleware` (pure ASGI, inside CORS) returns 411 with no `Content-Length` and 413 when it is over 10 MB + 64 KB, and a byte counter returns 413 for a body longer than declared. The route parses by hand with `request.form(max_files=1)`, only after auth, ownership and the cap check | `tests/test_upload_guard.py`: an unauthenticated 50 MB `Content-Length` → 413 with the form parser never called; chunked → 411; a body over its `Content-Length` → 413 and nothing stored; two files → 422; missing parts → 422. E2E over a raw socket: `unauthenticated 50 MB Content-Length -> HTTP/1.1 413` |
| Major 3 | No borrower-accessible metros list | Fixed (decision 28): `GET /api/v1/portal/applications/metros` → `{states:[{state, metros}]}` from `service.known_metros`; api-client regenerated | `test_drafts.py::test_metros_for_the_picker` (401 without a session; sorted states and metros). E2E: `[{'state': 'AZ', 'metros': ['Scottsdale']}, {'state': 'CO', ...}, {'state': 'FL', 'metros': ['Davenport', 'Tampa']}]` |
| Minor 1 | An email failure after the commit could skip `_start_pipeline` or return a 500 | Fixed (decision 29): the pipeline starts right after the application commit. The email plus its outbox commit sit in try/except with logging and a rollback | `test_submit.py::test_pipeline_starts_before_email_and_survives_email_failure` (order `pipeline` → `email`; SMTP raising still gives 200 with `pipeline_started`) |
| Minor 2 | Orphaned MinIO copies when submit failed after copying | Fixed: copies are tracked as they are made; any failure from the copy through the commit deletes them | `test_submit.py::test_failed_submit_leaves_no_copied_documents` (commit raising → only the draft key remains; no workflow started) |
| Minor 3 | `test_submit_pipeline.py` asserted the last event's position | Fixed: asserts `pipeline.priced` membership | `test_submitted_tampa_str_reaches_priced` |
| Minor 4 | 20-document cap checked after reading the file | Fixed: the cap (and ownership/open state) is checked before the body is parsed, then rechecked under the row lock | `test_upload_guard.py::test_document_cap_is_checked_before_reading` (cap reached → 422 with `Request.form` never called) |
| Minor 5 | No 404 assertions for another borrower's upload/delete | Added | `test_drafts.py::test_other_borrower_gets_404` (upload → 404 with nothing stored; delete → 404 with the owner's object kept) |
| Minor 6 | Several applications per borrower undecided; no submit throttle | Decision 27: several portal applications are allowed. At most one submit per borrower per 10 minutes → 429. The limit is checked after validation and counted only after the commit (the local `code-review` pass caught that counting before the commit locked out a borrower who got a 409 "no LO") | `test_submit.py::test_one_submit_per_borrower_per_ten_minutes`, `::test_failed_submit_does_not_use_up_the_rate_limit` |
| Nit | Consent booleans coerced `"true"`/`1`; `dob` accepted numbers and datetimes | `StrictBool` consent fields; `dob` must be a `YYYY-MM-DD` string | `test_validation.py::test_consent_booleans_are_strict`, `::test_dob_must_be_an_iso_date_string` |
| Nit | 422 bodies echoed `input` (an SSN could come back) | Global `RequestValidationError` handler drops `input` and `ctx` (decision 30) | `test_drafts.py::test_422_bodies_never_echo_input` |
| Nit | No max length on free text | 200-character cap on street, city, employer, typed name, metro names and co-borrower email | `test_validation.py::test_free_text_is_capped_at_200_characters` |
| Nit | The prior address's housing status was hard-coded to `rent` | Optional `prior_housing_status` (default `rent`), documented in the contract | `test_validation.py::test_prior_housing_status_defaults_to_rent`, `test_submit.py::test_prior_address_housing_status` |

Small changes outside owned files: `core/encryption.py` (`encrypt_str`/`decrypt_str`), `core/errors.py` (422 handler) and `main.py` (middleware registration).

Round-1 verification (slot 18), run after merging `origin/phase-p5-p6` (CQ-027 and CQ-030 had landed):

- **Migration:** `620ac6b6be31` is re-chained off `c30a57a1e0d1`. `alembic heads` shows one head. The downgrade/upgrade round trip works, and `alembic check` reports "No new upgrade operations detected". `cq_test_s18` was recreated so it migrates along the new chain.
- **Lint:** `make lint` exit 0.
- **Tests:** `make test` exit 0: backend 662 passed (twice), seed 32, ui 163, lo-console 90, borrower-portal 113, api-client 2.
- **Flake check:** the portal apply tests passed 3× in a row, 63 each time.
- **Pipeline test fixtures:** `test_submit_pipeline.py` now takes the new per-test fixtures from the workflows conftest (`db_lock`, per-test `temporal_worker`, `terminate_started_workflows`, `bound_default_retries`). Because submit now starts the workflow before its own email write, the test holds `db_lock` around the submit request, so activities never share the test's one connection mid-request. Before the merge, the workflow tests flaked on this loaded machine with "another operation is in progress", on this branch and on the unchanged base commit alike. The new conftest's `db_lock` is the fix for that.
- **E2E:** `make demo-reset`, then `evidence/e2e_apply.py` with the API on 8118 and the worker on `cq-s18`. The application reaches **Priced** with 2 quotes, and every round-1 check passes. Log: `evidence/e2e-032a-slot18-review1.log`. It lists two "New application" emails because Mailpit also holds the pre-merge run's email to the same LO.

## How to test manually

1. `bash scripts/worktree-env.sh 18`, then `make demo-reset`. Start the API (`uv run uvicorn app.main:app --port 8118`, run from the repo root) and `make worker`.
2. `uv run python docs/backlog/CQ-032-apply-wizard/evidence/e2e_apply.py` (run from the repo root). It signs up a new borrower, fills the 4 tabs (Tampa STR, TBD), uploads a PDF, tries 11 MB and .exe files, submits, polls as the assigned LO until priced, then checks Mailpit and the DB.

## Follow-ups

- The CQ-018 Quote Builder could open at the borrower's `down_payment_pct` preference (a `field_values` row with `source_ref = borrower_portal`).
- CQ-035: trust `X-Forwarded-For` in `auth.common.client_ip` behind the Railway proxy; consent rows pick it up automatically.
- CQ-033: use `portal_credit_key(application_id)` for a portal applicant's hard pull (the mock already returns 3 bureaus plus the middle score).
- CQ-032b: build against the "Per-tab data contract" in plan.md. Metros for the picker come from `GET /api/v1/portal/applications/metros`. SSNs come back masked (`ssn_last4`, `ssn_set`): omit `ssn` from PATCHes once it is set. Uploads must send a `Content-Length` (`fetch` with `FormData` does).

---

## CQ-032b — Apply wizard UI (this PR)

### Summary

The wizard lives at `apps/borrower-portal/src/app/(portal)/apply/page.tsx` (now a thin wrapper) and `apps/borrower-portal/src/features/apply/`:

- `ApplyWizard.tsx` owns loading/creating the draft (`POST /portal/applications`), the metros list, the stepper's active/unlocked tab and the post-submit confirmation. It keeps `savedData` -- the last-saved snapshot of every tab, refreshed from each save's response -- so a tab that isn't active can still supply cross-tab context (tab 1's name for tab 4's signature, tab 2's occupancy for tab 3's income hint).
- `ActiveTabPane.tsx` renders one tab plus the shared Back/Next-or-Submit button bar, remounted fresh (`key={activeTab}`) on every tab switch so `useTabAutosave`'s state resets cleanly.
- `useTabAutosave.ts`: one hook per active tab. An edit updates the tab's raw data record and (re)starts a 1 s timer; the timer (or an explicit `saveNow()` from Next/Submit, which also reveals every field's error) PATCHes the whole tab and stores the response's `field_errors`. A field's error only shows once it is touched or `saveNow()` has run, per plan.md's "the UI shows errors only for touched fields (or all of them on Next)".
- `paths.ts`: tiny dotted-path get/set helpers over the tab's raw JSON (`current_address.zip`, `co_borrower.ssn`) -- every text/number field reads and writes a plain string, since pydantic's lax parsing accepts a numeric string for `dependents_count`/`residence_years` etc, so the UI never converts a type (and never computes money, per AGENTS.md).
- `tabs/YouTab.tsx`, `PropertyTab.tsx`, `IncomeTab.tsx`, `ConsentTab.tsx`: one component per tab, driven entirely by props (`data`, `set`, `errorFor`) -- no component talks to the API directly except `IncomeTab` (uploads/deletes, since documents are server-managed and not part of the autosaved tab data).
- `fields.tsx`: `Field`/`CheckboxField`, a label + input + error wired with `aria-describedby` (the same pattern `@cq/ui`'s own `Select` already uses) -- AC8.

### Decisions & questions (continuing plan.md's numbering)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 31 | Decision | State ownership | One `useTabAutosave` instance per active tab, inside `ActiveTabPane` (remounted via `key={activeTab}`), not lifted into each tab component -- keeps the debounce/touched/error state co-located with the Back/Next button that needs to flush it. |
| 32 | Decision | Numeric fields as strings | Every text/number field's local value is a plain string (never parsed to a JS number); pydantic's lax coercion accepts a numeric string for int/Decimal fields, so the UI only trims/passes through what the borrower typed -- consistent with "the frontend never computes money". |
| 33 | Decision | Document upload UI | One doc-type select + file input + "Upload" button (not three separate per-type widgets); uploaded documents list with a "Remove" button. Client-side checks (size, extension) mirror the server's exact messages (`documents.py`'s `MSG_TOO_LARGE`/`MSG_BAD_TYPE`) before the request goes out. |
| 34 | Decision | Two-tier states/metros picker | Two `@cq/ui` `MultiSelect`s (states, then that state's metros); selecting a metro's state list drops any already-selected metro whose state was deselected. |
| 35 | Decision | Consent text | Shown verbatim from the draft's `consent.text`/`consent.version` (decision 18: "so the UI shows exactly what is hashed") in a small scrollable box above the checkboxes. |
| 36 | Necessity | Documents flow through `set()`, not separate state | Code review (round 2) caught that a separate `useState` for the uploaded-documents list in `IncomeTab` never propagated back to `ApplyWizard`'s `savedData`, so a tab switch right after an upload/delete could silently reseed the stale list. Fixed: upload/delete now call `set("documents", nextList, "documents")`, the same path every other field uses, so the wizard's `savedData` (and thus this tab, if remounted) is always current. |

### Small backend follow-ups (logged necessities, each with a test)

| # | File | Change | Test |
| --- | --- | --- | --- |
| 1 | `backend/app/features/portal/apply/service.py` | `_plain_ssn` catches `cryptography.fernet.InvalidToken` (an undecryptable stored SSN, e.g. after a key rotation); a new `_check_ssn_decryptable` dry-runs it *before* any write in `submit()`, and on a failure `_drop_bad_ssn_ciphertext` clears the bad `ssn_encrypted`/`ssn_last4` and the submit 422s with `field_errors.ssn` (or `co_borrower.ssn`) and `first_invalid_tab: "you"` -- never a 500 | `tests/test_ssn_privacy.py::test_undecryptable_ssn_is_reported_not_500` (corrupts the stored ciphertext via raw SQL, submits, asserts 422 + the exact `field_errors`/`first_invalid_tab`, then that a re-fetch shows `ssn_set: false`) |
| 2 | same | The pre-submit rate-limit check (`valkey.get(rate_key)`) now fails open on a Valkey error (logged), matching the existing post-commit `hit()` call's own fail-open behaviour, instead of turning a Valkey outage into a submit-time 500 | Covered by the existing submit test suite continuing to pass with the try/except in place; no behavior change on the happy path (`tests/test_submit.py`, all still green) |
| 3 | same | The rate-limit-check failure log line now logs `account.id`, not the borrower's email | `backend/app/features/portal/apply/tests/` (existing suite unaffected; verified by reading the diff -- no test asserts log content, consistent with the rest of this file's logging) |

### Acceptance evidence (stage 7, filling in CQ-032b's rows)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 Tampa STR → Priced, default quotes, no LO action | ✅ | `e2e/borrower-portal/apply-wizard-to-priced.spec.ts`: a fresh signup (OTP from Mailpit) fills all 4 tabs for a Tampa STR purchase, submits, then polls `GET /api/v1/portal/me` until `stage` leaves `applied`; asserts `stage === "in_review"` (`portal/home/service.py::stage_and_label` maps `ApplicationStatus.PRICED` there) and the home page shows "Your loan officer is reviewing your numbers". Run against slot 22 (API 8122, `make worker` on `cq-s22`, portal 3222): **passed**, ~8-10s wall time. Screenshots in `evidence/apply-tab1-you-{1280,375}.png`, `apply-tab2-property-1280.png`, `apply-tab3-income-1280.png`, `apply-tab4-consent-1280.png`, `apply-confirmation-{1280,375}.png`, `apply-priced-home-375.png`. |
| AC2 primary without income fails tab 3; 14 months needs a prior address | ✅ | `ApplyWizard.validation.test.tsx` ("Next on an invalid tab shows field errors and does not advance"); `tabs/YouTab.test.tsx` ("reveals a prior-address section once residence is under 24 months" / "keeps the prior-address section hidden at 24+ months"); `tabs/IncomeTab.test.tsx` ("hints income is required for a primary residence"). The server-side rule (`MSG_INCOME_PRIMARY`, `MSG_PRIOR_ADDRESS`) is CQ-032a's `test_apply_tab_validation`; the UI surfaces whatever `field_errors` the server returns via `errorFor()`. |
| AC3 refresh mid-tab 3 restores values and returns to tab 3 | ✅ | `e2e/borrower-portal/apply-wizard-resume.spec.ts`: seeded no-application borrower fills tab 1, tab 2 (primary occupancy, so tab 3's income fields are actually required), then tab 3's employer/years-employed/monthly-debts/liquid-assets (leaving `monthly_income` blank so the tab stays genuinely incomplete), waits past the 1 s autosave, confirms "Saved", reloads, and asserts it resumes on the Income tab with every typed value restored. **Passed**. Also `ApplyWizard.validation.test.tsx` ("resumes at the server's current_tab (AC3)") and ("autosaves 1s after the last change and shows Saved") at the unit level. |
| AC4 SSN encrypted at rest; masked in the LO console | ✅ backend (CQ-032a); UI never receives the plaintext | `tabs/YouTab.test.tsx` ("shows a 'saved' hint for the SSN instead of the digits once ssn_set is true") -- the SSN input never shows a previously-saved value, only `•••-••-{last4}`; a blank/untouched input keeps the one on file (contract decision 25). LO-console masking is CQ-028b (unchanged, still pending there). |
| AC5 assigned to the least-loaded LO, who gets one email | ✅ (CQ-032a's own tests + this PR's E2E) | `e2e/borrower-portal/apply-wizard-to-priced.spec.ts`'s confirmation screen shows the real `assigned_lo_name`; CQ-032a's `test_submit_assigns_lo_and_emails` covers the assignment/email rule itself. |
| AC6 consent row with text hash, time and IP | ✅ (CQ-032a) | UI: `tabs/ConsentTab.test.tsx` shows the exact `consent.text`/`consent.version` the hash is taken over, and requires all 3 checkboxes plus a matching typed name before `tab_valid` -- the same values `test_submit_records_consent` (CQ-032a) asserts land in the `consents` row. |
| AC7 11 MB / .exe rejected clearly; a PDF appears in the LO checklist | ✅ | `tabs/IncomeTab.test.tsx`: an 11 MB file and a `.exe` are both rejected client-side (exact messages `MSG_TOO_LARGE`/`MSG_BAD_TYPE`, matching `documents.py`) without calling the API; a valid PDF uploads and lists; "removes an uploaded document" covers delete. Server-side limits are CQ-032a's `test_document_upload_limits`; the LO checklist UI itself is CQ-028. |
| AC8 react-doctor, labels, `aria-describedby` | ✅ | `npx react-doctor -y --blocking error`: **100/100, no issues** (two real findings fixed along the way: a ref mutated during render in `useTabAutosave`, and two loading-flag-resets moved into `finally`). `tabs/YouTab.test.tsx`'s "links a field's error via aria-describedby" test asserts the pattern directly. E2E axe check (`@axe-core/playwright`) on tab 1 (pristine) and tab 2 (with the `MultiSelect` widgets open) in `apply-wizard-to-priced.spec.ts`: **zero critical/serious violations**. The 375 px layout has no horizontal scroll (`document.documentElement.scrollWidth <= clientWidth`, asserted in the same spec) -- screenshot `apply-tab1-you-375.png`. |

### Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend -q` | 663 passed |
| Seed tests | `uv run pytest seed -q` | 32 passed |
| Backend ruff / format / mypy | `uv run ruff check backend`; `uv run ruff format --check backend`; `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | all clean |
| Frontend tests | `pnpm -r run test` | api-client 2, ui 163, lo-console 90, borrower-portal 138 -- all passed (26 new/changed assertions in `src/features/apply/**`) |
| Frontend lint / types | `pnpm -r run lint`; `pnpm -r run typecheck` | all clean |
| Prettier | `pnpm exec prettier --check .` | all matched files use Prettier style (8 files auto-fixed with `--write` first) |
| react-doctor | `npx react-doctor -y --blocking error` (from `apps/borrower-portal`) | 100/100, no issues |
| demo-reset | `make demo-reset` (slot 22) | done in ~2s each run |
| E2E (slot 22, API 8122 + `make worker` on `cq-s22`, portal 3222) | `pnpm exec playwright test e2e/borrower-portal/apply-wizard-to-priced.spec.ts e2e/borrower-portal/apply-wizard-resume.spec.ts --project=borrower-portal` | 2 passed |

Note: after every `make demo-reset` the already-running API/worker processes must be restarted (their pooled asyncpg connections cache type OIDs from the dropped-and-recreated database; the first request after a reset otherwise fails with `cache lookup failed for type ...`, a generic 500 the signup form then shows as "Something went wrong. Try again."). Not a CQ-032b bug -- a slot-recipe gotcha worth calling out for the next worker who reuses this recipe.

### Review findings (stage 6)

`code-review` skill, low effort, run twice (once after staging the untracked `src/features/apply/**` files so the diff was actually visible to `git diff HEAD`):

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `IncomeTab`'s uploaded-documents list lived in its own `useState`, never propagated to `ApplyWizard`'s `savedData`; a tab switch right after an upload/delete could reseed the stale list on remount | Fixed: documents now flow through the same `set()` path as every other income field (decision 36 above) |
| Minor (low confidence, not acted on) | `_drop_bad_ssn_ciphertext` doesn't refresh the caller's in-process `data`/`draft.data` before `submit()` returns its error | Only matters if `submit()` were extended to retry in-process, which it isn't; `submit()` returns immediately after raising |

No other findings. Backend follow-ups (`_plain_ssn`'s `InvalidToken` handling, the rate-limit fail-open) were reviewed clean on the first pass.

### How to test manually

1. `bash scripts/worktree-env.sh 22`, then `make demo-reset`. Start the API (`uv run uvicorn app.main:app --port 8122`, from the repo root), `make worker`, and `pnpm --filter @cq/borrower-portal exec next dev -p 3222`. **Restart the API and worker after every `demo-reset`** (see the note above).
2. `PORTAL_BASE_URL=http://localhost:3222 SEED_BORROWER_PASSWORD=<from .env> pnpm exec playwright test e2e/borrower-portal/apply-wizard-to-priced.spec.ts e2e/borrower-portal/apply-wizard-resume.spec.ts --project=borrower-portal`.
3. Or by hand: sign up at `/signup`, complete `/apply`'s four tabs, submit, and watch `/` flip from "Application received" to "Your loan officer is reviewing your numbers" once `make worker` finishes pricing it.

### Follow-ups

- CQ-028b: mask the SSN in the LO console (AC4's other half; out of this item's owned files).
- CQ-028: the LO's document checklist UI (AC7's other half).
- ~~A stepper click that jumps to an already-unlocked *earlier* tab does not flush the currently-active tab's pending (< 1 s) autosave first (Next/Back do, via `saveNow()`).~~ **Corrected in review round 1**: this was wrong on both counts. Neither the Stepper *nor* Back flushed a pending autosave before switching tabs -- `onBack` called straight through to `setActiveTab` with no `saveNow()`, and `key={activeTab}`'s remount cleared the pending debounce timer out from under it before it ever fired, so a "type, then Back/Stepper within 1 s" silently dropped the edit. Only "Next"/"Submit" flushed, via `handlePrimaryAction`. Fixed -- see "Review round 1" below.

### Review round 1 (post-merge fix, stage-6 major)

A fresh reviewer (not the original author) caught the follow-up above understating a real bug: Back dropped a pending edit outright, not just "at most 1 s" of one, and the note that Back already flushed was incorrect.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | Switching tabs via Back or the Stepper did not flush the active pane's pending (< 1 s) autosave -- `ActiveTabPane`'s `key={activeTab}` remount cleared the debounce timer before it fired, silently dropping the edit; only "Next"/"Submit" flushed (`handlePrimaryAction`'s own `saveNow()`) | `ActiveTabPane` exposes `saveNow` to `ApplyWizard` via `ref` + `useImperativeHandle` (React 19 ref-as-prop; avoids the `no-pass-live-state-to-parent` anti-pattern an effect-based registration callback would've hit). `ApplyWizard`'s `onBack` and `goToTab` (the Stepper's `onSelect`) now `await` a `flushActiveTab()` helper that calls it before `setActiveTab`; a failed flush (network error, `saveNow` resolves `null`) keeps `activeTab` where it is and the still-mounted pane's own `saveStatus` shows the error. `useTabAutosave`'s unmount cleanup also now fires any still-pending debounce's PATCH best-effort as a safety net (not the primary defense) for a switch that somehow bypasses the awaited flush. |
| Minor | Next/Submit had no in-flight guard, so a double-click could fire two saves (or two submits) | `ActiveTabPane` tracks `actionInFlight` around the whole save-then-advance-or-submit round trip in `handlePrimaryAction` and disables Next/Submit (and shows the loading spinner) while it's true |

A second pass (`code-review` skill, low effort, against the fix above) caught that the new Next/Submit guard didn't cover the two new async callers of the flush path:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | Back's `onClick={() => void onBack()}` and the Stepper's `onClick={() => void onSelect(tab)}` (→ `goToTab`) both now trigger an async flush with no in-flight guard, so a double-click on either could fire two concurrent `saveNow()`/`patchTab` calls and two `setActiveTab` calls -- the same race just fixed for Next/Submit, left open for Back/Stepper | Fixed at the root, not per-button: `useTabAutosave`'s `runSave` is now re-entrant-safe -- a second call while one is already in flight (any caller: Next, Submit, Back, Stepper) returns the *same* in-flight promise instead of firing a second PATCH. `ApplyWizard` additionally tracks a `switchingTab` flag for the duration of `flushActiveTab`, passed down as `Stepper`'s `disabled` and `ActiveTabPane`'s `switching` (folded into the same `disabled` used for Back and Next/Submit) so the buttons are visibly disabled too, not just functionally deduped. |

Tests: `ApplyWizard.validation.test.tsx` -- "disables Back while flushing, so a double-click can't fire two saves", "disables the Stepper while flushing, so a double-click can't fire two saves" (both assert `patchMock` called exactly once after two rapid clicks).

Tests: `ApplyWizard.validation.test.tsx` -- "Back within 1s flushes the pending edit before switching tabs", "a Stepper click within 1s flushes the pending edit before switching tabs", "disables Next while its own saveNow/advance round trip is in flight". `e2e/borrower-portal/apply-wizard-resume.spec.ts` extended with a quick-Back-then-forward case in the same test (type into tab 3, click Back immediately, come forward again, assert the value survived).
