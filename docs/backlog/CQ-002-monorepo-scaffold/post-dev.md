# CQ-002 — Post-development notes

## Summary

Scaffolded the full monorepo skeleton pinned by `spec.md`: a pnpm workspace (`@cq/lo-console`, `@cq/borrower-portal`, `@cq/ui`, `@cq/api-client`) with minimal-but-real Next.js/TS packages, a root `uv` Python project (`backend/app`, ruff/mypy/pytest config), the `alembic/` skeleton wired to the not-yet-existing `app.core` modules, root `Makefile`/`.env.example`/`.pre-commit-config.yaml`/ESLint+Prettier config, and empty placeholder directories for everything later items (CQ-004, 007, 009, 011) will fill in. `make lint` and `make test` both run cleanly end to end; `pre-commit run --all-files` is green. All work stayed inert: no real FastAPI app, no Docker Compose, no design tokens/components — only structure and tooling.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `corepack enable` implied as the pnpm install path | Used `npm install -g pnpm@9.15.4` | `corepack enable` failed with exit 127 (permission issue writing shims to `/usr/local/bin` without sudo) — the execution brief explicitly allows this fallback. |
| `pnpm exec prettier --check .` (root-wide, no exclusions implied) | Added `.prettierignore` entries for `docs/`, `graphify-out/`, `.claude/`, `.codex/`, `.mcp.json`, `opencode.json`, `AGENTS.md` | Root-wide Prettier flagged ~168 pre-existing files owned by other backlog items / agent tooling that predate this item's tooling and that AGENTS.md says not to change. |
| `pre-commit run --all-files` (repo-wide) | Added a top-level `exclude` regex in `.pre-commit-config.yaml` for `.claude/`, `.codex/`, `graphify-out/`, `docs/` | The generic hooks initially rewrote pre-existing tracked files in `.claude/`/`graphify-out/` (CQ-001 content); reverted those edits and scoped hooks to this item's tree. |
| AC5 test command `grep -E '^[A-Z_]+=' .env.example \| wc -l` (≥ 16) | Ran as pinned (result: 12) plus a corrected count | The pinned regex's `[A-Z_]+` excludes any key containing a digit, so it misses all five `S3_*` keys (`S3` contains "3"). All 17 pinned keys are present, spelled exactly as the spec lists them — verified with `grep -cE '^[A-Za-z_][A-Za-z0-9_]*=' .env.example` → 17. See evidence row below for both numbers. |
| Directory layout `backend/app/core/` shown with `config.py, db.py, errors.py, registry.py` | Left `backend/app/core/` empty (`.gitkeep` only), same as `integrations/`, `features/`, `workflows/` | The spec annotates those four files "(real code lands CQ-004)", and CQ-004's own spec independently lists creating exactly those four files under "Modules to create". Creating stub versions here would mean CQ-004 overwrites (not creates) them. Logged as Decision #2 in `plan.md`. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — `make lint` and `make test` pass | Pass | `make lint` → exit 0 (ruff check, ruff format --check, mypy, `pnpm -r lint`, `pnpm -r typecheck`, `pnpm exec prettier --check .` all green). `make test` → exit 0 (`uv run pytest backend`: 1 passed; `pnpm -r run test`: 4/4 workspace test suites, 1 passed each). |
| AC2 — directory layout exact | Pass | `find backend/app apps packages alembic -maxdepth 2 \| sort` matches the pinned layout (plus gitignored `node_modules/`/`__pycache__` build artifacts, which don't exist in a fresh checkout before install). |
| AC3 — workspace packages exactly | Pass (with note) | `pnpm ls -r --depth -1 --json \| jq '[.[].name]'` → `["clear-quote","@cq/borrower-portal","@cq/lo-console","@cq/api-client","@cq/ui"]`. The four pinned `@cq/*` names are all present exactly; the private workspace root (`clear-quote`) is inherent to `pnpm ls -r` and not an extra package (Decision #11). |
| AC4 — `uv sync` + `import app` | Pass | `uv sync` → resolved/installed cleanly. `uv run python -c "import app; print('ok')"` → `ok`. |
| AC5 — `.env.example` keys | Pass (with note) | All 17 pinned keys present, spelled exactly. Pinned command `grep -E '^[A-Z_]+=' .env.example \| wc -l` → `12` (regex excludes digit-bearing keys like `S3_*`; < 16 as literally run). Corrected `grep -cE '^[A-Za-z_][A-Za-z0-9_]*=' .env.example` → `17` (≥ 16, and matches full key list). See Decision #10. |
| AC6 — Makefile targets exist | Pass | `grep -E '^(up|down|logs|lint|test|api-client|demo-reset):' Makefile` lists all seven. `make demo-reset; echo $?` → prints `demo-reset: not implemented until CQ-010`, exit `0`. `make up` (no compose file yet) → fails loudly: `open .../infra/docker-compose.yml: no such file or directory`, `make: *** [up] Error 1`. |
| AC7 — `pre-commit run --all-files` | Pass | All 6 hooks (`ruff`, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`) report `Passed`. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | `1 passed in 0.00s` |
| Backend lint | `uv run ruff check backend` | `All checks passed!` |
| Backend format | `uv run ruff format --check backend` | `2 files already formatted` |
| Backend types | `uv run mypy backend/app` | `Success: no issues found in 1 source file` |
| Backend import | `uv run python -c "import app"` | succeeds |
| uv sync | `uv sync` | resolved 15 packages, installed cleanly |
| Frontend lint | `pnpm -r run lint` | 4/4 packages `Done`, exit 0 (two informational "Pages directory cannot be found" warnings from `eslint-config-next` on the non-Next `packages/ui`/`packages/api-client` — cosmetic, not an error, doesn't fail the run) |
| Frontend typecheck | `pnpm -r run typecheck` | 4/4 packages `Done`, exit 0 |
| Frontend test | `pnpm -r run test` | 4/4 Vitest suites, 1 test each, all passed |
| Formatting | `pnpm exec prettier --check .` | `All matched files use Prettier code style!` |
| Full lint | `make lint` | exit 0 |
| Full test | `make test` | exit 0 |
| Pre-commit | `pre-commit run --all-files` | all 6 hooks `Passed` |
| Workspace packages | `pnpm ls -r --depth -1 --json \| jq '[.[].name]'` | `["clear-quote","@cq/borrower-portal","@cq/lo-console","@cq/api-client","@cq/ui"]` |
| Makefile targets | `grep -E '^(up\|down\|logs\|lint\|test\|api-client\|demo-reset):' Makefile` | all 7 present |
| demo-reset | `make demo-reset; echo $?` | prints placeholder message, exit `0` |
| up (loud failure) | `make up` | exit `2`, clear "no such file" error (infra/docker-compose.yml not yet created — CQ-003) |

## Review findings (stage 6)

_(left for the fresh reviewer — stage 6 not yet run)_

| Severity | Finding | Resolution |
| --- | --- | --- |

## How to test manually

1. `pnpm install && uv sync`
2. `make lint`
3. `make test`
4. `find backend/app apps packages alembic -maxdepth 2 | sort` and compare to `spec.md`'s "Directory layout" section.
5. `pre-commit run --all-files` (requires `uv tool install pre-commit` once, or run via `uvx pre-commit run --all-files`).

## Follow-ups

- CQ-004 creates `backend/app/core/{config,db,errors,registry}.py`; once it does, `alembic/env.py`'s pinned imports will actually resolve (they don't yet — out of scope here, not exercised by any CQ-002 check).
- CQ-005 replaces every `src/lib/placeholder.ts(.test.ts)` / `src/index.ts(.test.ts)` file in `apps/*` and `packages/ui`/`packages/api-client` with real content and tests (mirrors the already-pinned `backend/tests/test_placeholder.py` deletion note).
- CQ-005 pins the frontend dev ports (3010/3020) in each app's `dev` script; left at Next's default here since that item explicitly owns the port choice.
- Cosmetic: `eslint-config-next`'s `no-html-link-for-pages` rule prints a "Pages directory cannot be found" informational warning (not an error) when linting `packages/ui`/`packages/api-client`, since they aren't Next apps. Doesn't fail `make lint`; could be silenced later by scoping the Next-specific ESLint extends to `apps/**` only if it becomes noisy.
