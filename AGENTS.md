# AGENTS.md — Clear Quote TQL

Shared instructions for every coding agent (Claude Code, Codex, OpenCode). `CLAUDE.md` only imports this file. Keep this file the single source; tool installers may append their own fenced sections below the marker at the end.

## What this repo is

Clear Quote is a prototype mortgage quoting system: an LO Console and a Borrower Portal (Next.js) over one FastAPI backend, with a Temporal pipeline that imports, verifies, enriches and prices loan files from **emulated** providers (Encompass, Optimal Blue, RentCast, AirDNA and others are mocks). Read these before any work:

1. `docs/design/system-design.md` — product spec, calculation engine, data model, architecture. Binding.
2. `docs/design/data-field-catalog.md` — field names and sources.
3. `docs/roadmap.md` — phases, backlog, agent loop.
4. The backlog item you are working on: `docs/backlog/CQ-XXX-*/`.

## Project map

```
alembic/                 migrations (root level)
backend/app/core/        config, db, auth deps, errors
backend/app/integrations/  mock adapters behind Protocols
backend/app/features/<feature>/<sub-feature>/   router.py models.py schemas.py service.py endpoints/ tests/
backend/app/workflows/   Temporal workflows, activities, worker
apps/lo-console/         Next.js, internal
apps/borrower-portal/    Next.js, public
packages/ui/             design tokens + shared report components
packages/api-client/     generated from the FastAPI OpenAPI schema; never hand-edit
seed/                    persona fixtures + generators
infra/                   compose + railway
docs/                    design/, roadmap.md, backlog/
```

## Commands

Filled in by CQ-002 and CQ-003. Until they exist, do not invent them.

| Command | Does |
| --- | --- |
| `make up` / `make down` / `make logs` | Local stack (Postgres, Valkey, MinIO, Mailpit, Temporal) |
| `make lint` | ruff, mypy, eslint, prettier check, tsc |
| `make test` | pytest + frontend tests |
| `make demo-reset` | Drop DB, migrate, seed personas and background data |
| `make api-client` | Export OpenAPI and regenerate `packages/api-client` |

## Tool split (codegraph vs graphify)

- **codegraph** answers code questions: where a symbol lives, callers/callees, impact of a change. Use `codegraph_explore` (MCP) or `codegraph explore "<question>"` before grepping or reading source files.
- **graphify** answers docs questions: specs, design, cross-document links. Use `graphify query "<question>"` for anything under `docs/`.
- If a graph answer looks stale, read the file directly; do not re-verify every answer with grep.

## How work is done: the agent loop

Every backlog item runs this loop. Use `using-superpowers` to pick the skill at each stage. Frontend tasks also use `react-doctor`.

| Stage | Skill | Output | Gate |
| --- | --- | --- | --- |
| 1 Brainstorm | brainstorming, as a **gap check against spec.md** (no new design doc) | "Decisions & questions" at top of `plan.md`. Small gaps with data available → decide and log `Decision: …`. Big gaps → Kaneo comment + `needs-input` label, stop | No open big gaps |
| 2 Plan | writing-plans | `plan.md`: why, what, files touched, tasks + dependencies, a test for every acceptance criterion | Every criterion maps to ≥ 1 test |
| 3 Execute | dispatching-parallel-agents, using-git-worktrees | Wave schedule in `plan.md`; each task lists owned files | No two tasks in one wave touch the same file; schemas, migrations and API contracts land before consumers |
| 4 Code | subagent-driven-development, test-driven-development (+ react-doctor) | Code + tests; checklist ticks in `plan.md` | Task tests green. Same error 3× → stop, run systematic-debugging, hand findings to a subagent to re-brainstorm and re-plan |
| 5 Test | verification-before-completion | Test log in `post-dev.md` (pytest, ruff, mypy, eslint, tsc, react-doctor) | All green; add tests for gaps found |
| 6 Review | requesting-code-review via a **fresh subagent** that did not write the code; receiving-code-review | Findings by severity in `post-dev.md` | No critical/major open |
| 7 Verify | verification-before-completion | Acceptance checklist in `post-dev.md`, each with evidence | All evidenced; failure → back to stage 2; same criterion failing twice → `needs-input` |
| 8 Commit | finishing-a-development-branch | Conventional commits prefixed `CQ-XXX:` | Kaneo task → In Review; the human merges |

**Rules**

- The main session is the orchestrator: it plans, dispatches and reviews. Subagents read and write code.
- Contract first: when backend and frontend run in parallel, the OpenAPI change and regenerated api-client are wave 1.
- One branch and worktree per item: `cq-XXX-slug`. Never commit to `main` directly.
- Do not change `docs/design/*` or another item's `spec.md`. Propose changes in your `plan.md` under "Decisions & questions".
- Money math lives only in `quote_engine` (Decimal). Frontends never compute money.
- Primary loans never show rent, DSCR, cashflow, cost seg or PPP. LTR and STR are never shown side by side.

## Handoff protocol

When your context is about 70% used, or you end a session with the item open, append an entry to the item's `handoff.md` (template in `docs/backlog/_templates/handoff.md`) and add a Kaneo comment linking it. A new session starts by reading `spec.md`, `plan.md`, then the latest `handoff.md` entry, then runs the "verify state" commands from it.

## Kaneo

Project **Clear Quote TQL** (key `CQ`) in workspace Personal-Work-Projects, reached through the `kaneo` MCP server (local Kaneo at `http://localhost:5183`, configured in `.mcp.json`, `.codex/config.toml` and `opencode.json`; no API key). Kaneo's task number equals the backlog id (CQ-017 is Kaneo task 17). Each task's description holds its folder path.

| Moment | Kaneo action |
| --- | --- |
| Start stage 1 | Move to In Progress |
| Big gap | Comment with the question; attach `needs-input` |
| Dependency not done | Attach `blocked`; do not start |
| Each handoff | Comment: "Handoff N — see handoff.md" |
| Stage 8 done | Move to In Review; comment with the post-dev summary |

Only the human moves tasks to Done.

## Definition of done

- Acceptance criteria in `spec.md` met, each with evidence in `post-dev.md`
- Tests pass; ruff, mypy, eslint, tsc clean; react-doctor passes (frontend)
- Fresh-subagent review: no critical/major findings open
- `make demo-reset` still works (from CQ-010 onward)
- `post-dev.md` complete; Kaneo task in In Review

<!-- Tool-generated sections (codegraph, graphify) go below this line. Keep the sections above authoritative. -->
