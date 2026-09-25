# Phase P3 + P4: orchestrator handoff

Written 2026-09-25 at the end of the first orchestrator session. A new session reads this, then `docs/backlog/phase-p3-p4-plan.md`, then the item folders it touches.

## State

The integration branch `phase-p3-p4` (origin) is at 826c7f2. Merged into it:

| PR | Unit |
| --- | --- |
| #3 | P3/P4 foundation |
| #4 | CQ-021 report components |
| #5 | CQ-016 workspace |
| #6 | CQ-022 borrower report |
| #7 | CQ-023 matches |
| #8 | CQ-024 borrower actions |
| #9 | CQ-017 pricing panel |
| #10 | Property-tax units fix |
| #12 | CQ-018 quote builder |
| #13 | CQ-019 send tab |

- The alembic head is `5bd9d8620699`.
- `make lint` is green. `make test` is green on a clean run (backend 521, seed 31, frontend 365).
- The P4 lane is complete. For P3, only CQ-020 is left.
- The Kaneo tasks for CQ-016–019 and CQ-021–024 are In Review with merge comments. CQ-020 is To Do.

## Open work, in order

1. **Finish the CQ-019 post-merge minors.**
   - The work is on branch `cq-019-review-minors`, WIP commit 909eebc, pushed with no PR. The Sonnet worker crashed before it could verify anything, so this code is untested.
   - Scope: M1, M2 and M4–M10 from the PR #13 review. The list is in the worker prompt; the review is summarised in `docs/backlog/CQ-019-send-tab/post-dev.md` once the section is written.
     - M1: serialize Send-tab saves.
     - M2: GET re-draft without the lock.
     - M4: recommendation consistency on delete, plus a `default_draft` event.
     - M5: an empty draft gets its default.
     - M6: a `strategy_missing` blocker.
     - M7: FICO parsing.
     - M8: letter escaping and CSP tests.
     - M9: the checklist lists only received documents.
     - M10: the e2e spec restores Sam Reed.
     - Nits: docstrings, one shared 5-year PPP constant, `_ASSET_FLOOR_STEP` order.
   - M3 (a sent package is still editable) is deliberately left for CQ-020.
   - Next step: a fresh Sonnet worker checks out the branch, runs `make lint` and `make test` on slot 9, fixes the failures, writes the post-dev section, runs the code-review skill, opens a PR to `phase-p3-p4`, and gets a quick fresh review before the merge.
2. **CQ-020 Letter PDF & send (wave 6).** Use Opus, on slot 10. Inputs:
   - `render_package_letter(db, package, *, portal_url=None, letter_date=None) -> str` in `app.features.quotes.pdf.service`.
   - WeasyPrint. Pango is installed; on macOS it needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
   - `freeze_package_version` in `portal/reports/versions.py`.
   - `build_package_view_model` in `app.features.quotes.send.view_model`.
   - `compute_matches_for_package`.
   - H2: the email links to `/report/{token}`. The borrower must sign in, and no account is created.
   - Decide M3: PUT on a sent package copies it into a new draft.
   - The spec line deferred from CQ-024: "ask_other is the only type allowed after an Inquiry is answered by a new version".
3. **Cross-item re-checks after CQ-020.** CQ-022 AC1 end to end (email link, sign in, report). CQ-024 AC1 and AC6 on a truly sent package. CQ-019 AC2 against a real send.
4. **Open PR `phase-p3-p4` → `main` for the human to merge.** Before opening it, run the full `make e2e` on slot 0 and update the backlog README statuses.
5. **Remind the human about the P2 S1.6 local git cleanup** (memory `p2-merge-to-main`). It should run only when no worker is active.

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
