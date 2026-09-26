# Phase P3 + P4: orchestrator handoff

First written 2026-09-25 at the end of the first orchestrator session. Updated 2026-09-25 by the final-verification run (`docs/backlog/phase-p3-p4-verification.md`).

## State

- **All P3 and P4 items (CQ-016 to CQ-024) are merged into `phase-p3-p4`.** The last merge was PR #30, CQ-020 (a39ab90). The backend test-flake fix is PR #28 (`docs/backlog/p34-test-flake-fix.md`). CQ-019's post-merge minors are PR #22.
- The alembic head is `d4a1c0f2e920` (CQ-020 send tracking). There is exactly one head.
- Final verification ran on slot 0 and is recorded in `docs/backlog/phase-p3-p4-verification.md` (PR "P3/P4 final verification" → `phase-p3-p4`).
  - `make lint` and `make test` are green, and `make demo-reset` takes about 2 s.
  - `make e2e` passes 51/51 with `--workers 1`. Parallel runs flake on shared seed data.
  - The real-send re-checks pass: CQ-022 AC1, CQ-024 AC1 and AC6, CQ-019 AC2, and the P4 milestone.
- Kaneo: CQ-016 to CQ-019 and CQ-021 to CQ-024 are In Review. CQ-020 is moved to In Review by the orchestrator at its merge; the verification run did not change Kaneo.

## Open work, in order

1. Merge the "P3/P4 final verification" PR into `phase-p3-p4`.
2. **The human** opens and merges the PR `phase-p3-p4` → `main`, after confirming CI is green on it.
3. Remind the human about the P2 S1.6 local git cleanup (memory `p2-merge-to-main`). Run it only when no worker is active.

The non-blocking follow-ups are listed in `phase-p3-p4-verification.md` (Follow-ups) and below.

## Follow-ups logged (not blocking)

- A `make worker` running on the same task queue during `make test` hangs `test_resume_signal`. Stop workers before running tests.
- A TBD persona's report preview takes about 6 s, because the CQ-023 matches call the mock providers with latency on every load.
- `backend/scripts/freeze_version.py` and `freeze_sent_version.py` duplicate each other. `freeze_version.py` should use `new_default_package`.
- `pricing/panel/service.py` still duplicates the scenario-input gathering in `pricing/scenarios/service.py`.
- The e2e specs mutate seed data without `afterAll` reverts; CQ-018 has an authenticated API helper for this.
- react-doctor scores are about 77–83, warnings only.

## Rules in force (human)

- Opus 5.5 for medium or high complexity work and for reviews of feature PRs. Sonnet 5 for small fix rounds. Never Haiku.
- No subagent above 400K context. Hand off at about 350K. Never resume a worker that has handed off; send fixes to a fresh worker, and batch the review findings.
- One PR per item into `phase-p3-p4`. The orchestrator merges only after a fresh-subagent review approves.
- Per-worktree slots come from `scripts/worktree-env.sh <N>`. Slots 0–11 belong to this lane. P5/P6 run in another session; never touch their branches, worktrees or Kaneo tasks (CQ-025–034).
- The seeded LO login is `jordan.lee@clearquote-demo.test`. Passwords are in each slot's `.env` (`SEED_*`).
