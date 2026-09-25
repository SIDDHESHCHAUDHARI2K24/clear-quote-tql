# CQ-002 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | pnpm install method | `corepack enable` failed with exit 127 (permission issue writing shims into `/usr/local/bin` without sudo). Used `npm install -g pnpm@9.15.4` instead (one of the two options the execution brief allows). Logged here per brief instruction. |
| 2 | Decision | Contents of `backend/app/core/`, `integrations/`, `features/`, `workflows/`, `backend/scripts/`, `alembic/versions/` | Spec's directory layout lists `core/config.py, db.py, errors.py, registry.py` but annotates "(real code lands CQ-004)"; CQ-004's own spec independently lists these same four files under "Modules to create (pin exactly)". Decided these dirs stay empty (git-tracked via `.gitkeep`) at CQ-002 time, matching `integrations/`, `features/`, `workflows/` which the spec explicitly marks "empty". CQ-004/007/009/011 each create their own files per their own specs — no duplicate/half-built modules for them to overwrite. |
| 3 | Decision | `alembic/env.py` imports of `app.core.db`/`app.core.config` | Spec pins these imports exactly even though those modules don't exist until CQ-004 (decision #2). This is safe: alembic migrations are explicitly out of scope for CQ-002 (real models land CQ-007), no CQ-002 AC invokes any `alembic` command, and `alembic/` is outside the `backend/` tree that `make lint`'s ruff/mypy commands scope to, so it is never imported or linted by this item's checks. |
| 4 | Decision | Frontend "empty but real" scaffold | `apps/lo-console`, `apps/borrower-portal`, `packages/ui`, `packages/api-client` get minimal real Next.js/TS package scaffolds now (package.json, tsconfig, one page/index file) with `lint`/`typecheck`/`test` scripts that genuinely run. Each gets exactly one trivial passing Vitest test (mirroring the `backend/tests/test_placeholder.py` decision already pinned in this spec) so `pnpm -r run test` is genuinely green, not stubbed. Design tokens, real components, the gallery, the home page and Testing-Library-based component tests are CQ-005 scope and are not added here. |
| 5 | Decision | Frontend dev port | Left at Next.js's default (`next dev`, port 3000) rather than pre-pinning 3010/3020, since CQ-005's own spec explicitly states it "owns the frontend dev-port choice." No CQ-002 AC depends on the dev port. |
| 6 | Decision | Pre-commit install | Installed via `uv tool install pre-commit` (kept Python-only per spec's explicit decision) rather than a separate global installer, so `pre-commit run --all-files` works without extra host setup. |
| 7 | Decision | `make up` / `make api-client` "fail loudly" behavior | `make up` runs the pinned `docker compose -f infra/docker-compose.yml up -d --wait` as-is; since `infra/docker-compose.yml` doesn't exist yet (CQ-003 lands it), `docker compose` itself fails loudly (non-zero exit, "no such file" on stderr) — no extra guard needed. `make api-client` runs both pinned commands as-is, which similarly fail loudly today because `backend/scripts/export_openapi.py` and `@cq/api-client`'s `generate` script don't exist yet (CQ-004/CQ-005 add them). No AC requires either target to succeed at CQ-002 time, only to exist and fail loudly, not silently. |
| 8 | Decision | `pnpm exec prettier --check .` scope | Root-wide Prettier flags ~168 pre-existing markdown/config files under `docs/`, `graphify-out/`, `.claude/`, `.codex/`, `.mcp.json`, `opencode.json` and `AGENTS.md` — all authored before this item and owned by other backlog items or agent tooling, which AGENTS.md says not to change. Added `.prettierignore` entries for these paths so `make lint`'s Prettier check is scoped to code/config this and later items own, without reformatting content out of scope. |
| 9 | Decision | `pre-commit run --all-files` scope | The generic hooks (`end-of-file-fixer` etc.) initially rewrote pre-existing tracked files under `.claude/` and `graphify-out/` (agent tooling from CQ-001) that this item shouldn't touch. Added a top-level `exclude` regex to `.pre-commit-config.yaml` for `.claude/`, `.codex/`, `graphify-out/`, `docs/`, mirroring the Prettier decision above. Reverted the unintended edits to those files before committing. |
| 10 | Decision | AC5's `grep -E '^[A-Z_]+='` count | This exact pattern only matches 12 of the 17 pinned `.env.example` keys — it excludes every `S3_*` key because `S3` contains a digit, which `[A-Z_]+` doesn't allow. All 17 pinned keys are present, spelled exactly as the spec lists them; a corrected pattern (`^[A-Za-z_][A-Za-z0-9_]*=`) counts 17. Recorded both counts in `post-dev.md` rather than renaming spec-pinned keys to fit the AC's example regex. |
| 11 | Decision | `pnpm ls -r --depth -1 --json` includes the workspace root | The command in AC3 always includes the private root project (`clear-quote`) alongside the four `@cq/*` packages — pnpm's `-r` flag lists the whole workspace, root included. Verified via `jq` that the four pinned names are present exactly; the root entry is inherent to the command, not an extra package this item added. |

## Why

CQ-002 lays the one-time skeleton (pnpm workspace, uv project, Makefile, lint/test tooling, directory layout) that every later item builds on, so nobody re-litigates paths, package names or tool config. Scope is deliberately inert: no real backend app, no Docker Compose, no design system — just enough structure for `make lint` and `make test` to pass genuinely on empty projects.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Root tooling | `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `.python-version`, `uv.lock`, `Makefile`, `.env.example`, `.pre-commit-config.yaml`, `eslint.config.mjs`, `.prettierrc.json`, `.prettierignore`, `.gitignore` (extend) |
| Backend skeleton | `backend/app/__init__.py`, `backend/app/{core,integrations,features,workflows}/.gitkeep`, `backend/scripts/.gitkeep`, `backend/tests/test_placeholder.py` |
| Alembic | `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`, `alembic.ini` |
| Frontend apps | `apps/lo-console/*`, `apps/borrower-portal/*` (Next.js App Router + TS minimal scaffold, one placeholder page, one Vitest test) |
| Frontend packages | `packages/ui/*`, `packages/api-client/*` (minimal TS package scaffold, one Vitest test each) |
| Misc dirs | `seed/.gitkeep`, `infra/.gitkeep` (compose file lands CQ-003) |
| Docs | this `plan.md`, `post-dev.md`, `docs/backlog/README.md` status row |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Root pnpm workspace + package.json + workspace packages | — | `package.json`, `pnpm-workspace.yaml` | AC3 |
| T2 | Root uv project (pyproject.toml, .python-version, ruff/mypy/pytest config) | — | `pyproject.toml`, `.python-version` | AC4 |
| T3 | Backend package skeleton + placeholder test | T2 | `backend/app/**`, `backend/tests/test_placeholder.py` | AC2, AC4, AC1 (pytest) |
| T4 | Alembic skeleton | T2, T3 | `alembic/**`, `alembic.ini` | AC2 |
| T5 | Frontend apps scaffold (lo-console, borrower-portal) | T1 | `apps/**` | AC1 (pnpm lint/test), AC2, AC3 |
| T6 | Frontend packages scaffold (ui, api-client) | T1 | `packages/**` | AC1, AC2, AC3 |
| T7 | Root ESLint/Prettier config | T1, T5, T6 | `eslint.config.mjs`, `.prettierrc.json` | AC1 |
| T8 | Makefile | T1–T7 | `Makefile` | AC1, AC6 |
| T9 | `.env.example` | — | `.env.example` | AC5 |
| T10 | pre-commit config | T2 | `.pre-commit-config.yaml` | AC7 |
| T11 | Run full verification, fill post-dev.md, update backlog README status | T1–T10 | `post-dev.md`, `docs/backlog/README.md` | all ACs |

## Wave schedule (stage 3)

Single agent, sequential (no independent parallel workers needed — nearly every task touches shared root config). Order: T2→T3→T4, T1→T6→T5→T7 (T1 first since T5/T6 need the workspace), T9/T10 any time, T8 last before T11.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `make lint`, `make test` |
| AC2 | `find backend/app apps packages alembic -maxdepth 2 \| sort` |
| AC3 | `pnpm ls -r --depth -1 --json` |
| AC4 | `uv sync && uv run python -c "import app"` |
| AC5 | `grep -E '^[A-Z_]+=' .env.example \| wc -l` (≥ 16) |
| AC6 | `make demo-reset; echo $?` + `grep` for each target in Makefile |
| AC7 | `pre-commit run --all-files` |

## Progress

- [x] T1 pnpm workspace + root package.json
- [x] T2 uv project
- [x] T3 backend skeleton + placeholder test
- [x] T4 alembic skeleton
- [x] T5 frontend apps scaffold
- [x] T6 frontend packages scaffold
- [x] T7 root eslint/prettier config
- [x] T8 Makefile
- [x] T9 .env.example
- [x] T10 pre-commit config
- [x] T11 verification + post-dev.md + backlog README
