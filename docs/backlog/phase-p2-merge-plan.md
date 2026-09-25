# Merge plan: `phase-p2` → `main`

The human approved this plan on 2026-09-25. Phase 2 (CQ-014 Staff auth, CQ-015 Borrower auth) is complete on the local branch `phase-p2`, and both items are In Review in Kaneo. Phase 1 (`phase-p0-p1`, PR #1) is being merged to `main` by the other session. This plan starts only once that merge has landed.

A new session runs this plan as orchestrator. It follows `AGENTS.md`: the orchestrator plans, dispatches and reviews, Sonnet subagents write code, and conventional commits are prefixed with their item id. Integration work uses the prefix `P2-merge:`.

## Human decisions (2026-09-25)

| # | Decision |
| --- | --- |
| H1 | Wait for PR #1. The first gate checks that `origin/main` contains `phase-p0-p1`. If it does not, stop and ask. |
| H2 | **Rewrite P2 history before anything is pushed.** Commit `64ee14a` added a demo password in plain text to `.env.example` (`DEMO_STAFF_PASSWORD` / `DEMO_BORROWER_PASSWORD`), and it is still in the tip. `phase-p2` has never been pushed. Remove the value from every P2 commit so it never reaches GitHub, and adopt P1's policy: no password is ever committed; the seed passwords are blank env vars. |
| H3 | **Wire real staff auth into P1's routes during this merge.** Replace CQ-013's `get_current_lo_stub` (fixed `DEV_LO_ID`) with `CurrentStaff` plus LO scoping, put staff auth on CQ-011's pipeline endpoints, and remove `DEV_LO_ID`. |
| H4 | Merge style is the same as PR #1: a PR from `phase-p2` to `main`, merged with `gh pr merge --merge` so per-item history survives. Kaneo tasks stay In Review; only the human moves them to Done. |

## Current state

- `phase-p2` is checked out at `.worktrees/phase-p2`, which has its own gitignored `.env`. It contains 17 commits over `5e9fcc7`, CQ-014 merged at `f0da258` and CQ-015 at `4d92687`, and a green `make lint` / `make test` (177 backend tests, 124 frontend).
- Item worktrees `.worktrees/cq-014-staff-auth` and `.worktrees/cq-015-borrower-auth` are finished.
- The P2 isolation `.env` uses `cq_dev_p2` / `cq_test_p2`, Valkey db 2 (tests db 3) and API port 8012. Once P1 is merged the isolation is no longer needed, but it is harmless.
- `git merge-tree phase-p2 phase-p0-p1` (as of `4cf9c01`) shows content conflicts in `.env.example`, `backend/app/core/config.py`, `backend/app/core/registry.py`, `backend/conftest.py` and `docs/backlog/README.md`. `packages/api-client/*` auto-merges but must be regenerated. `.github/workflows/ci.yml` auto-merges and must be checked by eye.

## Integration issues found while planning

| # | Issue | Why it matters |
| --- | --- | --- |
| X1 | `seed/loader.py::seed_users` hashes staff passwords with **bcrypt**. P2's `core/security.verify_password` uses **argon2** and returns False for other hashes. | After the merge, no seeded persona LO (e.g. `jordan.lee@clearquote-demo.test`) could log in. |
| X2 | There are two seed-password schemes: P1's `SEED_STAFF_PASSWORD` (blank, required by `make demo-reset`) and P2's `DEMO_STAFF_PASSWORD` / `DEMO_BORROWER_PASSWORD` (committed values). | Keep one. H2 says P1's scheme wins. |
| X3 | There are two staff seed paths: `seed/users.yaml` via `make demo-reset` (2 LO, 1 Manager, 1 Admin at `@clearquote-demo.test`, Jordan Lee pinned to `…0001`) and P2's `backend/scripts/seed_dev_users.py` (`lo@` / `manager@` / `admin@clearquote.test` plus borrower Casey Morgan). | Two sets of demo users confuse the demo. |
| X4 | Persona clients get no `borrower_accounts` from `make demo-reset`. | No persona borrower can sign in to the portal. |
| X5 | CQ-015 migration `642b3bc55d31` has `down_revision = 8aa99c7f2577`. P1 added `e7b20ff388a7` on top of `8aa99c7f2577`. | Leaves two alembic heads, and `upgrade head` fails. |
| X6 | Pricing routes (`pricing/enrichment/router.py`, `pricing/scenarios/router.py`) depend on `get_current_lo_stub`. `applications/router.py` (`start_pipeline`, `resume_pipeline`) has no auth. | H3. |
| X7 | CI: P2 added a Valkey service and `TEST_VALKEY_URL` to the backend job. P1 restructured `ci.yml` (seed and api-client-drift jobs). | Every job whose tests import `backend/conftest.py`'s `valkey` fixture needs a Valkey service. |

## Steps

### S0 Preconditions (gate)

1. `git fetch origin`. `git merge-base --is-ancestor phase-p0-p1 origin/main` must succeed and `gh pr view 1` must show MERGED. Otherwise stop (H1).
2. The CI run on `main` after the PR #1 merge is green. If it is red, stop and report; the P1 merge plan covers the fix-forward.
3. `git status` is clean in `.worktrees/phase-p2`, apart from the ignored `.env`.

### S1 Rewrite P2 history (H2)

`git filter-repo` is not installed; use `git filter-branch`. Only P2 commits are rewritten; `5e9fcc7` and everything before it stay untouched.

1. Remove the finished item worktrees: `git worktree remove .worktrees/cq-014-staff-auth` and `git worktree remove .worktrees/cq-015-borrower-auth`. Keep `.worktrees/phase-p2`.
2. Take a safety ref: `git branch backup/phase-p2-pre-rewrite phase-p2`. It stays local and is never pushed.
3. In `.worktrees/phase-p2`:
   ```bash
   git filter-branch -f --tree-filter \
     "if [ -f .env.example ]; then sed -i '' -e 's/^DEMO_STAFF_PASSWORD=.*/DEMO_STAFF_PASSWORD=/' -e 's/^DEMO_BORROWER_PASSWORD=.*/DEMO_BORROWER_PASSWORD=/' .env.example; fi" \
     -- 5e9fcc7..phase-p2
   ```
4. Verify. Read the value back from the backup (never type it into a file):
   ```bash
   PW=$(git show backup/phase-p2-pre-rewrite:.env.example | sed -n 's/^DEMO_STAFF_PASSWORD=//p')
   test -n "$PW"
   git log -S"$PW" --oneline 5e9fcc7..phase-p2   # expect empty
   git grep -F "$PW" phase-p2                    # expect empty
   git log --merges --oneline 5e9fcc7..phase-p2  # CQ-014 and CQ-015 merges still present
   ```
5. Delete the old item branches, whose commits still hold the value. Their history now lives in the rewritten `phase-p2` merges: `git branch -D cq-014-staff-auth cq-015-borrower-auth`.
6. After S7's PR is merged and CI is green, delete `backup/phase-p2-pre-rewrite` and `refs/original/*`, then run `git reflog expire --expire=now --all && git gc --prune=now` so the value is gone from the local object store.
7. The local `.env` files in the old worktrees are gitignored and can stay. They should be deleted with the worktrees.

### S2 Merge `origin/main` into `phase-p2`

Run in `.worktrees/phase-p2`: `git merge origin/main`. Resolve conflicts by keeping both sides:

| File | Resolution |
| --- | --- |
| `backend/conftest.py` | Keep both import sets and both fixture additions (P1: `delete`, `failure_toggle`, `IntegrationCall`, latency off; P2: `Redis`, `get_valkey`, `valkey` fixture with `TEST_VALKEY_URL` / db 15, `client` overriding `get_valkey`). Remove P1's `DEV_LO_ID` default in S4. |
| `backend/app/core/config.py` | Keep all fields. Remove `demo_staff_password` / `demo_borrower_password` and add `seed_borrower_password: str | None = None` (S3). Remove `dev_lo_id` in S4. |
| `backend/app/core/registry.py` | Keep all five routers: P1's `applications`, `pricing.enrichment` and `pricing.scenarios`, and P2's `auth.staff` and `auth.borrower`. |
| `.env.example` | Keep P1's blocks and P2's session/OTP override block. Drop `DEMO_*` and document `SEED_BORROWER_PASSWORD=` (blank) next to `SEED_STAFF_PASSWORD=`. Drop `DEV_LO_ID` in S4. |
| `docs/backlog/README.md` | Take `main`'s rows for CQ-001…013 and P2's for CQ-014/015 (In Review). |
| `packages/api-client/*` | Take either side, then run `make api-client` after S4. |
| `.github/workflows/ci.yml` | Check that the backend job has P2's Valkey service and `TEST_VALKEY_URL: redis://localhost:6379/1`. Add the same service to any other job that runs `backend/conftest.py`-based tests, and keep the `SEED_STAFF_PASSWORD` CI dummy. |

Commit as `P2-merge: merge main (Phase 1) into phase-p2`. Leave the tree compiling even if tests still fail; S3 and S4 fix them.

### S3 Integration fixes (X1–X5, X7)

These are Sonnet subagent tasks in one worktree, `.worktrees/phase-p2`, or in a `p2-merge-fixes` branch off it. Owned files must not overlap.

| Task | Change | Owned files |
| --- | --- | --- |
| T-A alembic (X5) | Point `642b3bc55d31_borrower_accounts_password.py`'s `down_revision` at P1's head (`e7b20ff388a7`, or whatever `alembic heads` shows after S2). `alembic heads` must show one head. Run upgrade → downgrade base → upgrade on a fresh scratch DB. | `alembic/versions/642b3bc55d31_*.py` |
| T-B seeds (X1–X4) | See the notes below the table. | `seed/**`, `backend/app/core/config.py` (seed fields only), `.env.example` (seed block), `backend/app/features/auth/users/**`, `backend/scripts/*user*`, `pyproject.toml` / `uv.lock`, `Makefile` if needed |
| T-C CI (X7) | Adjust `ci.yml` per S2. The seed job needs `SEED_BORROWER_PASSWORD` if T-B requires it, and Valkey if the seed tests use the `valkey` fixture. | `.github/workflows/ci.yml` |

T-B changes:
- `seed/loader.py` hashes with `app.core.security.hash_password` (argon2, hashed once). Drop `bcrypt` from `pyproject.toml` and `uv.lock`, and from the mypy overrides.
- Add a `SEED_BORROWER_PASSWORD` setting, blank by default. When it is set, `make demo-reset` creates a `borrower_accounts` row (argon2 hash, `email_verified_at = now`) for every persona client. When it is unset, it skips borrower accounts with a clear log line; it does not fail, because borrower login is optional for the LO demo.
- Retire P2's `seed_dev_users` / `DEV_USERS` / `seed_dev_borrowers` / `scripts/seed_dev_users.py` in favour of `make demo-reset`. Keep `create_user` and `scripts/create_user.py`.
- Update `seed/tests` (e.g. `test_users_seeded.py` asserts argon2 via `verify_password`, and borrower accounts appear when the password is set) and `auth/users/tests`.
- Update `seed/users.yaml`'s comment, which mentions bcrypt and `DEV_LO_ID`.

### S4 Real auth on P1 routes (H3, X6)

| Task | Change | Owned files |
| --- | --- | --- |
| T-D pricing auth | See the notes below the table. | `backend/app/features/pricing/**`, `backend/app/core/config.py` (`dev_lo_id` removal), `.env.example` (`DEV_LO_ID` block), `backend/conftest.py` (`DEV_LO_ID` default removal plus a shared `staff_session` fixture), `seed/users.yaml` comment |
| T-E pipeline auth | `applications/router.py`: `start_pipeline` / `resume_pipeline` require `CurrentStaff`, and the application must be in `scope_applications` for that user (404 otherwise). Update the tests. | `backend/app/features/applications/router.py`, its tests |
| T-F contract | Run `make api-client` after T-D and T-E. Check that no frontend code calls the changed routes; the LO Console does not call pricing yet. | `packages/api-client/**` |

T-D changes:
- Every route that used `Depends(get_current_lo_stub)` uses `CurrentStaff` instead. `lo_id` becomes `user.id`.
- Where a route loads an application or scenario by id, enforce `scope_applications` (LO: own only; Manager and Admin: all) and return 404 for out-of-scope ids, not 403, to match CQ-015 Decision #11's style.
- Delete `scenarios/deps.py::get_current_lo_stub`, `test_auth_stub.py`, the `dev_lo_id` setting and `DEV_LO_ID`.
- Pricing tests authenticate through a shared fixture that creates a staff `User` and a Valkey session and sets the `cq_staff_session` cookie on the test client. Put it in `backend/conftest.py` as `staff_session` / `authed_client`, or reuse an existing helper from `auth/staff/tests` if one fits.
- Add tests: 401 without a cookie; an LO gets 404 on another LO's application; a Manager gets 200.

T-D and T-E share no files except `backend/conftest.py`. That fixture belongs to T-D; T-E waits for it or uses the auth tests' helper.

Wave order: **W1** T-A, T-B, T-C. **W2** T-D, T-E. **W3** T-F. Then S5.

### S5 Verification (gates)

| # | Gate | Check |
| --- | --- | --- |
| G1 | History clean | With `PW` read from the backup ref as in S1.4, `git grep -F "$PW" phase-p2` and `git log -S"$PW" origin/main..phase-p2` are both empty. `git ls-files | grep -E '(^|/)\.env$'` is empty. A secret-pattern `git grep` over `origin/main..phase-p2` shows nothing new. |
| G2 | Single alembic head | `uv run alembic heads` shows one head. On a fresh DB, upgrade head → downgrade base → upgrade head is clean. |
| G3 | Full suite | `make lint` and `make test` (backend, seed, frontend), plus `make api-client` with no diff. |
| G4 | Demo reset | With `SEED_STAFF_PASSWORD` and `SEED_BORROWER_PASSWORD` set locally, `make demo-reset` finishes in under 60 s and every persona ends in its expected status (P1's AC). |
| G5 | Real login e2e | Start the API (port 8000 is free once P1 is merged; use it or 8012). Log in as `jordan.lee@clearquote-demo.test` with `SEED_STAFF_PASSWORD` → Mailpit code → verify → a pricing route returns 200 → the same route without the cookie returns 401 → Morgan Reyes (the other LO) gets 404 on Jordan's application → the Manager gets 200. Borrower: log in as a persona client email with `SEED_BORROWER_PASSWORD` → `/me` returns that client and its application status. Both apps' `/login` pages load, and signing in through the console at 3010 and the portal at 3020 reaches the home pages (curl with a cookie jar, as in the CQ-014/015 post-dev files). |
| G6 | Whole-phase review | A fresh Sonnet subagent reviews `origin/main...phase-p2` as a whole: cross-item contracts (auth ↔ pricing ↔ pipeline ↔ seed), AGENTS.md rules (Decimal money only in `quote_engine`, mocks only, primary loans hide investment fields), secrets, and the known-accepted items in the CQ-014/015 `post-dev.md` files. No critical or major finding may be open. Save the result in `docs/backlog/phase-p2-review.md`. |
| G7 | CI green | Push `phase-p2`. The push run and the PR checks are green. |
| G8 | `main` has not moved | `git merge-base --is-ancestor origin/main phase-p2`. If `main` moved, merge it again and rerun G2–G7. |

### S6 Docs

- `docs/backlog/CQ-014-staff-auth/post-dev.md` and `CQ-015-borrower-auth/post-dev.md`: add an "After merge to main" section covering the demo users (now from `make demo-reset`: persona staff at `@clearquote-demo.test` and persona borrowers), the `SEED_*` env vars that replace `DEMO_*`, and the retired `seed_dev_users.py`. Update "How to test manually".
- `docs/backlog/README.md`: CQ-014 and CQ-015 stay In Review.
- The P1 merge-plan follow-up "pipeline endpoints have no auth until CQ-014" is now resolved: note that in this file's verification record, not in P1's file.
- Run `graphify update .` after the docs change (CLAUDE.md).

### S7 PR and merge

1. Push: `git push -u origin phase-p2`. This is the first push of P2, after S1 and G1.
2. `gh pr create --base main --head phase-p2 --title "Phase 2: staff and borrower auth (CQ-014, CQ-015) + P1 auth integration"`. The body lists the items, review outcomes, the H1–H4 decisions, the integration fixes X1–X7, the gate evidence and the follow-ups. End it with the Claude Code attribution line.
3. Once G6 and G7 are green, run `gh pr merge <n> --merge`. Do not delete `phase-p2`.
4. Watch the CI run on `main` and record its id and result below.
5. Kaneo: comment the merge commit on tasks 14 and 15. They stay In Review.
6. Tell the human that `main` has changed and give a summary of what the demo logins are now.

## If something fails

- The same error three times: stop, run systematic-debugging, and give the findings to a subagent (AGENTS.md).
- CI red on `main` after the merge: fix forward on a branch from `main` through a PR. A revert (`git revert -m 1`) needs the human's approval.
- If S1's rewrite goes wrong: `git branch -f phase-p2 backup/phase-p2-pre-rewrite` and retry. Nothing has been pushed at that point.

## Known follow-ups carried past this merge (not blockers)

- CQ-035: run uvicorn with `--proxy-headers --forwarded-allow-ips` (per-IP rate limits behind Railway); make session cookies same-site across Railway domains.
- A concurrency test for two simultaneous sign-up verifies of one new email; a `lower(email)` index on `clients`.
- There is no locking on least-loaded LO assignment (accepted).
- Plus everything in the P1 merge plan's follow-up list that this plan does not resolve.

## Verification record

Run on 2026-09-25 by the orchestrator session (Opus) with Sonnet subagents.

- **S0**: PR #1 was MERGED as `3f2dedd`, and main CI run 36121921951 succeeded. The worktree was clean.
- **S1**: The item worktrees were removed and `backup/phase-p2-pre-rewrite` was taken at `42eba55`. `git filter-branch` rewrote 18 commits. Afterwards neither password value appears in any P2 commit (`git log -S` and `git grep` both empty), both item merges survive, and the only tip diff against the backup is the two blanked `.env.example` lines. Commit ids in "Current state" above are pre-rewrite. They map to: `64ee14a` → `ab15c6b`, `f0da258` → `66dd422`, `4d92687` → `48f9602`, `42eba55` → `a49ef83`. `9018ff6` is unchanged. The branches `cq-014-staff-auth` and `cq-015-borrower-auth` were deleted.
- **S2**: `fd729d8` merged `origin/main` and resolved the conflicts as the S2 table says.
- **S3/S4**: T-A `cbe1478`; T-B `3e629f9`, `fad4c63`, `0bab0ef`; T-C needed no change (the backend job already runs `pytest seed` with Valkey and MinIO, and the seed tests set their own borrower password); T-D `59da3e1`; T-E `c232408`; T-F `8445321`. No frontend code calls the changed routes.
- **G1**: Clean (see S1). No `.env` is tracked. The only password-shaped strings in the diff are test fixtures and CI dummies.
- **G2**: There is one head, `642b3bc55d31`. Upgrade, downgrade base and upgrade on a scratch DB are clean.
- **G3**: `make lint` is clean. `make test` passes 344 backend, 27 seed and 124 frontend tests (api-client 2, ui 66, lo-console 20, borrower-portal 36). `make api-client` produces no diff.
- **G4**: `make demo-reset` takes 1.1 s. There are 4 staff users and 10 personas, with marcus_hale, kathleen_mcreynolds, priya_nair, daniel_ortiz, sam_reed and tom_lisa_brandt `priced`, aisha_coleman and ben_ford `needs_attention`, grace_kim `sent` and luis_romero `option_selected`. It also creates 10 borrower accounts and 200 background applications.
- **G5**: Run on API port 8000. Jordan Lee's login and OTP verify return 200, and `/me` reports role lo. `GET /scenarios/{id}/products` returns 200 for the owner and 401 without a cookie. `POST pipeline/start` returns 401 without a cookie. Morgan Reyes gets 404 on Jordan's scenario and on pipeline resume. Manager Casey Nguyen gets 200. For the borrower, Marcus Hale's login and OTP return 200, and `/me` returns his client with `latest_application.status = priced`. Both `/login` pages return 200 on 3010 and 3020. `/` redirects (307) to `/login` without a cookie and returns 200 with the session cookie on both apps.
- **G6**: `docs/backlog/phase-p2-review.md` has 0 critical, 0 major, 2 minor and 1 nit, all fixed (`2521b30`, `8df0ba2`).
- **G8**: `origin/main` is an ancestor of `phase-p2`.
- **P3/P4 isolation**: The P3/P4 work had started in parallel on `p34-setup`, which rewrites CQ-016…024 specs. This PR's only P3/P4 file was CQ-020's `spec.md`, from P2's `9018ff6` magic-link edit. `db1b529` restores `main`'s copy, because `p34-setup` already drops the magic link there. `git merge-tree p34-setup phase-p2` is clean. CQ-015 `plan.md` Decision #1 still says the CQ-020 spec was updated on `phase-p2`; that change now lives in the P3/P4 rewrite instead.
- **P1 follow-up resolved**: "pipeline endpoints have no auth until CQ-014" is resolved by T-E.
