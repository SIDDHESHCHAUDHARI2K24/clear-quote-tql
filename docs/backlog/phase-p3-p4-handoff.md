# Phase P3 + P4: orchestrator handoff

Written 2026-09-25 at the end of the first orchestrator session. A new session reads this, then `docs/backlog/phase-p3-p4-plan.md`, then the item folders it touches.

## State

- The integration branch `phase-p3-p4` (origin) is at aefa278. Merged: PRs #3–#10, #12, #13, and #22 (CQ-019 post-merge minors).
- The alembic head is `c8869567cd57` (`quote_packages.lo_edited`).
- The P4 lane is complete: CQ-021–024.
- In P3, CQ-016–019 are done. Only CQ-020 remains.
- Kaneo: CQ-016–019 and CQ-021–024 are In Review with merge comments. CQ-020 is To Do.

## Open work, in order

1. **CQ-020 Letter PDF & send (wave 6).** Use Opus on slot 10. Inputs:
   - `render_package_letter(db, package, *, portal_url=None, letter_date=None) -> str` in `app.features.quotes.pdf.service`.
   - WeasyPrint. Pango is installed; on macOS set `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
   - `freeze_package_version` in `portal/reports/versions.py`.
   - `build_package_view_model` in `app.features.quotes.send.view_model`.
   - `compute_matches_for_package`.
   - H2: the email links to `/report/{token}`. The borrower must sign in; no account is created.

   Decisions it must take:
   - M3: a PUT on a sent package should copy it into a new draft, so sent packages stay frozen.
   - Deferred from CQ-024: "ask_other is the only type allowed after an Inquiry is answered by a new version".

   Carry these PR #22 review minors:
   - A failed Send-tab save can be silently dropped by a later successful save.
   - `_delete_quote_row` reports `recommendation_cleared=True` when the recommendation actually moved.
   - Log the "refill after the Builder deletes all quotes" Decision.
2. **Fix the backend test flake before the main PR (required, because CI must be green).**
   - `asyncpg InterfaceError: cannot perform operation: another operation is in progress` also happens in CI: the push run 36183565823 failed and the PR run 36183570634 passed, on the same commit eeb259a.
   - It also appears locally, as errors in the workflow and schema tests.
   - So it is a test-isolation bug, probably in `backend/conftest.py`'s session and savepoint fixture or in the Temporal test env sharing a connection. It is not just load.
   - Use Opus and systematic-debugging. Reproduce it with `pytest -p randomly` or repeated runs.
3. **Cross-item re-checks after CQ-020.**
   - CQ-022 AC1 end to end: the email link, then sign-in, then the report.
   - CQ-024 AC1 and AC6 on a truly sent package.
   - CQ-019 AC2 against a real send.
4. **Open the PR `phase-p3-p4` → `main` for the human to merge.**
   - Before that, run the full `make e2e` on slot 0.
   - Update the backlog README statuses.
   - Confirm CI is green.
5. **Remind the human about the P2 S1.6 local git cleanup** (memory `p2-merge-to-main`). Run it only when no worker is active.

## Follow-ups logged (not blocking)

- The backend tests flake under shared-Postgres load: asyncpg "another operation is in progress", plus workflow and schema test errors. The P5/P6 session uses the same Postgres. Rerunning passes.
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
