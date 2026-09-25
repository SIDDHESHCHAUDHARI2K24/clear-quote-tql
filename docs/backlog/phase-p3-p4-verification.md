# Phase P3 + P4: final verification before `phase-p3-p4` → `main`

Run on 2026-09-25 on branch `p34-final-verify`, cut from `origin/phase-p3-p4` at a39ab90 (CQ-020 merged via PR #30; test-flake fix via PR #28). All of CQ-016 to CQ-024 are merged into `phase-p3-p4`.

Environment: slot 0 (`scripts/worktree-env.sh 0`). DBs `cq_dev_s0`/`cq_test_s0`, API :8100, LO console :3100, portal :3200, Temporal queue `cq-s0`, Valkey db 2. `.env` also sets `TEST_VALKEY_URL=redis://localhost:6379/2`. The stack is the shared `make up` infra.

Evidence is in `docs/backlog/phase-p3-p4-verification/`.

## Result

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| 1a | `alembic heads` = 1 | Pass: `d4a1c0f2e920 (head)` | this doc |
| 1b | `make lint` | Pass (ruff, ruff format, mypy, eslint, tsc, prettier) | `make-lint.log` |
| 1c | `make test`, no worker running | Pass. Backend 572, seed 31, api-client 2, ui 141, borrower-portal 84, lo-console 156 | `make-test.log` |
| 1d | `make demo-reset` < 60 s | Pass: 1.9 s wall (`elapsed: 1.1s`) | `demo-reset.log` |
| 2 | `make e2e` (Playwright, 51 tests) | Pass serially. Parallel runs flake on shared seed data (details below) | `e2e-run*.log` |
| 3a | CQ-022 AC1 end to end on a real send | Pass | `1-email-link-redirects-to-login.png`, `2-report-after-signin.png`, `real-send-api.json`, `real-send-email.txt` |
| 3b | CQ-024 AC1 on a really sent package | Pass | `3a-…`, `3b-moved-forward-confirmed.png`, `cq024-checks.json`, `cq024-lo-email.txt`, `db-state-{before,after}-move-forward.txt` |
| 3c | CQ-024 AC6 on a really sent package | Pass, with the known deviation: the header updates on the next load, not on an idle poll | `4-lo-header-viewed-before.png`, `4-lo-header-option-selected.png`, `p4-ui-notes.txt` |
| 3d | CQ-019 AC2 against a real send | Pass (the only difference is the two portal-only wrapper fields, as plan.md Decision 3 allows) | `cq019-ac2-staff-preview.json`, `cq019-ac2-portal-report.json` |
| 3e | P4 milestone: emailed link → switch options → move forward → LO header shows OptionSelected | Pass | screenshots 1–4, `p4-ui-notes.txt` |

No real product failure was found. One small test fix was made (see 2).

## 1. Integration branch health

```
uv run alembic heads          # d4a1c0f2e920 (head)
make lint                     # exit 0
make test                     # exit 0: 572 + 31 pytest; vitest 2 / 141 / 84 / 156
time make demo-reset          # exit 0, 1.909 s total
```

## 2. E2E (`make e2e` = `pnpm exec playwright test`)

The command was `uv run --no-sync --env-file .env pnpm exec playwright test` with `LO_BASE_URL=http://localhost:3100` and `PORTAL_BASE_URL=http://localhost:3200`. The API, `make worker`, and both `next dev` apps ran on slot 0. Every run followed a fresh `make demo-reset`.

| Run | Mode | Result | Log |
| --- | --- | --- | --- |
| 1 | parallel (default workers) | 48 passed, 2 failed, 1 did not run (45.7 s) | `e2e-run1-parallel.log` |
| 2 | `--workers 1` | **51 passed** (1.6 min) | `e2e-run2-serial.log` |
| 3 | parallel, after the locator fix | 43 passed, 2 failed, 6 did not run (44.6 s) | `e2e-run3-parallel-after-fix.log` |

Run 2 used the fixed `workspace.spec.ts` (the fix below). The "did not run" tests are later tests in a serial file whose first test failed.

**Why the parallel runs fail.** Both causes are test isolation, not product bugs:

- *OTP collision on one shared staff account.* In run 1 `pricing-latency` AC7 failed, and in run 3 `quote-builder` AC1 failed. Many specs sign in as `jordan.lee@…` at the same moment. `readOtpCode` reads the newest OTP email for that address, so a test can pick up another test's code. The page then shows "Invalid or expired code" and `waitForURL("/")` times out.
- *Concurrent edits to Marcus Hale.* In run 3, `pricing-latency` AC7 did not see the breakdown change. Another spec was changing or re-pricing Marcus at the same time. This is the known "pricing specs editing Marcus race" issue.

**Small fix (logged): `e2e/lo-console/workspace.spec.ts`.** In run 1, CQ-016 AC5 failed a strict-mode check: `getByText("Ben Ford")` matched both the `<h1>` and Next.js's `__next-route-announcer__`, and whether the announcer holds the name depends on timing. The four `getByText("<persona name>")` assertions (AC2, AC5, AC8) now use `getByRole("heading", { name })`. It did not recur in runs 2 or 3.

Each e2e run overwrites the committed evidence screenshots of CQ-016 to CQ-024. Those changes were reverted after every run, so this PR does not change them.

## 3. Cross-item re-checks against a real send

Setup:

1. A fresh `make demo-reset`.
2. Restart the slot-0 API and worker, because a reset under a running API causes one `InvalidCachedStatementError` 500; see Follow-ups.
3. `POST /api/v1/packages/{id}/send` for Marcus Hale's package as Jordan Lee (staff password + Mailpit OTP), with the worker running on `cq-s0`.

Scripted through the API (httpx) and a one-off Playwright spec that was not committed; the results are in the evidence files.

**The send** (`real-send-api.json`):

- `POST /send` returned 202 `queued`. `send-status` went `queued → rendering → emailing → done`.
- The summary status went from `priced` to `sent`.
- Mailpit received "Your pre-approval and numbers from Total Quality Lending" for `marcus.hale@…`. It had `preapproval-letter.pdf` (application/pdf, 37,181 bytes) attached and the link `http://localhost:3200/report/<token>`. The email text is in `real-send-email.txt`.

**CQ-022 AC1:** the email link, then sign-in, then the report. The result is correct and the report data equals the frozen snapshot.

- Opening the emailed link in a fresh browser redirected to `/login?next=%2Freport%2F<token>` (`1-email-link-redirects-to-login.png`).
- Signing in with password and the Mailpit OTP landed on `/report/<token>` with "Here are your numbers" (`2-report-after-signin.png`).
- The borrower's `GET /portal/reports/{token}` response, minus the portal-only `borrower_action`/`newest_report_token` wrapper, equals `quote_package_versions.snapshot` for that version (`True`).

**CQ-019 AC2** (`cq019-ac2-*.json`): the staff preview `GET /packages/{id}/report` and the portal `GET /portal/reports/{token}` for the sent version differ only in the portal-only keys `borrower_action` and `newest_report_token`. Every other key is identical, including `header` (sent the same day). The raw bodies are not byte-identical because of those two wrapper fields. CQ-019 plan.md Decision 3 and `send/tests/test_report.py::PORTAL_ONLY_FIELDS` explicitly allow that difference.

**CQ-024 AC1** (move forward on Buydown on the real send; `cq024-checks.json` and the DB diff in `db-state-*-move-forward.txt`):

- The application status went from `viewed` to `option_selected`.
- `quote_package_versions.borrower_action` = `{type: move_forward, quote_id: 9dbd8d53-…}`. That is the Buydown quote: it is the `?option=` the Buydown radio set.
- Exactly one LO email, "Marcus Hale would like to move forward with Buydown", to `jordan.lee@…` (`cq024-lo-email.txt`).
- Exactly one activity event (`quote.move_forward`) and one CRM event (`borrower.move_forward`).
- AC2, checked as a side effect: a second `move_forward` returned 409 `CONFLICT` "This option has already been acted on." No new LO email was sent (the count is still 1).

**CQ-024 AC6 / P4 milestone** (screenshots 3a, 3b, 4 and `p4-ui-notes.txt`):

- Selecting the Buydown radio set `?option=` and showed the alternative-view note.
- "Move forward with this option" → "Yes, let Jordan know" showed "You chose Buydown on September 25, 2026".
- The LO console header for Marcus showed `Viewed` before and `Option selected` after the next load.
- As logged in CQ-024 post-dev (Deviations, AC6), an idle workspace page does **not** update by itself: after waiting 6 s without navigating the header still showed the old status (`LO header updated by poll alone: false`). `WorkspaceProvider` stops polling once the pipeline is terminal. This is the existing CQ-016/CQ-025 follow-up, not a regression. CQ-025 tiles are not merged into this branch, so the tile half of AC6 does not apply.

## Follow-ups (non-blocking)

Newly observed here:

- The e2e suite is not parallel-safe:
  - Specs share one staff account, so concurrent logins steal each other's OTP.
  - Specs mutate Marcus Hale concurrently.
  - Use `--workers 1` after a fresh `make demo-reset` until CQ-036 gives specs per-test accounts or data, or serializes the Marcus specs.
  - Running e2e rewrites the committed evidence PNGs of CQ-016 to CQ-024.
- `make demo-reset` while the API is running: the first request on each pooled connection fails with a 500 (`InvalidCachedStatementError`), because the schema was dropped and recreated under asyncpg's prepared-statement cache. Dev only. Restart the API and worker after a reset, or have the reset dispose the pools.

From CQ-020 (post-dev and handoff):

- SMTP is at-least-once: a crash after the SMTP hand-off and before the `sent` commit re-sends on retry (Decision 8). The 20 s `SEND_ACTIVITY_TIMEOUT` makes this window easier to hit, because a slow SMTP hand-off can now time out and retry.
- A second click on `POST /send` returns 500 on a Temporal RPC error instead of `SendUnavailableError` 503 (`features/quotes/delivery/service.py` ~146, the `describe`/double-click path).
- `test_send_execution_timeout_exceeds_the_worst_case_retry_budget` has two gaps:
  - Its retry budget leaves out `mark_send_failed`.
  - It counts activities by scanning the workflow's source text.
- `scripts/worktree-env.sh` should set a per-slot `TEST_VALKEY_URL`. The shared default db 15 is flushed by every concurrent test run. This run set it by hand.
- The Send tab's "Open in Outbox" link returns 404 until CQ-029 builds `/outbox?email=…`.
- CQ-035 must install Pango (`libpango-1.0-0 libpangoft2-1.0-0`) in the Railway image for WeasyPrint.
- A `queued` send with no worker running waits up to 10 min (`SEND_EXECUTION_TIMEOUT`) before it is marked failed.
- CQ-024's literal "only ask_other after an answered Inquiry" rule is deferred (CQ-020 plan.md Decision 3).

Already in `phase-p3-p4-handoff.md`:

- A `make worker` on the same task queue during `make test` hangs `test_resume_signal`.
- The report preview for a TBD persona takes about 6 s, because the CQ-023 matches call the mock providers on every load.
- `freeze_version.py` duplicates `freeze_sent_version.py`.
- `pricing/panel/service.py` duplicates the scenario-input gathering in `pricing/scenarios/service.py`.
- The e2e specs mutate seed data with no `afterAll` reverts. CQ-016 AC6 and CQ-018 AC8 cannot be rerun without a reset.
- react-doctor scores are about 77–83, warnings only.
- CQ-016/CQ-025: the workspace header does not poll after the pipeline reaches a terminal stage (see AC6 above).

## Remaining

The human merges `phase-p3-p4` → `main`. Before that, confirm CI is green on the `phase-p3-p4` → `main` PR. Also, when no worker is active, run the P2 S1.6 local git cleanup (memory `p2-merge-to-main`).
