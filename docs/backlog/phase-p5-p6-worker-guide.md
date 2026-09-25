# P5/P6 worker guide (shared instructions for every item worker)

Placeholders: {BRANCH}, {FOLDER}, {KID} (Kaneo task id), {CQ}, {SLOT}, {PORT} (= 100+SLOT, e.g. slot 12 → 112), {PPORT} (= 200+SLOT) and {E2E_NOTE} are given in your coordinator prompt.

Before anything else in a fresh worktree, run `pnpm install --frozen-lockfile` and `uv sync`.

## Overall goal
The human asked us to plan and build phases P5 (LO Tier B, CQ-025–030) and P6 (Borrower Tier B/C, CQ-031–034) of Clear Quote TQL. It is a prototype mortgage quoting system: an LO Console and a Borrower Portal (Next.js) over a FastAPI backend with a Temporal pipeline, and every provider is a mock. The specs and design docs are the reference.

## Setup
Repo: this worktree. FIRST: `git fetch origin && git switch -c {BRANCH} origin/phase-p5-p6`. Never touch main, phase-p2, phase-p3-p4 or other worktrees or branches.

Read in order:
1. AGENTS.md
2. docs/backlog/{FOLDER}/spec.md
3. docs/backlog/phase-p5-p6-plan.md (H1–H5 and E1–E17 are binding)
4. docs/backlog/phase-p5-p6-foundation.md. It lists what the foundation already gives you:
   - migration 3b55187d53d7: flags.message; consents status and request columns (server default pending); tables support_requests and application_drafts; applications.source los/portal
   - core/clock.now() (honours CLOCK_NOW)
   - core/pagination: Page[T] and paginate(db, stmt, page, page_size)
   - core/storage (async code uses astream_object)
   - applications.assignment.least_loaded_lo_id(db)
   - pipeline: an application with source=portal skips the import step
   - seed borrower noapp.borrower@clearquote-demo.test, who has no application
   - lo-console `(staff)` route group with StaffShell and useStaffSession(); admin guard
   - portal `(portal)` route group with useBorrowerSession(); ToastProvider mounted in both shells
   - @cq/ui primitives: Pagination, Select, MultiSelect, Drawer, EmptyState, useToast, useFocusTrap
5. docs/design/system-design.md and docs/design/data-field-catalog.md, only the sections the spec names.

Docs questions: `graphify query "<q>"`. Code questions: codegraph if `.codegraph/` exists, else grep/read.

## Agent loop (AGENTS.md stages 1–8; templates in docs/backlog/_templates/)
- **Stages 1–3:** fill docs/backlog/{FOLDER}/plan.md from _templates/plan.md:
  - Decisions & questions, including the E-decisions that apply to you
  - why, files, tasks with owned files, wave schedule
  - every AC mapped to at least one test

  For a small gap, decide and log `Decision: …`. For a big gap:
  - post a Kaneo comment on task `{KID}` (kaneo MCP `create_task_comment`)
  - attach the label `needs-input` with `attach_label_to_task` and workspace label id `alox7xayonm5qx2usezz5uip`
  - stop and report `PR: none — needs-input`.
- **Stage 4: TDD.** Backend conventions:
  - Layout: `features/<feature>/<sub>/{router,models,schemas,service}.py` plus `tests/`. Register the router module in `core/registry.py` FEATURE_ROUTERS. Routes live under `/api/v1`, so a spec path `/api/x` means `/api/v1/x`.
  - Errors: core/errors.py.
  - Auth: core/auth.py.
    - Staff: CurrentStaff with scope_applications(stmt, user, lo_id) and get_scoped_application. Out-of-scope access returns 404 (E16).
    - Admin-only: require_roles, which gives 403.
    - Borrowers: CurrentBorrower with ensure_borrower_owns_client.
  - Email: notifications/email/service.py `send_email(db, *, to, subject, html, application_id=None)`. It writes an outbox row and does not commit. Templates are Python string helpers, like portal/actions/templates.py.
  - Activity: ActivityEvent in applications/timeline/models.py.
  - Test fixtures: backend/conftest.py (db_session, client, make_staff_session(role), make_borrower_session, fake Valkey).
  - Money math lives only in quote_engine (Decimal). Frontends never compute money.
  - Primary loans never show rent, DSCR, cashflow, cost seg or PPP. LTR and STR are never shown side by side.
  - After API changes run `make api-client`. Never hand-edit packages/api-client.

  Frontend conventions:
  - Build from packages/ui tokens and components.
  - Put code in `src/features/<feature>/`, with thin `api.ts` wrappers over `lib/api-client.ts` (openapi-fetch).
  - Write Vitest tests.
  - Run `npx react-doctor -y --blocking error` in stages 4 and 5.
- **Owned files:** stay inside your owned paths. You may also add one line to `core/registry.py` and regenerate the api-client. Edit anything else only for a small necessity, and log it.
- **Stage 5:** `make lint` and `make test` green. Log the results in docs/backlog/{FOLDER}/post-dev.md, made from _templates/post-dev.md.
- **Stage 7:** acceptance checklist in post-dev.md with evidence for each AC. Some ACs need unbuilt P3 items (CQ-017..020) or later P5/P6 items. Verify those with fixtures, factories or URL assertions, and mark them `pending — re-check after <item>`.
- **Stage 8:**
  - Conventional commits prefixed `{CQ}:`, each ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Run `graphify update .` before the final commit.
  - Post a Kaneo comment on task `{KID}` with the PR link. Do not change the task status; the orchestrator does that.

## Context cap (binding)
Wave-2 workers overran the cap (one reached 432K). Keep context lean:
- Read files by line range, not whole.
- Run tests with `-q` and tail the output.
- Don't paste large logs.
- Hand small, self-contained pieces (a component, a test file) to sub-agents.
- Check your usage after every stage.
Never exceed 400K tokens of context. At about 350K:
1. Commit your WIP.
2. Append an entry to docs/backlog/{FOLDER}/handoff.md using _templates/handoff.md.
3. Push the branch.
4. Stop with `PR: none — handoff at <sha>`.

If you are mid-way through a critical atomic step (a migration, a half-applied refactor, a failing test being fixed), you may continue to about 450K to reach a consistent state, then hand off. Any sub-agents you spawn get the same cap and must stay small.

## Parallel siblings in this wave (do not build their parts)
- CQ-025 dashboard
- CQ-027 applications list (owns ApplicationRow and the list endpoint)
- CQ-028a verification API
- CQ-029 timeline, outbox and admin screens
- CQ-030 stale quote job
- CQ-031 borrower home
- CQ-032a apply API
- CQ-034 support form

Each lands as its own PR into phase-p5-p6. Shared lines in registry.py and the api-client files will be merged by the orchestrator.

## E2E recipe (slot {SLOT})
1. In a **bash** shell (not zsh; the script uses BASH_SOURCE), run `source scripts/worktree-env.sh {SLOT}`. It gives you:
   - DBs cq_dev_s{SLOT} and cq_test_s{SLOT}
   - your own Valkey db, and TEST_VALKEY_URL for pytest
   - API port 8{PORT}, LO console 3{PORT}, portal 3{PPORT}
   - Temporal queue cq-s{SLOT}

   Shared infra from `make up` is already running. Never touch the cq_dev, cq_test or *_p2 DBs, ports 8000/3010/3020, or any other slot.
2. Run `make demo-reset`. Then start, in the background:
   - the API, **from the repo root** (config reads `.env` relative to the cwd): `uv run --directory backend uvicorn app.main:app --port $API_PORT` or `PYTHONPATH=backend uv run uvicorn app.main:app --port $API_PORT`. Run pytest from the repo root too
   - `make worker`, if workflows are involved
   - the affected app: `pnpm --filter @cq/<app> exec next dev -p <port>`
3. API check. Log in with curl:
   - staff: users in seed/users.yaml, password SEED_STAFF_PASSWORD from .env
   - borrowers: `<first>.<last>@clearquote-demo.test`, password SEED_BORROWER_PASSWORD
   - the OTP comes from Mailpit at http://localhost:8025/api/v1/messages

   Hit your endpoints for the AC personas and check the numbers and emails.
4. UI: run the Playwright specs named in your spec's test plan:
   `LO_BASE_URL=http://localhost:3{PORT} PORTAL_BASE_URL=http://localhost:3{PPORT} pnpm exec playwright test <specs>`
   Save screenshots (1280 px; also 375 px for portal pages) to docs/backlog/{FOLDER}/evidence/.
5. Kill the background processes **by PID**. Never use `pkill -f` patterns, because they can kill another slot's worker.

After every `make demo-reset`, restart the API and worker. Their pooled asyncpg connections cache type OIDs from the dropped database, so the first request fails with `cache lookup failed for type`.

{E2E_NOTE}

## After you finish implementing the change:
1. **Code review** — Invoke the `Skill` tool with `skill: "code-review"` to find correctness bugs (it reports findings; it does not edit code). Fix any findings it surfaces before continuing.
2. **Run unit tests** — Run the project's test suite (check for package.json scripts, Makefile targets, or common commands like `npm test`, `bun test`, `pytest`, `go test`). If tests fail, fix them.
3. **Test end-to-end** — Follow the e2e test recipe from the coordinator's prompt (below). If the recipe says to skip e2e for this unit, skip it.
4. **Commit and push** — Commit all changes with a clear message, push the branch, and create a PR with `gh pr create`. Use a descriptive title. If `gh` is not available or the push fails, note it in your final message.
5. **Report** — End with a single line: `PR: <url>` so the coordinator can track it. If no PR was created, end with `PR: none — <reason>`.

The project suite is `make lint` plus `make test`. Create the PR with `gh pr create --base phase-p5-p6 --title "{CQ}: <title>"`. The PR body summarises each AC and its evidence, and ends with "🤖 Generated with [Claude Code](https://claude.com/claude-code)".
