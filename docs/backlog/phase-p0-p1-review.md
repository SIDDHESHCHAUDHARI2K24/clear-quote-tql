# G4 whole-phase integration review — `main...phase-p0-p1` (CQ-001…CQ-013)

Reviewed in a throwaway worktree (`.worktrees/g4-review`, detached at `phase-p0-p1` = `fe15d93`), removed at the end. Did not write, merge, or push anything. CI clean-up pass (cq-006-ci branch: compose/Makefile `up`, `.github/`) excluded per scope.

## Commands run (pass/fail)

| Command | Result |
| --- | --- |
| `git worktree add .worktrees/g4-review phase-p0-p1 --detach` | Pass |
| `uv sync` | Pass |
| `pnpm install` | Pass (480 packages) |
| `cp .env.example .env` + generated `FIELD_ENCRYPTION_KEY`, set `SEED_STAFF_PASSWORD` | Pass |
| `make lint` (ruff, ruff format, mypy, eslint ×4, tsc ×4, prettier) | **Pass** |
| `make test` (backend 247, seed 23, frontend 27+1+4+4) | **Pass** |
| `uv run pytest backend -q` ×3 consecutive runs | **Pass** — 247/247/247, no flakes, no random-order plugin available (`pytest-randomly`/`pytest-reverse` not installed) so re-ran the fixed order three times instead |
| Scratch DB `cq_g4review`: `alembic upgrade head` → `alembic check` → `alembic downgrade base` → `alembic upgrade head` → `alembic check` | **Pass** — clean round-trip both ways, "No new upgrade operations detected" both times |
| `make api-client` (diff check) | **FAIL** — see Finding #1 |
| `git checkout -- packages/api-client/` (revert the diff produced above) | done, worktree left clean |
| `time make demo-reset` | **Pass** — 1.3s; all 10 personas at spec's exact end status (6× `priced`, `aisha_coleman`/`ben_ford` → `needs_attention`, `grace_kim` → `sent`, `luis_romero` → `option_selected`); 200 background applications |
| `git log --merges --oneline \| grep cq-0` | **Pass** — merge commits present for CQ-001…CQ-013 (G1) |
| `git merge-base --is-ancestor origin/main HEAD` | **Pass** (G7 — main hasn't moved) |
| `git grep` for AKIA/private-key/`sk-`/api_key/password literals; `git ls-files` for `.env`/`.pem`/`.key`/credentials | **Pass** — none tracked in the working tree (G8) |
| `git log phase-p0-p1 -p -- seed/users.yaml` (history scan) | **FAIL-ish** — see Finding #2 |
| `grep -rn "float("` in `backend/app` outside tests | **Pass** — no hits |
| `grep -rn "parseFloat\|parseInt\|Number("` in `apps/`, `packages/ui/src`, `packages/api-client/src` outside tests | **Pass** — no hits (frontends never compute money) |
| `grep -rniE` for real provider domains/SDKs/`requests.`/`httpx.` in `backend/app/integrations/` | **Pass** — none; every adapter only touches its own `provider_*`/`crm_events` table |
| Router auth-dependency sweep (`grep -L "get_current_lo_stub"` over all `router.py`) | Informational — see Finding #4 (expected/tracked) |
| SSN handling: grepped `.ssn`/`ssn_encrypted` usage, `RuleResult` messages, logging calls in `verification/` | **Pass** — SSN decrypted only in-process for rule evaluation, never logged, never in a `RuleResult.message`, never returned by any router |
| `backend/app/core/errors.py` unhandled-exception handler | **Pass** — generic `{"code":"INTERNAL_ERROR","message":"Internal server error"}`, no exception text/stack leaked |
| `grep -rn "\.occupancy\b"` across `backend/app` (nullable-occupancy consumer sweep) | **Pass**, with one already-tracked exception — see Finding #5 |
| Test-quality spot check: zero-assert test files, `assert True` literals | **Pass** — none found |

## Findings

| # | Severity | file:line | Finding | Suggested fix | Owning item |
| --- | --- | --- | --- | --- | --- |
| 1 | **major** | `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`; introduced by `backend/app/features/applications/router.py` (pipeline routes) | `make api-client` is **not** a no-op on `phase-p0-p1` HEAD — running it adds `POST /api/v1/applications/{application_id}/pipeline/start` and `.../pipeline/resume` (with their `operationId`s) to `openapi.json`/`schema.d.ts`. CQ-011 added these two live endpoints (`router.py`) but its post-dev.md never records running `make api-client`, and its own review's command table omits it too — CQ-013 (the last item to touch this file) is the last one that verified a clean diff, before CQ-011 landed its endpoints. This means the committed `packages/api-client` is stale for anything CQ-016+ needs to call the pipeline endpoints from a frontend, and it fails G5's literal exit check ("`make api-client` produces no diff") today, not hypothetically — reproduced live in this review. | Run `make api-client` on `phase-p0-p1` (or in a small follow-up branch) and commit the regenerated `openapi.json`/`schema.d.ts` before G5/merge. | CQ-011 (fix), blocks G5 |
| 2 | **major** | `seed/users.yaml` history: commits `ea72560`, `a036651` (both reachable from `phase-p0-p1` via `git log phase-p0-p1 -- seed/users.yaml`) | The plaintext demo password `ClearQuoteDemo!2026` isn't just in the standalone public `cq-010-seed-data` branch (as the merge plan's "Known follow-ups" section frames it) — those two commits are ancestors of `phase-p0-p1` itself (the CQ-010 merge was a real, non-squash merge, so its full commit history rode along). The merge plan's Execution step 2 is `gh pr merge 1 --merge` (merge commit, keeps per-item history) — that will carry `ea72560`/`a036651` into `main`'s own reachable history permanently, not just leave them stranded on a side branch. Working tree/HEAD are clean (confirmed: `git grep ClearQuoteDemo` on HEAD is empty), so this is a history-only exposure, but it is now inside the exact history the merge plan intends to publish to `main`. | Before merging PR #1, human decision: either accept the exposure (throwaway demo password, no other use, already disclosed in CQ-010's own post-dev) and update the merge-plan wording to reflect that it *will* reach `main`'s history, not just stay on a side branch — or rewrite/squash `phase-p0-p1`'s history for the CQ-010 range before the PR merge. Do not reuse `ClearQuoteDemo!2026` as a real credential anywhere. | Human call (G8), CQ-010 origin |
| 3 | minor (carried forward, unresolved) | `backend/app/workflows/worker.py:31-55` vs `alembic/env.py:17-41` | Already flagged by CQ-011's own review (finding #1, informational): the "import every model module" list is hand-duplicated in two files with nothing enforcing they stay in sync. Still true at HEAD — confirmed no shared `model_registry` module exists and no test diffs the two lists. Not blocking, but worth closing before more feature modules land. | Extract to one shared `app.core.model_registry` list both files import, or add a test asserting the two import-line sets are equal. | CQ-011 follow-up (untouched) |
| 4 | informational (expected) | `backend/app/features/applications/router.py` (pipeline `start`/`resume`), `backend/app/features/system/router.py` (`/health`) | No auth dependency on these routes. Confirmed intentional and already documented (CQ-011 post-dev finding #4, CQ-004/system spec): no staff auth exists until CQ-014. All pricing/enrichment routers do have `get_current_lo_stub`. Listed per the review brief's instruction to enumerate unauthenticated routes, not a new defect. | CQ-014 should add the same auth dependency to the two pipeline routes once it lands. | CQ-014 (future) |
| 5 | minor (carried forward, unresolved) | `backend/app/features/applications/verification/service.py:170-173` | Already flagged by CQ-010's round-2 review (finding #4, left as-is by orchestrator): `reserves_key = "reserves_months_primary" if application.occupancy is Occupancy.PRIMARY else "reserves_months_investment"` treats a `None` occupancy (Aisha Coleman, persona 7) as investment via the catch-all `else`, unlike every other `.occupancy` consumer in the codebase (`pricing/scenarios/service.py:125` `_strategy_type`, `ob_request.py:99/111/113`, `enrichment/service.py:235/275`), all of which explicitly test `is Occupancy.INVESTMENT`/`is Occupancy.PRIMARY` and either raise or take the correct branch on `None`. Harmless today only because Aisha is in fact an investment persona. Re-verified still present and still the only occupancy-consumer with this asymmetry. | Change to `"reserves_months_investment" if application.occupancy is Occupancy.INVESTMENT else "reserves_months_primary"`. | CQ-012/CQ-010 (untouched follow-up) |
| 6 | nit | n/a | `pytest-randomly`/`pytest-reverse` are not installed in this environment, so true order-randomized flake detection wasn't possible; substituted 3 consecutive same-order full-suite runs (247/247/247, identical). No flakiness observed, but a true randomized run is stronger evidence and cheap to add (`uv add --dev pytest-randomly`). | Add `pytest-randomly` as a dev dependency for future CI/review runs. | CQ-006/CI (future) |

No critical findings. Everything else re-verified in this review (AGENTS.md money-math rule, mocks-only rule, primary-loan field suppression at both the engine and API-schema level, SSN handling, error-handler leakage, G1/G7/G8 mechanics, alembic round-trip, demo-reset personas, full lint/test suite) checks out clean and matches what the 13 items' own post-dev.md fresh-reviewer sections already documented.

## Verdict

**FAIL** — two major findings (stale `packages/api-client` after CQ-011's pipeline endpoints; plaintext demo password reachable in `phase-p0-p1`'s own git history, not just a side branch as previously believed). Neither is a deep design problem — both are quick to close (regenerate api-client and commit; human decision + optional history rewrite for the password) — but both are real, newly-confirmed gaps this whole-phase pass was specifically meant to catch, and G5's literal `make api-client` exit check fails today.
