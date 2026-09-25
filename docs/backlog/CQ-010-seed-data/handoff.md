# CQ-010 — Handoffs

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

## Handoff 1 — 2026-09-25 — Claude agent (Phase A)

- **Branch / last commit:** `cq-010-seed-data` @ (see `git log -1` after the commit this handoff ships with)
- **Stage:** 5 Test / 7 Verify complete for Phase A scope; stage 8 Commit next.
- **Done:** Per the orchestrator's Phase A/B split (CQ-013 not merged into `phase-p0-p1` yet):
  - `backend/app/integrations/los/schemas.py`: additive `employment`/`liabilities`/`assets`/`co_borrower_dob` fields on `LoanFileDTO` (plan.md decision #4).
  - `backend/app/features/applications/service.py`: `import_from_los` (this item's owned service function), tested in `backend/app/features/applications/tests/test_service.py` (4 tests).
  - `seed/personas/p01..p10_*.yaml`: full raw-input + LOS 1003 payload per persona from `spec.md`'s table.
  - `seed/providers/*.yaml`: tax/rent/str/rate_sheet/listings (AC3's 5 named tables) + credit_reports/insurance_factors (extra, for full adapter coverage).
  - `seed/users.yaml` + `seed/loader.py::seed_users` (AC4).
  - `seed/loader.py`: `seed_providers`, `seed_persona` (client/application/property/LOS record creation, then `import_from_los` -> `run_and_persist`, one `activity_events` row per stage), `apply_send_fixture` (Decision D2 mechanism, implemented but not yet invoked -- see below), `seed_persona_documents`.
  - `seed/pricing_seam.py`: the clearly-marked seam onto CQ-013's pinned function names; `PRICING_AVAILABLE=False` today.
  - `seed/generators/background_applications.py` (AC5) and `seed/generators/documents.py` (AC6, MinIO watermarked PDF/PNG).
  - `seed/reset.py` + `Makefile`'s `demo-reset`/`test` targets. `time make demo-reset` = ~1.5-2.0s.
  - Full test suite: `seed/tests/*` (22 tests, 1 skipped) + `backend` (169 tests) all green; ruff/mypy clean for `backend` (make lint's scope) and for `seed` (self-check, not in make lint yet).
- **In progress:** Nothing half-finished within Phase A's scope. Phase B (below) is the open work.
- **Next 3 steps (Phase B, once CQ-013 merges into `phase-p0-p1`):**
  1. `git merge phase-p0-p1` into this branch; confirm `seed/pricing_seam.py`'s guessed `draft_default_quote_set(application_id, pricing_result, db)` signature against CQ-013's real one (log a `Decision:` if it moved) -- `PRICING_AVAILABLE` will then flip to `True` automatically.
  2. Re-run `pytest seed -q`: `test_persona_final_statuses_match_table` and `test_grace_and_luis_downstream_rows` (both already `PRICING_AVAILABLE`-aware) should pass against the full persona table with no test-file edits needed. If either fails, that's real Phase B work, not a test bug.
  3. Re-run `time make demo-reset`, confirm still under 60s with pricing now running for all 10 personas, and update `post-dev.md`'s AC1/AC2/AC7/AC8 rows from Partial/Deferred to Full.
- **Open questions / blockers:** None -- waiting on the orchestrator's signal that CQ-013 has merged, per the dispatch instructions ("If CQ-013 is not merged when Phase A is done, commit Phase A, report status, and wait for my message").
- **Verify state:** `make up` (if the shared stack is down) `&&` `uv run pytest backend seed -q` `&&` `time make demo-reset`.
