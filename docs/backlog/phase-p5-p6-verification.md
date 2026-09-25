# Phase P5/P6 verification

Status: **in progress, handed off** (see Handoff section at the bottom). This
session did not reach two clean official full-suite runs; do not read
section (a) below as final.

## (a) Suite results

Setup used: slot 28 (API 8128, LO 3128, portal 3228), branch
`p56-phase-verification` off `origin/phase-p5-p6`.

### Fixes landed this session (before the two official runs)

1. **`e2e/borrower-portal/shell.spec.ts`** — the stale stub-era assertions
   (task 1) were replaced: `/support` now asserts the real `h1` "Get in
   touch" (matches `support.spec.ts`); `/apply` still asserts `h1` "Apply"
   (unchanged, still correct); `/tasks/credit-check/{unknown-uuid}` now
   asserts `h1` "Request not found" (`ConsentStates.tsx`'s `ConsentNotFound`,
   since an all-zero UUID 404s) instead of the old "Credit check"/"Built in
   CQ-033" stub text.
2. **`e2e/borrower-portal/portal-home.spec.ts:166`** — same stale-stub class
   of bug, found while checking the other borrower-portal specs: asserted
   `h1` "Credit check" for a *real, pending* consent; the real page
   (`ConsentForm.tsx`) renders "Authorize a credit check". Fixed.
3. **`e2e/helpers/db.ts`** — added `queryRows()`, a typed read-query export
   over the existing `pg` pool (alongside `execSql`'s write-only
   `psql -tAc`), for the P5 milestone spec's independent SQL recomputation
   of the dashboard tile counts.
4. **`playwright.config.ts`** — the `cross-app` project's `testMatch` was a
   single hardcoded filename; widened to also match `cross-app/*.spec.ts`
   so the two new milestone specs run.
5. **`e2e/cross-app/p5-milestone.spec.ts`** (new) — Manager dashboard tiles
   vs. SQL-computed counts, then an LO resolves Aisha Coleman's
   missing-occupancy flag and she reaches Priced and leaves "Needs your
   attention" (restored in `afterAll`).
6. **`e2e/cross-app/p6-milestone.spec.ts`** (new) — a new borrower signs up
   (Mailpit OTP), completes the apply wizard, submits, reaches Intake, and
   auto-prices with no LO action; the LO console (a second browser context,
   signed in as the Manager) shows the same application Priced.
7. **`backend/scripts/restart_pipeline.py`** (new, test-only) — see finding
   below; used only by `p5-milestone.spec.ts`.

### Real finding: two "real Temporal resume" specs can't share one demo-reset

`e2e/lo-console/aisha-occupancy-resume.spec.ts` (CQ-028 AC1, existing) and
the new `p5-milestone.spec.ts` both resolve Aisha Coleman's real
missing-occupancy flag through the real UI and a real Temporal run. Within
one full-suite pass (one `make demo-reset`), `lo-console` runs before
`cross-app`, so by the time `p5-milestone.spec.ts` reaches her,
`aisha-occupancy-resume.spec.ts` has already consumed her one Temporal
workflow run for this demo-reset cycle.

`backend/app/features/applications/sections/reverify.py::_plan_resume`
deliberately never restarts a *completed* run ("A completed (priced) run is
never repeated" — review minor 6; only failed/terminated/cancelled/timed-out
runs restart, via `ALLOW_DUPLICATE_FAILED_ONLY`). SQL can restore the
`applications`/`flags` rows to look freshly seeded, but not the spent
Temporal workflow: a second real resume attempt returns a different,
silent `"workflow_closed"` outcome (no toast, no re-price) — this is
correct, intentional app behaviour, not a bug.

Fix (test-only, in `p5-milestone.spec.ts`): `cleanupAishasPipelineArtifacts`
resets her DB rows (as `aisha-occupancy-resume.spec.ts`'s own `afterAll`
does, plus removes any `scenarios`/`quotes`/extra flags her first run left)
and `backend/scripts/restart_pipeline.py` (new) force-starts a **fresh**
Temporal run for her (`WorkflowIDReusePolicy.ALLOW_DUPLICATE`, broader than
the app's own policy) before the real UI edit, so the spec's own resume is
always a true first resume regardless of what already ran earlier in the
same suite pass. Verified in isolation: `e2e/cross-app/p5-milestone.spec.ts`
alone passes in ~17s after this fix.

### Runs

| Run | Scope | Result | Notes |
| --- | --- | --- | --- |
| 1 | Full suite (`--workers=1`, all 3 projects), fresh `make demo-reset` | 67 passed, 1 failed, 3 did not run (62 lo-console+borrower-portal+cross-app specs plus the 2 new milestones = 68 total attempted) | The one failure was `p5-milestone.spec.ts` — the two-Temporal-resume conflict above, root-caused and fixed *after* this run. Not re-run as a full pass yet (see Handoff). Every other spec, including the shell.spec.ts and portal-home.spec.ts fixes, passed clean in this run. |
| 2 | Full suite | **not started** | Blocked on re-running run 1 in full with the p5-milestone fix in place first. |

Evidence screenshots: `docs/backlog/evidence/p56-phase/` —
`p5-milestone-dashboard.png`, `p5-milestone-aisha-priced.png`,
`p5-milestone-dashboard-after.png` (from the passing isolated re-run),
`p6-milestone-borrower-intake.png`, `p6-milestone-borrower-priced.png`,
`p6-milestone-lo-console-priced.png` (from run 1, which p6-milestone
passed).

## (b) `make demo-reset` timing

Timed 3 times on slot 28 this session: **1.9s**, **1.3s**, **1.2s**
(`=== done in ===` line; wall time including `uv run` startup was ~2–9s).
Well under the 60s budget.

## (c) H2 "pending P3 re-check" list

**Not compiled this session** — the `grep -rn "pending" docs/backlog/CQ-02*/post-dev.md docs/backlog/CQ-03*/post-dev.md`
pass was not run before handoff. Known entries from the coordinator's brief
(still to be individually verified against each post-dev.md and marked
resolved/outstanding):

- CQ-030 AC5: CQ-018 reprice must call `clear_stale(fresh_quote_ids=…)`.
- CQ-029 AC2: the PDF from CQ-020.
- The E2 clock follow-up: pricing and send must use `core/clock.now()`.
- CQ-017 stale-marker reconciliation and `/field-values` re-verify.
- Workspace route-group move for P3 files.

## (d) Consolidated follow-up backlog

**Not compiled this session** — the pass collecting every "Follow-ups"
item across the 10 post-dev.md files and the hardening notes
(`phase-p5-p6-e2e-cleanup.md`, `phase-p5-p6-foundation.md`) was not run.
Known minors already documented in `phase-p5-p6-e2e-cleanup.md` (reviewers
accepted): `lock_application_quotes` FOR NO KEY UPDATE, `mark_stale` step-1
ordering, the `useSection` refetch bridge, the shared `send_email`
SMTP-before-commit pattern, the duplicated metros endpoints, metro names
not being state-qualified.

## (e) `make lint` / `make test` / `graphify update .`

**Not run this session.**

---

## Handoff

### Handoff 1 — 2026-09-25 (time not tracked) — Claude (Opus 5.5, P56-verify)

- **Branch / last commit:** `p56-phase-verification` @ (see next commit,
  prefixed `P56-verify: wip:`, made right after this doc)
- **Stage:** 5 Test (mid full-suite verification, tasks 1–2 done, task 3
  partially done, tasks 4–6 not started)
- **Done:**
  - Task 1: fixed the stale `shell.spec.ts` assertions (`/support`,
    `/apply`, `/tasks/credit-check/[id]`), plus one more stale assertion
    found in `portal-home.spec.ts:166`.
  - Task 2: added `e2e/cross-app/p5-milestone.spec.ts` and
    `e2e/cross-app/p6-milestone.spec.ts`; wired `playwright.config.ts`'s
    `cross-app` project to pick them up; added `queryRows()` to
    `e2e/helpers/db.ts`.
  - Task 3: ran the full suite once (see "Runs" table, row 1: 67/68,
    1 failure). Root-caused and fixed that one failure (the two-Temporal-
    resume conflict, `backend/scripts/restart_pipeline.py` + the
    `cleanupAishasPipelineArtifacts`/`restartAishasPipeline` helpers in
    `p5-milestone.spec.ts`). Verified the fix by running
    `e2e/cross-app/p5-milestone.spec.ts` alone (passed, ~17s). **Have not
    yet re-run the full suite end to end with the fix in place** — that is
    officially "run 1" once it's green, then a second fresh-demo-reset run
    is still needed for "run 2".
  - Task 4: timed `make demo-reset` 3×: 1.9s, 1.3s, 1.2s. Well under 60s.
  - Caught and fixed a live-infra issue mid-session (not a task item): the
    slot-28 Temporal worker died once (`Error 143`/SIGTERM) from being
    started with a plain `&`+`nohup` instead of the harness's
    `run_in_background`; restarted it (and API/both Next apps) via
    `run_in_background` this time, which held up for the rest of the
    session.
- **In progress:** Task 3 (full-suite runs). Nothing is mid-edit in any
  spec file — the fix landed cleanly and was verified standalone. What's
  left is purely *running* things, not further code changes.
- **Next 3 steps:**
  1. Bring slot 28 back up (see "Verify state" below), then run the full
     suite once (`pnpm exec playwright test --workers=1 --reporter=line`).
     Expect all 68 specs green now (67 passed + the now-fixed
     `p5-milestone.spec.ts`). If green, that's official run 1 — save its
     counts into the "Runs" table above (replace row 1) and take fresh
     screenshots into `docs/backlog/evidence/p56-phase/` if any are stale.
  2. Fresh `make demo-reset` + API/worker restart, run the full suite a
     second time (`--workers=1`). Record as run 2 in the table. Both runs
     must be fully green per the task brief — if either isn't, diagnose
     per the usual "real app bug vs. test leak" split and fix or record.
  3. Do tasks 5(c)/5(d) (the `grep -rn "pending"` pass across
     `docs/backlog/CQ-02*/post-dev.md` and `CQ-03*/post-dev.md`, and the
     consolidated follow-up backlog across all 10 post-dev.md files plus
     the hardening notes) and task 6 (`make lint && make test`,
     `graphify update .`), then finish the PR per the original brief
     (base `phase-p5-p6`, title "P5/P6: phase verification, milestone
     specs, follow-up backlog").
- **Open questions / blockers:** none technical — everything left is
  execution (run the suite twice, do the two grep/compile passes, run
  lint/test). The Aisha two-Temporal-resume root cause is understood and
  fixed; no further investigation needed there.
- **Verify state:**
  ```bash
  cd <repo> && git fetch origin && git switch p56-phase-verification
  # confirm nothing else is on slot 28's ports first:
  lsof -iTCP:8128,3128,3228 -sTCP:LISTEN -n -P
  bash scripts/worktree-env.sh 28   # re-derives .env, apps/*/.env.local
  make demo-reset                    # expect well under 60s
  # start API, worker, both apps (repo root, each via a persistent
  # background launcher, not a plain `&` — see the worker-death note
  # above):
  PORTAL_BASE_URL=http://localhost:3228 uv run uvicorn app.main:app --app-dir backend --port 8128
  make worker
  pnpm --filter @cq/lo-console exec next dev -p 3128
  pnpm --filter @cq/borrower-portal exec next dev -p 3228
  # then, from repo root:
  LO_BASE_URL=http://localhost:3128 PORTAL_BASE_URL=http://localhost:3228 \
    SEED_STAFF_PASSWORD=<from .env> SEED_BORROWER_PASSWORD=<from .env> \
    DATABASE_URL=<from .env> \
    pnpm exec playwright test --workers=1 --reporter=line
  ```
