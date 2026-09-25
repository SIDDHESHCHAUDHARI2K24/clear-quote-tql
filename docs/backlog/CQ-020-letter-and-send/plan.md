# CQ-020 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

Two units on one branch (`cq-020-letter-and-send`): **unit 1 — backend** (this plan's T1–T9, done by the backend worker) and **unit 2 — frontend worker** (T10–T13, done afterwards from the handoff). The API contract (T2) lands in unit 1 so unit 2 only consumes it.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | AC7 says 403 for an unassigned LO; Decision #11 / phase D6 say cross-LO access is 404 everywhere | Decided: **404**. `get_scoped_package` (CQ-019) already 404s out-of-scope packages, and D6 settles the whole phase on 404 so a probe can't tell "exists but not yours" from "doesn't exist". `test_letter_pdf_access` asserts 404 for the unassigned LO, 401 signed out, 200 for the assigned LO and a manager. Logged as a deviation in post-dev.md. |
| 2 | Decision | M3: what a `PUT /applications/{id}/package` does to a sent package | Decided: **reopen in place**, not copy. D2 makes `quote_packages` the working package and `quote_package_versions` the frozen sent snapshots; the frozen things (snapshot, PDF, token, outbox link) all live on the version row, which a PUT never touches. So a PUT on a package whose `sent_at` is set clears `sent_at` (it is a draft again: the Builder's star/delete hooks follow it again) and applies the edit. `sent_at` on the package now means "the current content is exactly the newest sent version". A copy would split one application's send history across several packages and break supersede (it is per `package_id` in `freeze_package_version` and in CQ-022's `_newest_report_token_for_package`). A PUT while a send is in flight (`send_status` queued/rendering/emailing) is a 409 `SEND_IN_PROGRESS`. |
| 3 | Decision | CQ-024 deferral: "ask_other is the only type allowed after an Inquiry is answered by a new version" | Decided: **not enforced as a restriction on the new version**; the link is recorded instead. The status machine (system-design.md: Inquiry → Priced "LO revises" → Sent) and CQ-024's own allowed-when table both let the borrower `move_forward` on a fresh, non-superseded Sent version, and revised numbers exist precisely so the borrower can pick one. The answered (old) version is superseded, and CQ-024 Decision 3 already blocks every action on a superseded version. The version↔inquiry link CQ-024 asked for is written by the Record step: the `quote.sent` activity event and the CRM event carry `in_reply_to_inquiry: true` and `previous_status` when the application was in Inquiry at send time. If the product owner wants the literal restriction, it is a one-line check in `portal/actions/service.py` keyed on that event. |
| 4 | Decision | PR #22 minor: "refill after the Builder deletes all quotes" | Decided: keep the CQ-019 rule. An *untouched* draft (`lo_edited=false`) that the Builder empties is refilled with the default selection on the next `GET` once quotes exist again; a draft the LO has ever saved (`lo_edited=true`) stays empty and readiness shows "Select at least one quote". The LO's explicit choices are never overwritten; a draft the LO never touched keeps tracking the defaults. Test: `test_untouched_draft_refills_after_builder_deletes_all_quotes`. |
| 5 | Decision (fix) | PR #22 minor: `_delete_quote_row` reports `recommendation_cleared=True` when the recommendation actually moved | Fixed: returns `True` only when the application ends with no recommendation. When the draft handed the recommendation to another quote, it returns `False`. Test: `test_reprice_reports_moved_recommendation_as_not_cleared`. |
| 6 | Decision | PDF key: spec says `packages/{package_id}/preapproval-letter.pdf`; a re-send would overwrite the older version's PDF | Decided: `packages/{package_id}/v{version}/preapproval-letter.pdf`. Each sent version keeps its own PDF (the Sent versions list downloads each). Deviation logged. `quote_packages.letter_key` mirrors the newest version's key. |
| 7 | Decision | Send progress / status source | Decided: DB-backed, like CQ-016's `last_pipeline_stage` (D7). New columns `quote_packages.send_workflow_id`, `send_status` (`queued`/`rendering`/`emailing`/`done`/`failed`), `send_error`. Each activity writes its step (only when the package's `send_workflow_id` is its own workflow). `GET /send-status` reads them: no Temporal round trip per poll, and it survives a worker restart. |
| 8 | Decision | Idempotency keys (AC5) | Decided: the workflow id. `quote_package_versions.send_workflow_id` (unique): Freeze returns the existing version for its workflow id. Render skips when the version's `letter_key` object exists. Email: `quote_package_versions.outbox_email_id` links the outbox row; a `sent` row is never re-sent. The row is committed `queued` before SMTP, then marked `sent`. Record skips when a `quote.sent` event for the version exists (status, event and CRM event are one transaction). The one residual window is a crash between the SMTP hand-off and the `sent` commit (at-least-once at the SMTP boundary); documented. |
| 9 | Decision | Workflow id / double click | Decided: `send-package-{package_id}-{uuid}` minted by `POST /send` under a `FOR UPDATE` lock on the package. If a send is already in flight (status queued/rendering/emailing) and its workflow is still running in Temporal, `POST` returns 202 with the existing id and starts nothing. A stuck status whose workflow is gone lets a new send start. |
| 10 | Decision | Spec's step 3 "Report link" | Folded into Freeze (the version's `report_token` is minted by `freeze_package_version`) plus the pure `report_url(token)` = `{PORTAL_BASE_URL}/report/{token}`. No separate activity: there is nothing to persist beyond the token. New setting `PORTAL_BASE_URL` (default `http://localhost:3020`; `scripts/worktree-env.sh` writes the slot's portal port). H2: no magic link, no account creation. |
| 11 | Decision | The PDF must match the frozen snapshot | Render builds a transient (never-added) `QuotePackage` from the version snapshot's option quote ids and recommended option, so a Builder change after Freeze can't change which quotes the letter shows. `letter_date` = version `sent_at` date. |
| 12 | Decision | Freeze re-checks readiness | Freeze re-runs `package_blockers`; if the package went not-ready between `POST` and Freeze (e.g. a reprice marked quotes stale), it fails non-retryably and the status becomes `failed` with the blocker message. Nothing is sent. |
| 13 | Decision | Sending a Withdrawn/Closed application | `POST /send` returns 409 with blocker `application_closed`. OptionSelected may be re-sent (the LO revises after the borrower picked). |
| 14 | Decision | WeasyPrint system libraries | There is no backend Dockerfile in the repo (H4: Railway image libraries come in CQ-035). Added instead: CI (`.github/workflows/ci.yml`) installs `libpango-1.0-0 libpangoft2-1.0-0` and runs a Mailpit service for the AC1 test; macOS dev uses `brew install pango` plus `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, which the Makefile now exports on Darwin for `test`, `api` and `worker`. |
| 15 | Decision | Retry policy for the send activities | `SEND_RETRY_POLICY`: 1 s initial, x2, max 30 s, 5 attempts, non-retryable `PackageNotReadyError`. CRM `ProviderUnavailableError` is retryable here (unlike the pipeline), so a CRM blip doesn't fail a send whose email already went out. After the last attempt the workflow runs `mark_send_failed` (status `failed`, `send_error`). |
| 16 | Decision | Email HTML | Table-based, inline-styled, one screen: greeting, address (or "Property to be determined"), purchase price, recommended option's monthly payment and cash to close (display formatting of snapshot strings only), a "See your numbers" button to `/report/{token}`, LO signature. A plain-text alternative carries the same lines and URL. The PDF is attached as `preapproval-letter.pdf`. |

No big gaps: nothing raised in Kaneo.

## Why

Sending is the last LO step of the demo: one click must produce the letter PDF, freeze the package, email the borrower a link into their report and record everything, exactly once, even across a worker restart.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Migration | create `alembic/versions/*_cq020_send_tracking.py` |
| Models | modify `backend/app/features/quotes/send/models.py` (send columns, version `send_workflow_id`/`outbox_email_id`) |
| Storage | create `backend/app/core/storage.py` |
| Config | modify `backend/app/core/config.py` (`portal_base_url`), `scripts/worktree-env.sh`, `.env.example` |
| PDF | modify `backend/app/features/quotes/pdf/service.py` (`render_letter_pdf`) |
| Email | modify `backend/app/features/notifications/email/service.py` (text part + attachments, `deliver_outbox_email`) |
| Send feature (new sub-feature) | create `backend/app/features/quotes/delivery/` (`router.py`, `schemas.py`, `service.py`, `email_template.py`, `tests/`) |
| Workflow | create `backend/app/workflows/send_quote_package.py`, `backend/app/workflows/send_activities.py`; modify `worker.py`, `retry_policies.py`, `constants.py` |
| Registry | modify `backend/app/core/registry.py` |
| M3 / minors | modify `backend/app/features/quotes/send/service.py` (`update_package`), `backend/app/features/quotes/builder/service.py` (`_delete_quote_row`) |
| CI / Make | modify `.github/workflows/ci.yml`, `Makefile` |
| API client | regenerate `packages/api-client` (`make api-client`) |
| Frontend (unit 2) | `apps/lo-console/src/features/send/**`, `apps/lo-console/src/app/applications/[id]/send/**` |

## API contract (unit 1 builds, unit 2 consumes)

All under `/api/v1`, staff session required, out-of-scope package = 404 (Decision 1).

| Route | Response |
| --- | --- |
| `POST /packages/{id}/send` | 202 `SendStarted {package_id, workflow_id, status}`. 409 `PACKAGE_NOT_READY` with `details.blockers: [{code, message, tab}]` (same shape as readiness). |
| `GET /packages/{id}/send-status` | 200 `SendStatus {package_id, workflow_id, status: idle/queued/rendering/emailing/done/failed, error, version, recipient_email, sent_at}` |
| `GET /packages/{id}/versions` | 200 `SentVersion[]`, newest first: `{id, version, sent_at, expires_at, superseded, viewed_at, report_url, letter_url, outbox_email_id, email_status, recipient_email}` |
| `GET /packages/{id}/letter.pdf[?version=N]` | 200 `application/pdf` (newest version with a PDF by default); 404 when none |
| `PUT /applications/{id}/package` | unchanged shape; reopens a sent package (Decision 2); 409 `SEND_IN_PROGRESS` during a send |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration + model columns | — | migration, `send/models.py` | `test_schema` (existing), all below |
| T2 | Schemas + router skeleton (contract) | T1 | `delivery/schemas.py`, `delivery/router.py`, `core/registry.py` | `test_send_refuses_when_not_ready` |
| T3 | `core/storage.py`, `render_letter_pdf`, `portal_base_url` | — | `core/storage.py`, `pdf/service.py`, `core/config.py` | `test_letter_pdf_contents` |
| T4 | Email: text part + attachments + `deliver_outbox_email`; borrower email template | — | `notifications/email/service.py`, `delivery/email_template.py` | `test_send_email_arrives_with_pdf`, `test_email_template_*` |
| T5 | Activities + workflow + worker registration + retry policy | T1, T3, T4 | `workflows/send_*.py`, `worker.py`, `retry_policies.py`, `constants.py` | `test_send_workflow_idempotent` |
| T6 | Service: start send, status, versions, letter stream | T2, T5 | `delivery/service.py`, `delivery/router.py` | `test_send_records_status_events_outbox`, `test_resend_supersedes_previous`, `test_letter_pdf_access` |
| T7 | M3 reopen + in-flight 409 | T1 | `send/service.py` | `test_put_on_sent_package_reopens_draft`, `test_put_during_send_is_409` |
| T8 | PR #22 minors (delete-row fix, refill test) | — | `builder/service.py`, `builder/tests/`, `send/tests/` | Decisions 4, 5 tests |
| T9 | CI/Make/WeasyPrint libs, `make api-client`, docs | T6 | `.github/workflows/ci.yml`, `Makefile`, `packages/api-client` | CI |
| T10 | unit 2 — frontend worker: Send confirm dialog → `POST /send`, poll `GET /send-status` (Rendering letter → Emailing → Done), 409 blockers shown | T9 | `apps/lo-console/src/features/send/**` | Vitest + Playwright |
| T11 | unit 2 — frontend worker: toast "Sent to {email}", status pill → Sent (refetch summary) | T10 | same | Vitest |
| T12 | unit 2 — frontend worker: "Sent versions" list (timestamp, PDF download via `letter_url`, "Open in Outbox" via `outbox_email_id`) | T9 | same | Vitest |
| T13 | unit 2 — frontend worker: PR #22 minor — a failed Send-tab save can be silently dropped by a later successful save (serialize saves / keep the failed state until a save of the same edit succeeds) | — | same | Vitest |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T3, T4, T8 | Contracts, schemas, migrations first; independent helpers |
| 2 | T2, T5, T7 | Contract and workflow on the new columns |
| 3 | T6 | Service wires the workflow to the routes |
| 4 | T9 | api-client regenerated before any frontend work |
| 5 (unit 2) | T10–T13 | Frontend consumes the generated client |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_send_email_arrives_with_pdf` (real SMTP → Mailpit API; PDF attachment; link `/report/{token}` of a version that belongs to him) |
| AC2 | `test_letter_pdf_contents` (pypdf text: name, price, LTV, term, FICO bracket, LO NMLS, portal URL; 1 page; 612×792 pt) |
| AC3 | `test_send_records_status_events_outbox` |
| AC4 | `test_send_refuses_when_not_ready` |
| AC5 | `test_send_workflow_idempotent` (every activity crashes once after its side effects; a second worker finishes after the first is shut down) |
| AC6 | `test_resend_supersedes_previous` |
| AC7 | `test_letter_pdf_access` (404 per Decision 1) |

## Progress

- [ ] T1
- [ ] T2
- [ ] T3
- [ ] T4
- [ ] T5
- [ ] T6
- [ ] T7
- [ ] T8
- [ ] T9
- [ ] T10 (unit 2)
- [ ] T11 (unit 2)
- [ ] T12 (unit 2)
- [ ] T13 (unit 2)
