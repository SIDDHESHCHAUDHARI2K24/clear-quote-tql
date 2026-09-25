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

Fresh-subagent review, 2026-09-25. Verdict: **APPROVE** — no critical/major findings.

Re-ran verification commands independently in the worktree (not trusting the log above):

| Command | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | exit 0, lockfile up to date |
| `uv sync` | exit 0, resolved/checked 14-15 packages |
| `make lint` | exit 0 (ruff check/format, mypy, pnpm -r lint/typecheck, prettier --check) |
| `make test` | exit 0 (`uv run pytest backend`: 1 passed; `pnpm -r run test`: 4/4 suites, 1 test each) |
| `find backend/app apps packages alembic -maxdepth 2 \| sort` | matches spec's pinned layout exactly |
| `pnpm ls -r --depth -1 --json \| jq '[.[].name]'` | `["clear-quote","@cq/borrower-portal","@cq/lo-console","@cq/api-client","@cq/ui"]` — matches AC3 |
| `uv sync && uv run python -c "import app"` | succeeds, prints `ok` |
| `grep -E '^[A-Z_]+=' .env.example \| wc -l` | `12` (spec's pinned regex, as documented, misses `S3_*` keys) |
| `grep -cE '^[A-Za-z_][A-Za-z0-9_]*=' .env.example` | `17` — all pinned keys present, spelled exactly |
| `grep -E '^(up\|down\|logs\|lint\|test\|api-client\|demo-reset):' Makefile` + `make demo-reset; echo $?` | all 7 targets present; prints placeholder message, exit 0 |
| `make up` (no compose file yet) | fails loudly: `open .../infra/docker-compose.yml: no such file or directory`, exit 2 |
| `pre-commit run --all-files` | all 6 hooks `Passed` |

Also checked: `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `.env.example`, `Makefile`, `alembic/env.py`/`alembic.ini`, all four apps'/packages' `package.json` and `tsconfig.json` against the spec's pinned contents — byte-for-byte match on names, paths, ports-deferred-to-CQ-005, and import wiring. Diffed `docs/` to confirm only `docs/backlog/README.md`'s CQ-002 status row and this item's own `plan.md`/`post-dev.md` changed — no other backlog item's `spec.md` or `docs/design/*` touched. Confirmed no secrets in `.env.example`, no `node_modules` committed, `uv.lock`/`pnpm-lock.yaml` both committed. Commit is on branch `cq-002-monorepo-scaffold`, not `main`, prefixed `CQ-002:`.

Sanity-checked plug-in points for downstream items: `@cq/ui`/`@cq/api-client` package names match CQ-005's spec exactly (CQ-005 explicitly says to reconcile against CQ-002 if it differs — it doesn't); both apps' `tsconfig.json` already set `"strict": true` (CQ-005 AC2); `eslint.config.mjs` already ignores `packages/api-client/src/schema.d.ts` ahead of CQ-005 generating it; `backend/app/core/{config,db,errors,registry}.py` are correctly left uncreated (`.gitkeep` only) so CQ-004 creates rather than overwrites them; `alembic/env.py` imports the not-yet-existing `app.core.db`/`app.core.config` but this is outside `backend/` (ruff/mypy scope) and no CQ-002 AC invokes `alembic`, so it's inert until CQ-004 lands; `.env.example` keys/ports match what CQ-003's and CQ-004's specs assume (`5432`, `6379`, `9010`, `1025`, `7233`, `8000` reserved for `make api`, `3010`/`3020` reserved for CQ-005).

| # | severity | file:line | finding | suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `docs/backlog/CQ-002-monorepo-scaffold/spec.md:170` | AC5's pinned test command `grep -E '^[A-Z_]+=' .env.example \| wc -l` undercounts (12, not ≥16) because `[A-Z_]+` can't match keys containing a digit (`S3_*`). Correctly diagnosed and logged as Decision #10 in `plan.md`, with the corrected regex giving 17 — but the spec itself (which this item may not edit per AGENTS.md) still has a command that fails its own stated threshold. | Flag for the human/a future item to fix the regex in `spec.md` (e.g. `^[A-Za-z_][A-Za-z0-9_]*=`) so the pinned AC command matches its own acceptance evidence. |
| 2 | nit | `.pre-commit-config.yaml:1`, `.prettierignore:11` | The `docs/` exclude (needed to avoid reformatting pre-existing content owned by other items) also exempts this item's own `plan.md`/`post-dev.md`, and every future item's backlog docs, from `trailing-whitespace`/`end-of-file-fixer`/Prettier going forward — not just the pre-existing files it was meant to protect. | Not blocking; consider scoping the exclude to specific pre-existing paths/a git-tracked-at-CQ-001 list instead of all of `docs/`, in a later item, if backlog-doc formatting drift becomes a problem. |
| 3 | nit | `apps/lo-console` / `packages/ui`, `pnpm -r run lint` output | `eslint-config-next`'s `no-html-link-for-pages` rule prints a cosmetic "Pages directory cannot be found" warning when linting the non-Next packages (`packages/ui`, `packages/api-client`). Already noted in this file's Follow-ups. | No action needed for this item; CQ-005 could scope the Next-specific ESLint extends to `apps/**` only if the noise becomes a problem. |

0 critical, 0 major, 1 minor, 2 nit.

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
