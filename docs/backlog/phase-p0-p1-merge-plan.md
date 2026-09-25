# Merge plan: `phase-p0-p1` → `main` (PR #1)

Approved by the human on 2026-09-25: the orchestrator merges PR #1 once Phase 0 and Phase 1 are fully complete and every gate below passes. Phase 2 (CQ-014+) is built in a separate session on its own branches and is **not** part of this merge.

## Scope

Only CQ-001 … CQ-013 plus the CI clean-up pass. Nothing from `phase-p2` or any `cq-014+` branch.

## Gates (all must pass, in order)

| # | Gate | How it is checked |
| --- | --- | --- |
| G1 | All 13 items merged into `phase-p0-p1` | `git log phase-p0-p1` has a merge commit for each of `cq-001` … `cq-013` |
| G2 | Every item reviewed | Each `post-dev.md` has a fresh-reviewer section with no open critical/major finding; acceptance checklist filled with evidence |
| G3 | CI clean-up pass merged | CQ-003: `minio-init` no longer an artificial `depends_on` of `temporal-ui`. CQ-006: AC2 evidence updated; actions bumped off Node-20 majors; run has no deprecation annotations |
| G4 | Whole-phase integration review | One fresh subagent reviews `main...phase-p0-p1` as a whole: cross-item contracts, spec conformance, AGENTS.md rules (Decimal money only in `quote_engine`, mocks only, primary loans hide investment fields), secrets. No open critical/major |
| G5 | Clean-checkout verification | In a fresh clone of `phase-p0-p1`: `make up`, `make lint`, `make test`, `alembic upgrade head` → `downgrade base` → `upgrade head`, `make api-client` produces no diff, `make demo-reset` under 60 s with every persona in its expected status. Output recorded below |
| G6 | CI green | Latest push run on `phase-p0-p1` and PR #1 checks green |
| G7 | `main` has not moved | `git merge-base --is-ancestor origin/main phase-p0-p1`. If `main` moved (for example Phase 2 merged first), merge `origin/main` into `phase-p0-p1`, resolve, and rerun G5–G6 |
| G8 | Secrets scan | No `.env`, keys, tokens or plaintext passwords tracked (`git ls-files`, `git grep` patterns) |

## Execution

1. Update the PR #1 description: final item list, review outcomes, known follow-ups, verification evidence.
2. `gh pr merge 1 --merge` (merge commit, keeps per-item history). Do not delete `phase-p0-p1`.
3. Watch the CI run on `main`; record its id and result. This is CQ-006's exit check ("CI green on main").
4. Kaneo: comment the merge commit on CQ-001 … CQ-013. Tasks stay **In Review**; only the human moves them to Done.
5. Tell the human that `main` changed so the Phase 2 session can merge `main` into `phase-p2`.

## If CI fails on `main`

Fix forward on a new branch from `main`, review, and merge through a PR. A revert (`git revert -m 1 <merge>`) only with the human's approval.

## Known follow-ups carried past the merge (not blockers)

- CQ-005: Overlay focus trap, Escape test, Tabs arrow-key navigation.
- CQ-005/CQ-004: declare the 503 response on `/health` in the OpenAPI schema.
- CQ-009: property-match ranking is a price proxy until CQ-023.
- CQ-013: scenarios snapshot `ConfigSnapshot()` defaults, not the `settings` table (no loader yet); HOA is always $0 until a source exists.

## Verification record

Filled in at merge time.
