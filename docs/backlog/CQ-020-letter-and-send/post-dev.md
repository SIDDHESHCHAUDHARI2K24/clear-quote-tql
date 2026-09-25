# CQ-020 — Post-development notes

Both units are complete: unit 1 (backend) and unit 2 (LO console frontend), on the same branch.

## Summary

`POST /packages/{id}/send` checks readiness (409 plus the blocker list when not ready) and starts the Temporal `SendQuotePackageWorkflow`. The workflow runs four idempotent activities. **Freeze** writes a `quote_package_versions` row with the token, `sent_at` and `expires_at` (+21 days). **Render** makes the WeasyPrint PDF and stores it in MinIO at a per-version key. **Email** sends a table-based HTML + text email with the PDF attached through SMTP/Mailpit, and always writes an `outbox_emails` row. **Record** sets status Sent and writes one activity event and one CRM event. The Send tab polls progress with `GET /send-status` and lists history with `GET /versions`; `GET /letter.pdf` streams a stored PDF. A PUT on a sent package reopens it as the draft (M3), and a PUT while a send is in flight is a 409. Two PR #22 minors are fixed or logged.

**Unit 2 (LO console).** The Send tab's confirm dialog now sends: `POST /send`, then a step list (Rendering letter → Emailing → Done) polled every 500 ms from `GET /send-status`. A 409 `PACKAGE_NOT_READY` lists the blockers in the dialog, and a failed send shows its error with "Try again". On done, a "Sent to {email}" toast appears, the header pill turns Sent (workspace summary refetch) and a "Sent versions" list shows each version: timestamp, Current/Superseded, "Download PDF" (`letter.pdf?version=N`) and "Open in Outbox" (`/outbox?email={id}`, CQ-029's route, plan.md Decision 17). Editing is locked while a send runs. A PUT refused with 409 `SEND_IN_PROGRESS` reverts to the server's package and follows the running send. The third PR #22 minor, where a failed save could be silently dropped by a later successful save, is fixed: failed edits ride along with every later save until one succeeds, and a Retry button re-sends them (Decision 20). Files: `apps/lo-console/src/features/send/` (`useSendFlow.ts`, `SendProgress.tsx`, `SentVersions.tsx`, `SendToast.tsx`, `versions.ts`, plus changes to `api.ts`, `useSendTab.ts`, `SendButton.tsx` and `SendTab.tsx`), `apps/lo-console/src/lib/api-client.ts` (`API_BASE_URL`), `e2e/p3-milestone-send-to-report.spec.ts` (P3 milestone and LO send-flow tests, one serial file), `e2e/p3-milestone-send-to-report.spec.ts`, `e2e/helpers/{send,mailpit}.ts`, `playwright.config.ts` (cross-app project). A backend fix came out of the full e2e run (Decision 21).

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| AC7: 403 for an unassigned LO | 404 | Decision #11 / phase D6 (plan.md Decision 1): cross-LO access is 404 everywhere |
| PDF at `packages/{package_id}/preapproval-letter.pdf` | `packages/{package_id}/v{version}/preapproval-letter.pdf` | A re-send must not overwrite an older version's PDF (plan.md Decision 6) |
| "Report link" as its own activity | Folded into Freeze (the token) plus the pure `report_url()` | Nothing to persist beyond the token (plan.md Decision 10) |
| WeasyPrint libraries in the backend image | CI apt step + Makefile `PDF_ENV` on macOS | There is no backend Dockerfile yet; H4 puts the Railway image libraries in CQ-035 (plan.md Decision 14) |
| "Open in Outbox" | Links to `/outbox?email={outbox_email_id}`, which 404s until CQ-029 | The Outbox viewer is CQ-029 (P5/P6) (plan.md Decision 17) |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1 | Met | Backend: `test_send_email_arrives_with_pdf`: real SMTP → Mailpit API, one message, `preapproval-letter.pdf` attached, `href` = `/report/{token}`; the portal report opens for Marcus's borrower session. Live slot 10: `evidence/marcus-hale-email.html`, `.txt`. **End to end (P3 milestone, also re-verifies CQ-022 AC1):** `e2e/p3-milestone-send-to-report.spec.ts`. Jordan Lee sends Marcus Hale's package in the LO console, and exactly one new email reaches Marcus in Mailpit, with only `preapproval-letter.pdf` attached. Its "See your numbers" link (`{PORTAL_BASE_URL}/report/{token}`, also in the text part) sends a signed-out browser to `/login?next=/report/{token}`. Marcus signs in with his password and the email OTP from Mailpit, then lands on "Marcus, here are your numbers" with no superseded banner. Screenshots: `evidence/p3-1-send-tab-ready-1280.png`, `p3-2-sent-toast-1280.png`, `p3-3-marcus-report-1280.png` |
| AC2 | Met | `test_letter_pdf_contents` (pypdf: 1 page, 612×792 pt; name, price, LTV, term, FICO bracket, LO NMLS, portal URL). Live PDF: `evidence/marcus-hale-preapproval-letter.pdf` |
| AC3 | Met | `test_send_records_status_events_outbox`. UI: the "LO send flow" test in `e2e/p3-milestone-send-to-report.spec.ts` checks the header pill turns Sent (`[data-status="sent"]`) after the send; Vitest `SendFlow.test.tsx` T10/T11/T12 checks the workspace refetch. `evidence/send-dialog-done-1280.png` |
| AC4 | Met | `test_send_refuses_when_not_ready`, `test_send_refuses_a_closed_application`. UI: Vitest "AC4 in the UI: a 409 PACKAGE_NOT_READY shows the blockers and polls nothing"; CQ-019's disabled-button checks still pass in `send-tab-draft.spec.ts` |
| AC5 | Met | `test_send_workflow_idempotent`: each activity crashes once after its side effects commit, and worker 1 is shut down after emailing, so worker 2 replays and finishes. Result: exactly 1 version, 1 PDF object, 1 SMTP send, 1 outbox row, 1 event, 1 CRM event. Also `test_double_click_returns_the_running_send` and `test_send_fails_cleanly_when_the_package_goes_stale` |
| AC6 | Met | `test_resend_supersedes_previous` (v1 `superseded=true` in the portal view model with `newest_report_token`; 2 PDFs). Live: v1 `t`, v2 `f` in `cq_dev_s10`. UI: the "LO send flow" e2e test sends twice. The Sent versions list shows the new version as Current and the previous one as Superseded, and the PDF link returns `application/pdf` starting with `%PDF-`. `evidence/sent-versions-1280.png`; Vitest "marks superseded versions…" |
| AC7 | Met, with deviation (404) | `test_letter_pdf_access` (manager 200, assigned LO 200, other LO 404, signed out 401). UI: the Sent versions PDF link points at the API origin and carries the staff cookie; it returns 200 for Jordan in the "LO send flow" e2e test |

Live check on slot 10 (`make demo-reset`, API :8110, `make worker` on `cq-s10`): Jordan Lee signed in with password + OTP from Mailpit and sent Marcus Hale's package. Status went `queued → rendering → emailing → done` in about 1 s. The application summary showed `sent`, and Mailpit showed the subject with `preapproval-letter.pdf` attached. A re-send made v2, and v1 became superseded.

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m pytest backend` (what `make test` runs on macOS) | 551 passed (4 of 5 full runs). One earlier full run showed the known asyncpg "another operation is in progress" cascade (12 failed / 32 errors in workflow/schema/isolation tests); rerun green, not fixed here (separate branch) |
| Seed tests | `… python -m pytest seed` | 31 passed |
| CQ-020 tests | `… python -m pytest backend/app/features/quotes/delivery backend/app/features/quotes/builder/tests/test_cq020_minors.py` | 16 + 2 passed; AC5 test 5/5 green in a loop |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | Clean |
| Frontend | `pnpm -r run test` | 365 passed (no frontend changes in unit 1) |
| **Unit 2** `make lint` | ruff, ruff format, mypy, eslint, tsc, prettier | Clean (exit 0) |
| **Unit 2** `make test` | worker stopped first; `TEST_VALKEY_URL` db 12 | Exit 0: backend 556 passed, seed 31, api-client 2, ui 141, borrower-portal 84, lo-console 155 (incl. the new `SendFlow.test.tsx`; rerun green after the review fixes) |
| **Unit 2** react-doctor | `npx react-doctor -y --blocking error` (apps/lo-console) | Exit 0, no errors. It first flagged "ref mutated during render" in the new hooks and in the existing `applicationIdRef` in `useSendTab`; fixed with layout effects and a state signal. The remaining warnings are pre-existing or advisory (complexity, state update after await) |
| **Unit 2** Playwright | full suite, `--workers 1`, slot 10, fresh `make demo-reset`, API + worker + both apps running | 51 passed, including both tests in `p3-milestone-send-to-report.spec.ts` (P3 milestone, then LO send flow). A second run without a reset fails only CQ-016 AC6 and CQ-018 AC8: they change seed state (withdraw, override) and were never safe to rerun |

Environment note: `backend/conftest.py`'s `valkey` fixture FLUSHDBs Valkey db 15 by default, and every worktree shares it. Another session's test run wiped this run's staff session mid-test (a 401 in AC5). This worktree's `.env` sets `TEST_VALKEY_URL=redis://localhost:6379/12` (the slot's own db). See Follow-ups.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | (unit 2, `/code-review` medium on the frontend commits) The P3 spec and the LO send-flow spec both sent Marcus Hale from different files under `fullyParallel`, so one send could supersede the other's version or be read as the other's email | Fixed: both tests are in one serial file, `e2e/p3-milestone-send-to-report.spec.ts` (cross-app project). Residual: a CQ-017/018 pricing spec that edits Marcus *during* a send can still fail it; evidence runs use `--workers 1` |
| Low–medium | `useSendFlow` retried a failing `send-status` read forever, leaving the tab locked on "Sending…" | Fixed: after 10 consecutive failures (about 5 s) the phase becomes `failed` with "Couldn't check the send's progress (…)" and editing unlocks. Test: "a status poll that keeps failing gives up…" |
| Low | A resync after a `SEND_IN_PROGRESS` refusal that read `done` never refreshed the pill or `sent_at`, and never cleared the notice | Fixed: a resync that reads `done` calls `onSent` (workspace refetch + package reload, which clears the notice). Test: "a SEND_IN_PROGRESS resync that finds the send already done…" |
| — | Fresh-subagent review of the whole PR | The orchestrator runs it |

## How to test manually

1. `scripts/worktree-env.sh 10 && make demo-reset`.
2. `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m uvicorn app.main:app --port 8110` and `make worker` (two terminals).
3. Sign in as `jordan.lee@clearquote-demo.test` and open Marcus Hale's package. `POST /api/v1/packages/{id}/send`, then poll `GET /send-status` until `done`.
4. Mailpit (http://localhost:8025): the "Your pre-approval and numbers from Total Quality Lending" email has the PDF attached. The button opens `http://localhost:3210/report/{token}` and needs the borrower to sign in.

5. UI: `pnpm --filter @cq/lo-console exec next dev -p 3110` (and the portal on 3210). Open Marcus Hale → Send, click "Send to borrower" → Send. Watch Rendering letter → Emailing → Done, the toast and the Sent pill, then the Sent versions list. E2E: `LO_BASE_URL=http://localhost:3110 PORTAL_BASE_URL=http://localhost:3210 pnpm exec playwright test e2e/p3-milestone-send-to-report.spec.ts --project cross-app` with `SEED_*_PASSWORD` exported and `make worker` running.

## Follow-ups

- `scripts/worktree-env.sh` should give each slot its own `TEST_VALKEY_URL`: the shared default db 15 is flushed by every concurrent test run.
- No backend Dockerfile exists; CQ-035 must install Pango (`libpango-1.0-0 libpangoft2-1.0-0`) in the Railway image.
- If the product owner wants CQ-024's literal "only ask_other after an answered Inquiry", key it on the `quote.sent` event's `in_reply_to_inquiry` (plan.md Decision 3).
- With no worker running, a `queued` send stays queued: the workflow waits in Temporal. `PUT /package` returns 409 until a worker picks the send up, and `POST /send` returns the same workflow id. A send whose workflow was terminated can be restarted by `POST /send`.
- CQ-029: the Outbox page should live at `/outbox` and open the row named by `?email={outbox_email_id}`. The Send tab already links there (plan.md Decision 17).
- The CQ-020 e2e specs add sent versions to Marcus Hale on every run, and they re-price his quotes if an earlier spec left them stale (`e2e/helpers/send.ts`). Other specs (CQ-016 AC6 withdraw, CQ-018 AC8 override) still need `make demo-reset` before a rerun.
- At-least-once at the SMTP boundary: a crash after the SMTP hand-off and before the `sent` commit re-sends on retry (plan.md Decision 8).
