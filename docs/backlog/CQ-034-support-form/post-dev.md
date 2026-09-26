# CQ-034 — Post-development notes

## Summary

Built `POST /api/v1/portal/support`: a borrower session posts `{topic, message, preferred_contact, phone?}`, which is rate-limited (5/hour, Valkey), validated with per-field pydantic errors, and creates one `support_requests` row with a short unambiguous reference (`SUP-XXXXX`, retried on collision). It emails `settings.support_inbox` with the borrower's contact info, message, and (when they have one) their latest application's id, CQ-031-mapped stage, internal status, property label, the assigned LO, and a link to the LO console (`settings.lo_console_base_url`, new); with no application the body says "No application yet". It writes one activity event (`support.requested`) when there's an application, and sends the borrower a short confirmation email with the reference. On the frontend, `/support` is a full form (topic select, message textarea with a character counter, preferred-contact radio, phone prefilled from `/me`), with a confirmation state showing the reference and the assigned LO's direct contact, and a 429 shows "Please try again later". The borrower login page gained a "Need help signing in?" line with the support email.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| — | Added `phone: str | None` to `BorrowerMeOut` (`auth/borrower/schemas.py`/`service.py`) | Small necessity (plan.md Decision #3): the phone prefill needs a per-borrower source; `/me` already fetches the `Client` row and is already loaded once per portal session via `useBorrowerSession()`, so this is the only zero-extra-request option that works for a borrower with 0 or 2+ applications |
| — | Added `settings.lo_console_base_url` (new setting; none existed) | Task brief explicitly asks for this ("Add an `lo_console_base_url` setting if one doesn't exist, and log the decision") — plan.md Decision #2 |
| — | Local `_stage_key_for`/`_STAGE_LABELS` in `support/service.py` duplicate CQ-031's status→stage table | CQ-031 (`features/portal/home/`) hasn't merged into `phase-p5-p6` yet in this worktree — plan.md Decision #1. **Follow-up**: switch to CQ-031's canonical function post-merge and delete this copy |
| — | Dropped the "Support" row from `apps/borrower-portal/src/app/(portal)/page.test.tsx`'s stub-page `it.each` (foundation file, not owned) | `/support` is no longer a stub; its coverage moved to `SupportForm.test.tsx` — plan.md Decision #9 |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — Marcus Hale submits a "quote" question; Mailpit shows one support-inbox email with name/email/phone/message/stage/status/LO/console link and one confirmation with the same reference | ✅ | `backend/app/features/portal/support/tests/test_router.py::test_support_request_emails`; e2e `e2e/borrower-portal/support.spec.ts::submitting a quote question emails the support inbox and the borrower, with the same reference` — run live on slot 19 against real Mailpit, both tests passed (`2 passed (8.9s)`); screenshot `evidence/support-confirmation-1280.png` |
| AC2 — one outbox row and one activity event on his application | ✅ | Same test: asserts `len(emails) == 2` (inbox + confirmation, both `application_id`-tagged) and `len(events) == 1` with `type == "support.requested"` |
| AC3 — a 9-character message, or phone preference without a phone, rejected with field errors | ✅ | `test_support_validation_short_message`, `test_support_validation_phone_required_when_preferred` (both 422); frontend: `SupportForm.test.tsx`'s two "linked error" tests exercise the same rules client-side with `aria-describedby` |
| AC4 — 6th request in an hour returns 429, page shows "Please try again later" | ✅ | `test_support_rate_limit` (API, exact message asserted); `SupportForm.test.tsx::shows 'Please try again later' on a 429`; e2e `a 6th request in an hour is rate-limited...` (5 requests via direct API + the 6th through the real UI form) — passed live; screenshot `evidence/support-rate-limited-1280.png` |
| AC5 — a borrower with no application can still submit; email says "No application yet" | ✅ | `test_support_without_application` (uses a borrower with no `Application` row; asserts the inbox email's HTML contains "No application yet" and zero `ActivityEvent`s are written) |
| AC6 — react-doctor passes; form is fully keyboard operable with visible, linked errors | ✅ | `npx react-doctor -y --blocking error` on `@cq/borrower-portal`: **100/100, no issues** (after splitting `SupportForm` into `MessageField`/`ContactFields`/`SupportConfirmation` sub-components per a `no-high-complexity-react-function` warning); `SupportForm.test.tsx::is fully keyboard-operable...` tabs through every field in order and lands on the submit button |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (whole suite) | `uv run pytest backend` | 507 passed (two runs showed transient `InterfaceError`/connection-pool failures unrelated to this item — shared Postgres container under concurrent load from sibling wave-2 workers; a clean re-run twice in a row passed 505 then 507 (+2 for the escaping regression tests) with zero failures) |
| Seed tests | `uv run pytest seed` | 32 passed |
| `backend/app/features/portal/support` | `uv run pytest backend/app/features/portal/support -q` | 13 passed |
| Lint / types (backend) | `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | clean |
| Full `make lint` | `make lint` | clean (ruff, mypy, eslint × 4 workspaces, tsc × 4 workspaces, prettier) |
| Frontend (whole monorepo) | `pnpm -r run test` | api-client 2, ui 163, lo-console 60, borrower-portal 101 — all passed |
| `SupportForm.test.tsx` | `pnpm --filter @cq/borrower-portal exec vitest run src/features/support` | 7 passed |
| react-doctor | `npx react-doctor -y --blocking error` (borrower-portal) | 100/100, no issues |
| e2e (slot 19, live Mailpit/Postgres/Valkey) | `pnpm exec playwright test e2e/borrower-portal/support.spec.ts --project=borrower-portal --workers=1` | 2 passed |
| e2e typecheck | `npx tsc --noEmit` (root, covers `e2e/**`) | clean |
| Prettier (e2e + touched files) | `npx prettier --check e2e/ apps/borrower-portal/src/features/support apps/borrower-portal/src/app/login` | clean |

### Fix worker re-run (after merging `phase-p5-p6`, review round 1)

| Check | Command | Result |
| --- | --- | --- |
| `backend/app/features/portal/support` | `uv run pytest backend/app/features/portal/support -q` | 16 passed (13 prior + 3 new: STALE without/with a sent version, option_selected LO first name) |
| `backend/app/features/portal` (support + home together) | `uv run pytest backend/app/features/portal -q` | 70 passed |
| `make api-client` | `make api-client` | regenerated `packages/api-client/openapi.json`/`src/schema.d.ts` after the merge conflict (CQ-031's `/api/v1/portal/me` types were missing until this ran) |
| Full `make lint` | `make lint` | clean (ruff, ruff format, mypy, eslint × 4 workspaces, tsc × 4 workspaces, prettier) |
| Full `make test` | `make test` | backend 566 passed, seed 32 passed, `pnpm -r run test` (api-client 2, ui 163, lo-console 90, borrower-portal 113) all passed |
| Borrower-portal vitest (incl. `SupportForm.test.tsx`, `page.test.tsx`, `stub-pages.test.tsx`) | `pnpm --filter @cq/borrower-portal exec vitest run` | 113 passed, 21 files |
| `make demo-reset` (slot 19) | `uv run alembic upgrade head && make demo-reset` | clean, 2.4s |
| e2e re-run (slot 19, live API + portal + Mailpit/Postgres/Valkey, post-merge/post-fix) | `pnpm exec playwright test e2e/borrower-portal/support.spec.ts` with `LO_BASE_URL`/`PORTAL_BASE_URL`/`SEED_BORROWER_PASSWORD` exported | 2 passed (17.7s) — AC1/AC2/AC4 still hold after the `stage_and_label` switch |

## Review findings (stage 6)

Fresh-subagent `code-review` skill run against the diff. Three findings; two fixed, one logged as an accepted, already-documented tradeoff.

| Severity | Finding | Resolution |
| --- | --- | --- |
| High (security) | `portal/support/templates.py` interpolated borrower-/LO-supplied free text (`message`, `phone`, `borrower_name`, `lo_name`, `property_label`) unescaped into the HTML email sent to the real support inbox and the borrower — a stored-HTML/phishing-link vector (e.g. a message containing `<a href="http://evil.example">...</a>` renders as a live link in an HTML mail client) | Fixed: added `_esc()` (`html.escape(..., quote=True)`) and applied it to every plain-text row value and every heading/intro/footer string; the one legitimate `<a href=...>` (the LO console link, built from `lo_console_base_url` + a UUID) escapes its own URL and builds the anchor explicitly rather than going through a "trusted by default" path. New regression tests: `test_support_inbox_html_escapes_borrower_supplied_markup`, `test_confirmation_html_escapes_borrower_name` |
| Low | The login page's "Need help signing in?" email was a bare hardcoded string with nothing keeping it in sync with the backend's `settings.support_inbox` if that's ever overridden | Fixed: reads `NEXT_PUBLIC_SUPPORT_EMAIL` (same pattern as `NEXT_PUBLIC_API_URL`), falling back to the same default; documented in both `.env.example` files with a "keep these in sync" note |
| Info | `_STAGE_LABELS`/`_stage_key_for`/`_property_label` in `support/service.py` duplicate logic CQ-031 will own canonically, with no automated parity check until CQ-031 merges | Not fixed — this is the explicit, human-approved decision in `phase-p5-p6-plan.md` (parallel-wave item workers write small local helpers, log a follow-up, and the orchestrator reconciles post-merge); no CQ-031 module exists in this worktree to test parity against yet. Follow-up already logged in plan.md Decision #1 |

## Review round 1

Fresh-subagent `code-review` skill run against `cq-034-support-form` after merging `phase-p5-p6` (which brought CQ-031's `features/portal/home/` in). One major finding, fixed; one accepted follow-up logged (not a fix here — shared pattern across every `send_email` caller).

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `support/service.py`'s own `_STAGE_LABELS`/`_STATUS_TO_STAGE_KEY`/`_stage_key_for` (the CQ-031-merge follow-up from Decision #1 above) checked `QuotePackage.sent_at` for its STALE split, but runtime code never sets that column (CQ-031/CQ-020 stamp `sent_at` on `QuotePackageVersion`, not `QuotePackage`) — so a sent-then-stale application was always mislabelled `in_review` ("Your loan officer is reviewing your numbers") in the support email instead of `preapproved`. The `option_selected` label was also a bare "You chose an option", dropping CQ-031's "— {LO first name} will be in touch" clause. | Fixed: deleted the local `_STAGE_LABELS`/`_STATUS_TO_STAGE_KEY`/`_stage_key_for` and switched `submit_support_request` to CQ-031's canonical `stage_and_label`/`has_ever_sent` (`app.features.portal.home.service`). `_has_ever_sent` was module-private in `home/service.py`; promoted to `has_ever_sent` (public) with a one-line docstring noting the new caller — the only other change to that module. New tests: `test_support_stale_without_sent_version_is_in_review`, `test_support_stale_with_sent_version_is_preapproved`, `test_support_option_selected_includes_lo_first_name` |
| Accepted (not fixed here) | `notifications/email/service.py::send_email` calls `smtp_send` (the real SMTP delivery) before the caller's `db.commit()` — `support/service.py`'s `submit_support_request` commits once, at the very end, after both the inbox and confirmation emails have already gone out over SMTP. A crash or exception between either `send_email` call and that final `db.commit()` rolls back the `SupportRequest`/`OutboxEmail`/`ActivityEvent` rows while the email has already been delivered: an "email sent, no record" gap. | Not fixed here — `send_email`'s own docstring already documents "does not commit, caller owns the transaction" as the contract, and every other `send_email` caller (OTP issue, CQ-020 send, CQ-024 actions) has the identical shape, so this is a shared pattern across the codebase, not specific to CQ-034. Logged as a follow-up below for whoever picks up hardening `notifications/email/service.py` (e.g. commit the outbox row in its own transaction before sending, or move the SMTP call after the caller's commit via an outbox-poller pattern) |

Deviations table update: the row "Local `_stage_key_for`/`_STAGE_LABELS` in `support/service.py` duplicate CQ-031's status→stage table" above is resolved as of this round — both were deleted and `submit_support_request` now calls CQ-031's `stage_and_label`/`has_ever_sent` directly.

## How to test manually

1. `source scripts/worktree-env.sh 19 && make demo-reset` (bash, not zsh).
2. `uv run uvicorn app.main:app --port 8119` (from the repo root — `cd backend` first breaks `.env` discovery, since `Settings`'s `env_file=".env"` is CWD-relative and there is no `backend/.env`; logged here since the worker guide's own recipe says `cd backend && uv run uvicorn ...`).
3. `pnpm --filter @cq/borrower-portal exec next dev -p 3219`.
4. Sign in as `marcus.hale@clearquote-demo.test` / `$SEED_BORROWER_PASSWORD`, go to `/support`, submit a "quote" question with a real message. Confirmation shows "Your reference is SUP-XXXXX" and Jordan (his LO)'s email/phone.
5. Check Mailpit (`http://localhost:8025`) for two emails: one to `support@tql.local` with subject `[SUP-XXXXX] quote — Marcus Hale`, one to Marcus with subject `We got your message — SUP-XXXXX`.
6. Submit 5 more times within the hour; the 6th shows "Please try again later".
7. Sign out and visit `/login`: "Need help signing in? Email us at support@tql.local" appears below the sign-in form.

## Follow-ups

- ~~Once CQ-031 (`features/portal/home/`) merges into `phase-p5-p6`, switch `support/service.py`'s `_stage_key_for`/`_STAGE_LABELS` to its canonical stage-mapping function and delete the local copy (plan.md Decision #1).~~ Done in review round 1 above (CQ-034 fix worker, PR #19): `support/service.py` now calls `home/service.py`'s `stage_and_label`/`has_ever_sent` directly; the local copy is deleted.
- **New (review round 1, accepted, not fixed here)**: `notifications/email/service.py::send_email` sends over SMTP before the caller's `db.commit()`. Every caller (OTP issue, CQ-020 send, CQ-024 actions, this item's inbox/confirmation emails) shares the same "email sent, no record" gap if the process dies between the send and the commit. Worth a dedicated hardening item on `notifications/email/`, not a per-caller fix.
- The shared Postgres container under concurrent load from sibling wave-2 workers intermittently produces `InterfaceError`/rollback failures across the whole backend suite (not specific to this item — reproduced on unrelated `backend/tests/*` and `backend/app/workflows/tests/*` files); a clean re-run always passes. Worth a note to the orchestrator if other workers hit the same flakiness.
- `apps/lo-console/.env.example` doesn't exist (only `apps/borrower-portal/.env.example` does), so the `LO_CONSOLE_BASE_URL`/`NEXT_PUBLIC_SUPPORT_EMAIL` sync note only lives in the borrower-portal one and the repo-root one; fine for now since neither app reads the other's env file, just noting it in case a later item adds one.
