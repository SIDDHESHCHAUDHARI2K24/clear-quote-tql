# CQ-020 — Handoffs

Append one entry per handoff, newest at the bottom. A new session reads spec.md, plan.md, then the latest entry.

## Handoff N — YYYY-MM-DD HH:MM — <agent>

- **Branch / last commit:** `cq-xxx-slug` @ `abc1234`
- **Stage:** 1 Brainstorm | 2 Plan | 3 Execute | 4 Code | 5 Test | 6 Review | 7 Verify | 8 Commit
- **Done:**
- **In progress:** file, function, what is half-finished
- **Next 3 steps:**
  1.
  2.
  3.
- **Open questions / blockers:**
- **Verify state:** commands to run first (e.g. `make up && make test`)

## Handoff 1 — 2026-09-25 21:00 — backend worker (Opus) → frontend worker

- **Branch / last commit:** `cq-020-letter-and-send` (off `origin/phase-p3-p4`); see `git log`. Pushed. No PR yet: the frontend worker opens it (`--base phase-p3-p4`).
- **Stage:** unit 1 (backend) at stage 7 done; unit 2 (frontend, plan.md T10–T13) not started. Stage 6 fresh-subagent review is still to do, on the whole PR.
- **Done (unit 1):** migration `d4a1c0f2e920` (single alembic head); `SendQuotePackageWorkflow` + 5 activities (`app/workflows/send_quote_package.py`, `send_activities.py`, steps in `features/quotes/delivery/steps.py`), registered on the same worker/task queue; send endpoints (`features/quotes/delivery/router.py`); `core/storage.py`; `render_letter_pdf`; email attachments + `deliver_outbox_email`; borrower email template; M3 reopen + `SEND_IN_PROGRESS` 409; `_delete_quote_row` fix; CI Pango + Mailpit; Makefile `PDF_ENV`; `PORTAL_BASE_URL` setting; `make api-client` regenerated. Tests for AC1–AC7 are green (see post-dev.md).
- **API contract for unit 2** (all `/api/v1`, staff cookie, types in `packages/api-client` as `SendStarted`, `SendStatus`, `SentVersion`):
  - `POST /packages/{id}/send` → **202** `{package_id, workflow_id, status: "queued"}`. **409** `{"error": {"code": "PACKAGE_NOT_READY", "details": {"blockers": [{code, message, tab}]}}}`: same blocker shape as `GET /readiness`, plus `application_closed`. A double click while a send is in flight returns 202 with the _same_ `workflow_id`. **503** `SEND_UNAVAILABLE` when Temporal is down.
  - `GET /packages/{id}/send-status` → `{package_id, workflow_id, status, error, version, recipient_email, sent_at}`. `status` is one of `idle | queued | rendering | emailing | done | failed`. UI mapping: queued/rendering → "Rendering letter", emailing → "Emailing", done → "Done", failed → show `error`. Poll about every 500 ms until done/failed. On done, show the toast "Sent to {recipient_email}" and refetch the workspace summary (status pill → `sent`), the package (`sent_at` set) and the versions.
  - `GET /packages/{id}/versions` → `SentVersion[]`, newest first: `{id, version, sent_at, expires_at, superseded, viewed_at, report_url, letter_url, outbox_email_id, email_status, recipient_email}`. `letter_url` is an API _path_ (`/api/v1/packages/{id}/letter.pdf?version=N`): prefix `NEXT_PUBLIC_API_URL` and open it with credentials (a plain `<a href target=_blank>` works because the cookie is sent to the API origin). `letter_url`/`outbox_email_id` are null for seeded versions (Grace Kim, Luis Romero). "Open in Outbox" → `/outbox?email={outbox_email_id}`; the Outbox viewer is CQ-029 (P5/P6), so the link may 404 until then. Say so in post-dev.
  - `GET /packages/{id}/letter.pdf[?version=N]` → `application/pdf`, 404 when nothing was sent.
  - `PUT /applications/{id}/package` now returns **409 `SEND_IN_PROGRESS`** during a send. A PUT on a sent package reopens it (`sent_at` → null). The Send tab should disable editing while `send-status` is in flight.
- **Unit 2 files:** `apps/lo-console/src/features/send/` (`SendButton.tsx` has the confirm dialog, `useSendTab.ts`, `api.ts`, `SendTab.tsx`), `apps/lo-console/src/app/applications/[id]/send/page.tsx`, `e2e/lo-console/`. T13 is the PR #22 minor: a failed Send-tab save can be silently dropped by a later successful save (see `useSendTab.ts`/`draft.ts` save sequencing).
- **Next 3 steps:**
  1. T10/T11: wire the confirm dialog to `POST /send`, the progress poller, the 409 blockers, the toast and the pill refresh (Vitest with a mocked client).
  2. T12: Sent versions list (timestamp, PDF download, Open in Outbox); T13: the save-ordering minor.
  3. Playwright spec for the LO send flow on slot 10 (screenshot at 1280 into `evidence/`), `npx react-doctor -y --blocking error`, post-dev frontend rows, fresh-subagent review, open the PR.
- **Open questions / blockers:** none. Decisions 1–16 are in plan.md.
- **Verify state:**
  - `scripts/worktree-env.sh 10`
  - `make demo-reset`
  - `make lint`
  - `make test`: stop any `make worker` first. `make test` now runs `python -m pytest` with `DYLD_FALLBACK_LIBRARY_PATH` on macOS, because WeasyPrint needs Homebrew Pango. Also put `TEST_VALKEY_URL=redis://localhost:6379/12` in `.env`: the default db 15 is flushed by other sessions' test runs.
  - Stack: `make worker` (queue `cq-s10`) and `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m uvicorn app.main:app --port 8110`.
  - LO app: `pnpm --filter @cq/lo-console exec next dev -p 3110`.
  - Send Marcus Hale's package from the Send tab and check Mailpit at http://localhost:8025.
  - The known asyncpg "another operation is in progress" flake may appear in one full run; rerun it.

## Handoff 2 — 2026-09-25 — PR #30 review-fix worker (Opus)

- **Branch:** `cq-020-letter-and-send` (pushed from local `cq-020-fix`). PR #30 → `phase-p3-p4`, not merged.
- **Done:** both majors and minors a–f from the fresh review, TDD; see post-dev.md "Review findings" and plan.md Decisions 22–23.
- **Verify state:** `scripts/worktree-env.sh 10`; `make lint`; `make test` (no worker running); `make demo-reset`, then API :8110, `make worker`, LO :3110, portal :3210 and `pnpm exec playwright test e2e/p3-milestone-send-to-report.spec.ts e2e/lo-console/send-tab-draft.spec.ts --workers 1` with `SEED_*_PASSWORD` exported (e.g. `uv run --no-sync --env-file .env pnpm exec playwright ...`).
- **Test note:** `test_concurrent_posts_send_once` commits real data (a real lock race needs two connections) and removes it afterwards: it empties every table that was empty before the test, with FK triggers off. Never use `TRUNCATE ... CASCADE` there: `settings` references `users` and would be wiped. That breaks every later test with "Missing required setting"; the fix is to recreate `cq_test_s10`.
- **Next:** the orchestrator re-reviews and merges.
