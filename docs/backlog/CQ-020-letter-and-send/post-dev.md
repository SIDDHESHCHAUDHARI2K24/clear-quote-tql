# CQ-020 — Post-development notes

Unit 1 (backend) is complete; unit 2 (LO console frontend) follows on the same branch. The frontend worker adds its rows to each section below.

## Summary

`POST /packages/{id}/send` checks readiness (409 plus the blocker list when not ready) and starts the Temporal `SendQuotePackageWorkflow`. The workflow runs four idempotent activities. **Freeze** writes a `quote_package_versions` row with the token, `sent_at` and `expires_at` (+21 days). **Render** makes the WeasyPrint PDF and stores it in MinIO at a per-version key. **Email** sends a table-based HTML + text email with the PDF attached through SMTP/Mailpit, and always writes an `outbox_emails` row. **Record** sets status Sent and writes one activity event and one CRM event. The Send tab polls progress with `GET /send-status` and lists history with `GET /versions`; `GET /letter.pdf` streams a stored PDF. A PUT on a sent package reopens it as the draft (M3), and a PUT while a send is in flight is a 409. Two PR #22 minors are fixed or logged.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| AC7: 403 for an unassigned LO | 404 | Decision #11 / phase D6 (plan.md Decision 1): cross-LO access is 404 everywhere |
| PDF at `packages/{package_id}/preapproval-letter.pdf` | `packages/{package_id}/v{version}/preapproval-letter.pdf` | A re-send must not overwrite an older version's PDF (plan.md Decision 6) |
| "Report link" as its own activity | Folded into Freeze (the token) plus the pure `report_url()` | Nothing to persist beyond the token (plan.md Decision 10) |
| WeasyPrint libraries in the backend image | CI apt step + Makefile `PDF_ENV` on macOS | There is no backend Dockerfile yet; H4 puts the Railway image libraries in CQ-035 (plan.md Decision 14) |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1 | Met (backend) | `test_send_email_arrives_with_pdf`: real SMTP → Mailpit API, one message, `preapproval-letter.pdf` attached, `href` = `/report/{token}`; the portal report opens for Marcus's borrower session. Live slot 10: `evidence/marcus-hale-email.html`, `.txt` |
| AC2 | Met | `test_letter_pdf_contents` (pypdf: 1 page, 612×792 pt; name, price, LTV, term, FICO bracket, LO NMLS, portal URL). Live PDF: `evidence/marcus-hale-preapproval-letter.pdf` |
| AC3 | Met | `test_send_records_status_events_outbox` |
| AC4 | Met | `test_send_refuses_when_not_ready`, `test_send_refuses_a_closed_application` |
| AC5 | Met | `test_send_workflow_idempotent`: each activity crashes once after its side effects commit, and worker 1 is shut down after emailing, so worker 2 replays and finishes. Result: exactly 1 version, 1 PDF object, 1 SMTP send, 1 outbox row, 1 event, 1 CRM event. Also `test_double_click_returns_the_running_send` and `test_send_fails_cleanly_when_the_package_goes_stale` |
| AC6 | Met | `test_resend_supersedes_previous` (v1 `superseded=true` in the portal view model with `newest_report_token`; 2 PDFs). Live: v1 `t`, v2 `f` in `cq_dev_s10` |
| AC7 | Met, with deviation (404) | `test_letter_pdf_access` (manager 200, assigned LO 200, other LO 404, signed out 401) |

Live check on slot 10 (`make demo-reset`, API :8110, `make worker` on `cq-s10`): Jordan Lee signed in with password + OTP from Mailpit and sent Marcus Hale's package. Status went `queued → rendering → emailing → done` in about 1 s. The application summary showed `sent`, and Mailpit showed the subject with `preapproval-letter.pdf` attached. A re-send made v2, and v1 became superseded.

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m pytest backend` (what `make test` runs on macOS) | 551 passed (4 of 5 full runs). One earlier full run showed the known asyncpg "another operation is in progress" cascade (12 failed / 32 errors in workflow/schema/isolation tests); rerun green, not fixed here (separate branch) |
| Seed tests | `… python -m pytest seed` | 31 passed |
| CQ-020 tests | `… python -m pytest backend/app/features/quotes/delivery backend/app/features/quotes/builder/tests/test_cq020_minors.py` | 16 + 2 passed; AC5 test 5/5 green in a loop |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | Clean |
| Frontend | `pnpm -r run test` | 365 passed (no frontend changes in unit 1) |
| react-doctor | — | Unit 2 |

Environment note: `backend/conftest.py`'s `valkey` fixture FLUSHDBs Valkey db 15 by default, and every worktree shares it. Another session's test run wiped this run's staff session mid-test (a 401 in AC5). This worktree's `.env` sets `TEST_VALKEY_URL=redis://localhost:6379/12` (the slot's own db). See Follow-ups.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| — | Fresh-subagent review happens on the PR after unit 2 (orchestrator) | — |

## How to test manually

1. `scripts/worktree-env.sh 10 && make demo-reset`.
2. `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m uvicorn app.main:app --port 8110` and `make worker` (two terminals).
3. Sign in as `jordan.lee@clearquote-demo.test` and open Marcus Hale's package. `POST /api/v1/packages/{id}/send`, then poll `GET /send-status` until `done`.
4. Mailpit (http://localhost:8025): the "Your pre-approval and numbers from Total Quality Lending" email has the PDF attached. The button opens `http://localhost:3210/report/{token}` and needs the borrower to sign in.

## Follow-ups

- `scripts/worktree-env.sh` should give each slot its own `TEST_VALKEY_URL`: the shared default db 15 is flushed by every concurrent test run.
- No backend Dockerfile exists; CQ-035 must install Pango (`libpango-1.0-0 libpangoft2-1.0-0`) in the Railway image.
- If the product owner wants CQ-024's literal "only ask_other after an answered Inquiry", key it on the `quote.sent` event's `in_reply_to_inquiry` (plan.md Decision 3).
- With no worker running, a `queued` send stays queued: the workflow waits in Temporal. `PUT /package` returns 409 until a worker picks the send up, and `POST /send` returns the same workflow id. A send whose workflow was terminated can be restarted by `POST /send`.
- At-least-once at the SMTP boundary: a crash after the SMTP hand-off and before the `sent` commit re-sends on retry (plan.md Decision 8).
