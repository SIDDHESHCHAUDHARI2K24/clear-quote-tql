# CQ-024 — Handoffs

Append one entry per handoff, newest at the bottom. A new session reads spec.md, plan.md, then the latest entry.

## Handoff 1 — 2026-09-25 10:05 — Sonnet 5 (worktree agent-a1097689c8704cb8c, slot 7)

- **Branch / last commit:** `cq-024-borrower-actions` @ `f2eafac` (pushed to origin; no PR opened yet)
- **Stage:** 6 Review done (one round: fixed a lock-ordering deadlock risk and an `AskOtherDialog`
  stale-message bug, both re-verified). **7 Verify** and **8 Commit** (PR + Kaneo) are what's left.
  This handoff exists only because the coordinator's context-budget rule (stop at ~350K) fired
  mid-session, not because of any known blocker.
- **Done:**
  - Backend: `backend/app/features/portal/actions/` (`schemas.py`, `service.py`, `router.py`,
    `templates.py`, `tests/`) — the full `move_forward`/`ask_other`/`ask_updated` rule set, row
    locking (package -> version -> application, matching `versions.py::freeze_package_version`'s
    order after the review fix), LO email, activity event, mock CRM event. Registered in
    `core/registry.py`.
  - `portal/reports/service.py` 404-message fix (missing vs. foreign token now identical) +
    regression test in `portal/reports/tests/test_router.py`.
  - `backend/scripts/freeze_sent_version.py` (dev freeze script; CQ-023's own equivalent isn't on
    this branch's base yet — see plan.md Decision 10).
  - `pyproject.toml` gained a `yaml.*` mypy override (script reads `seed/personas/*.yaml`).
  - `make api-client` regenerated (`packages/api-client/openapi.json`, `src/schema.d.ts`).
  - Frontend: `apps/borrower-portal/src/features/actions/` (`api.ts`, `MoveForwardDialog.tsx`,
    `AskOtherDialog.tsx` + tests) and a full rewrite of `ReportActionsSlot.tsx` (was a disabled
    "Coming soon" stub). `ReportView.tsx`'s `renderActions` closure now threads `token`/
    `borrowerAction`/`onActionTaken` through — no change to `ReportPage`'s own props interface
    (plan.md Decision 8).
  - E2E: `e2e/borrower-portal/report-expired-actions.spec.ts`, `move-forward.spec.ts`,
    `e2e/borrower-action-reflects-in-console.spec.ts` (new `cross-app` Playwright project in
    `playwright.config.ts`), and `report-expired.spec.ts` (CQ-022's own file) updated for the new
    expired-state button. All green against a real running stack (slot 7). Screenshots in
    `docs/backlog/CQ-024-borrower-actions/evidence/`.
  - `docs/backlog/CQ-024-borrower-actions/plan.md` and `post-dev.md` fully written, including the
    stage-6 review findings table. `docs/backlog/README.md`'s CQ-024 row set to "In Review".
  - Verified end to end against the real stack (not just tests): move_forward on Priya Nair's
    Buydown option (Marcus Hale has no Buydown candidate in his real priced data — see plan.md's
    Deviations), 409 on a second attempt, Grace Kim's expired report (`ask_updated` works,
    `move_forward` 409s), Mailpit received the correct LO emails, `activity_events`/`crm_events`/
    `outbox_emails` rows all correct.
  - `graphify update .` run (graph committed).
- **In progress:** Nothing half-finished in the code itself — the diff is complete and every check
  in `post-dev.md`'s Test log passed on this session's last run. What's *not* done is stage 7's
  formal acceptance write-up cross-check against `spec.md`'s AC list one more time fresh, and
  stage 8's PR + Kaneo update.
- **Next 3 steps:**
  1. Re-run the full verification sweep once more from a clean `make demo-reset` (backend:
     `uv run pytest backend seed -q`; frontend: `pnpm -r run test`; `make lint`; `react-doctor` on
     `apps/borrower-portal`) to confirm nothing drifted, then re-run the Playwright specs listed
     below (they were last green on this session's own run, but re-verify since a fresh session
     can't trust "it passed for someone else").
  2. `git fetch origin && git merge origin/phase-p3-p4` (per the coordinator's own instructions),
     resolve any conflicts (unlikely — this item's owned files are narrow), then
     `gh pr create --base phase-p3-p4 --head cq-024-borrower-actions --title "CQ-024: ..." --body
     "..."` (title prefixed `CQ-024:`, body ending with the Claude Code attribution line per the
     system reminder in scope).
  3. Post a Kaneo comment on task `ecrqlza5ruvr2uub5ct2xhck` with the PR link and the post-dev.md
     summary, then move it to `in-review` (it's currently `In Progress`).
- **Open questions / blockers:** None blocking. Two logged deviations worth a second look if a
  reviewer disagrees: (1) the E2E move-forward spec uses Priya Nair instead of Marcus Hale (his
  real priced data has no Buydown option — see plan.md's Deviations table for the live-verified
  root cause); (2) AC6's "shows the new status after its next poll" is demonstrated via a
  re-navigation rather than a literal 3s-interval poll, since `WorkspaceProvider` (CQ-016) stops
  its poll once the pipeline stage is terminal — logged as a CQ-016/CQ-025 follow-up, not a gap in
  this item's own scope.
- **Verify state:**
  ```
  source scripts/worktree-env.sh 7   # or reuse this worktree's existing .env (already slot 7)
  uv run alembic upgrade head && make demo-reset
  uv run uvicorn app.main:app --app-dir backend --port 8107 &      # restart after any demo-reset
  pnpm --filter @cq/borrower-portal exec next dev -p 3207 &
  pnpm --filter @cq/lo-console exec next dev -p 3107 &
  uv run pytest backend seed -q && make lint
  pnpm exec playwright test e2e/borrower-portal --project=borrower-portal --workers=1
  pnpm exec playwright test e2e/borrower-action-reflects-in-console.spec.ts --project=cross-app --workers=1
  ```
  (needs `SEED_STAFF_PASSWORD`/`SEED_BORROWER_PASSWORD`/`DATABASE_URL`/`LO_BASE_URL`/
  `PORTAL_BASE_URL` set — see this worktree's `.env` and `post-dev.md`'s "How to test manually".)
