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
| Migration | `alembic heads`; `alembic downgrade -1 && alembic upgrade head`; `alembic check` | single head `620ac6b6be31`; round trip OK; "No new upgrade operations detected." |
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

Round-1 verification (slot 18):

- `make lint`: exit 0.
- `make test`: backend 557 passed, seed 32, and the frontend suites (ui 163, lo-console 60, borrower-portal 95, api-client 2).
- Portal apply tests run 3× in a row: 63 passed each time.
- E2E `evidence/e2e_apply.py` with the API on 8118 and `make worker` on `cq-s18`: the application reaches **Priced** with 2 quotes. Log: `evidence/e2e-032a-slot18-review1.log`.

The Temporal workflow tests (`backend/app/workflows/tests`) were flaky on this loaded machine, on this branch **and on the unchanged base commit** (the base hung on one run). The failure is "another operation is in progress" at teardown, as the activities outlive the test on the shared connection. The P5/P6 conftest rewrite (a per-test `db_lock` and per-test workers) addresses this, and this branch now merges it.

## How to test manually

1. `bash scripts/worktree-env.sh 18`, then `make demo-reset`. Start the API (`uv run uvicorn app.main:app --port 8118`, run from the repo root) and `make worker`.
2. `uv run python docs/backlog/CQ-032-apply-wizard/evidence/e2e_apply.py` (run from the repo root). It signs up a new borrower, fills the 4 tabs (Tampa STR, TBD), uploads a PDF, tries 11 MB and .exe files, submits, polls as the assigned LO until priced, then checks Mailpit and the DB.

## Follow-ups

- The CQ-018 Quote Builder could open at the borrower's `down_payment_pct` preference (a `field_values` row with `source_ref = borrower_portal`).
- CQ-035: trust `X-Forwarded-For` in `auth.common.client_ip` behind the Railway proxy; consent rows pick it up automatically.
- CQ-033: use `portal_credit_key(application_id)` for a portal applicant's hard pull (the mock already returns 3 bureaus plus the middle score).
- CQ-032b: build against the "Per-tab data contract" in plan.md. Metros for the picker come from `GET /api/v1/portal/applications/metros`. SSNs come back masked (`ssn_last4`, `ssn_set`): omit `ssn` from PATCHes once it is set. Uploads must send a `Content-Length` (`fetch` with `FormData` does).
