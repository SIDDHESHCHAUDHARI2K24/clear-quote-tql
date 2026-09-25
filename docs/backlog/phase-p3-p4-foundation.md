# P3/P4 foundation

Shared groundwork for the P3 (LO Tier A, CQ-016–020) and P4 (Borrower Tier
A, CQ-021–024) parallel build, per `docs/backlog/phase-p3-p4-plan.md`
(decisions D1, H3, H4). No backlog item owns this file; it's the unit that
runs before any CQ-016–024 worker starts.

## Decisions

- **D1 migration scope.** Landed exactly the four things
  `phase-p3-p4-plan.md` D1 names, in one migration
  (`alembic/versions/bbd0e3150264_p3p4_foundation.py`, `down_revision =
  642b3bc55d31`): `applications.last_pipeline_stage`,
  `applications.recommended_quote_id`, `quotes.stale`,
  `quote_package_versions`. Any later P3/P4 item needing its own schema
  change chains a new migration off this one — `alembic heads` must stay
  at exactly 1 head at every merge into `phase-p3-p4` (plan.md
  "Orchestration steps" #4).
- **FK cycle (`applications.recommended_quote_id` → `quotes.id`).**
  `applications → quotes` (via this column) and `quotes → scenarios →
  applications` (via `quotes.scenario_id` / `scenarios.application_id`)
  form a foreign-key cycle. `Base.metadata`'s topological sort — and a
  single `CREATE TABLE`/`ALTER TABLE` DDL script — can't express a cycle
  in one pass, so the FK is declared `use_alter=True` (with an explicit
  constraint name, `fk_applications_recommended_quote_id`) and the
  migration adds it as a separate `ALTER TABLE ... ADD CONSTRAINT` after
  both tables exist. Same convention as CQ-007's `quote_packages.
  recommended_quote_id → quotes.id` (no cycle there, so no `use_alter`
  needed on that one).
- **`quote_package_versions` vs. `quote_packages`.** Per plan.md D2,
  `quote_packages` stays the draft/working package (unchanged by this
  migration); `quote_package_versions` is the new table holding one frozen
  row per actual send — CQ-020 writes rows, CQ-022/CQ-024 read them by
  `report_token` (opaque; only *selects* a version, never a credential —
  plan.md H2). `(package_id, version)` is unique together (per-package
  version numbering); `report_token` is globally unique.
- **Every FK column is indexed.** Per `docs/design/system-design.md`'s
  table conventions (enforced by the existing
  `backend/tests/test_schema.py::test_every_fk_column_has_an_index`, which
  inspects the live migrated schema, not just the ORM models):
  `applications.recommended_quote_id` and
  `quote_package_versions.package_id`/`.report_token` are all indexed
  (the token's index comes from its `unique=True`).
- **Playwright version pin (H3).** The cached browser at
  `~/Library/Caches/ms-playwright/chromium-1234` is Playwright's internal
  Chromium build 1234. Checked `playwright-core`'s `browsers.json` across
  several recent releases (via `unpkg.com/playwright-core@<version>/
  browsers.json`) and found `1.62.0` is the exact match (chromium
  revision 1234, Chrome 151.0.7922.34) — pinned `@playwright/test` to
  `1.62.0` exactly (root `package.json`) so `pnpm exec playwright test`
  never re-downloads a browser.
- **Root TS config for `e2e/`.** Added a root `tsconfig.json` scoped to
  `playwright.config.ts` + `e2e/**/*.ts` only (excludes `apps`/`packages`,
  which keep their own configs) so `tsc --noEmit -p tsconfig.json` can
  typecheck the E2E code — `make lint`'s `pnpm -r run typecheck` only
  recurses into workspace member packages (`apps/*`, `packages/*`), never
  the repo root, so this isn't wired into `make lint` itself; verify it by
  hand (`pnpm exec tsc --noEmit -p tsconfig.json`). `pnpm exec prettier
  --check .` (already in `make lint`) does cover `e2e/`.
- **Deviation: seeded LO email.** The brief for this unit named
  `lo@clearquote.test` for the staff-login E2E proof. No such account
  exists — `seed/users.yaml` (CQ-010) seeds `jordan.lee@clearquote-demo.
  test` as the first LO ("Jordan Lee"). Used the real seeded address in
  `e2e/lo-console/staff-login.spec.ts` instead; logged here rather than
  guessing at a seed-data change out of this unit's scope.
- **`e2e` not in `make test`.** Per the brief: CI has no running stack
  (API, worker, two Next dev servers, Mailpit) for Playwright to talk to.
  `make e2e` exists as its own target; a worker runs it by hand per the
  recipe below.
- **Fresh-subagent review findings (both fixed).** A code-reviewer that
  didn't write this code flagged two issues against the documented
  multi-slot workflow above:
  1. `scripts/worktree-env.sh` was truncating each app's `.env.local` to
     exactly one line on every rerun, contradicting its own "safe to
     rerun" framing — a developer's manually added line would silently
     vanish next time anyone ran the script. Fixed by generalizing the
     root `.env`'s line-patching `set_kv` into `set_kv_in <file> <key>
     <value>` and using it for `.env.local` too, so a rerun only ever
     patches the one key/value pair it owns. Verified: added a manual
     `MANUAL_LINE=1` to `apps/lo-console/.env.local`, reran the script,
     confirmed the line survived.
  2. `e2e/helpers/mailpit.ts::readOtpCode` paged `/api/v1/messages?
     limit=50` (all mailboxes) and filtered client-side — under this same
     doc's documented "10 slots can run `make e2e` concurrently against
     one shared Mailpit," another slot's login traffic could push the
     target email past position 50 before this test's first poll,
     causing an intermittent false "no OTP" failure. Fixed by switching
     to Mailpit's `/api/v1/search?query=to:"<email>" subject:"<OTP
     subject>"` endpoint (confirmed against the live local Mailpit to
     return the same `{messages: [...]}` shape), which is scoped to the
     recipient's own mailbox instead of a global recency window.
     Re-verified end to end after the fix: `staff-login.spec.ts` still
     passes.

## What changed

**Backend**

- `alembic/versions/bbd0e3150264_p3p4_foundation.py` — the D1 migration
  (see Decisions). `down_revision = 642b3bc55d31` (the pre-unit head).
- `backend/app/features/applications/models.py` — `Application.
  last_pipeline_stage` (nullable `String`), `Application.
  recommended_quote_id` (nullable, indexed FK → `quotes.id`, `ON DELETE
  SET NULL`, `use_alter=True`).
- `backend/app/features/quotes/builder/models.py` — `Quote.stale`
  (`Boolean`, not null, `server_default=false()`).
- `backend/app/features/quotes/send/models.py` — new `QuotePackageVersion`
  model/table (`quote_package_versions`): `id`, `package_id` (FK →
  `quote_packages.id`, `ON DELETE CASCADE`, indexed), `version` (int,
  unique with `package_id`), `snapshot` (JSONB — the frozen
  `ReportViewModel`), `letter_key` (nullable), `report_token` (unique,
  indexed), `sent_at`, `expires_at`, `viewed_at` (nullable), `superseded`
  (bool, default false), `borrower_action` (JSONB, nullable),
  `created_at`.
- `backend/tests/test_schema.py` — added `"quote_package_versions"` to
  `EXPECTED_TABLES` (the existing FK-index and enum-value checks in this
  file cover the new columns/table automatically, since they inspect the
  live migrated DB).
- New model tests (TDD-first, all against the real migrated test DB via
  `backend/conftest.py`'s session-scoped `test_engine`):
  - `backend/app/features/applications/tests/test_models.py` —
    `last_pipeline_stage` default/settable; `recommended_quote_id`
    default/settable, `ON DELETE SET NULL` on the referenced quote's
    deletion, and rejects an unknown quote id (FK violation).
  - `backend/app/features/quotes/builder/tests/test_models.py` —
    `stale` server-side default `false`, and settable to `true`.
  - `backend/app/features/quotes/send/tests/test_models.py` — creates a
    version; `(package_id, version)` unique (rejects a duplicate, allows
    the same version number across two different packages);
    `report_token` globally unique; cascade-deletes with its package.
- `pyproject.toml` / `uv.lock` — added `weasyprint` and `jinja2` (H4).
  **Nothing in this unit imports `weasyprint`** (its native `pango`
  dependency isn't installed here — confirmed `import weasyprint` fails
  locally with `OSError: cannot load library 'libgobject-2.0-0'` until
  `brew install pango` runs); `uv sync` and the full backend test suite
  both pass with the dependency merely declared.

**Playwright / E2E (H3)**

- `playwright.config.ts` (root) — two projects, `lo-console` (baseURL
  `LO_BASE_URL`, default `http://localhost:3010`) and `borrower-portal`
  (baseURL `PORTAL_BASE_URL`, default `http://localhost:3020`).
- `e2e/lo-console/smoke.spec.ts`, `e2e/borrower-portal/smoke.spec.ts` —
  each asserts `/login` renders (heading, email/password fields, "Sign
  in" button).
- `e2e/lo-console/staff-login.spec.ts` — exercises `staffLogin` against a
  real seeded LO end to end (skipped when `SEED_STAFF_PASSWORD` is unset).
  Not one of the plan.md-required smoke specs, but proves the OTP helper
  actually works, per this unit's own E2E recipe.
- `e2e/helpers/mailpit.ts` — `readOtpCode(email)`: polls Mailpit's REST
  API (`GET /api/v1/messages`, `GET /api/v1/message/{id}`) for the newest
  "Your Clear Quote sign-in code" email to `email` and regexes the 6-digit
  code out of it. `MAILPIT_URL` env override, default
  `http://localhost:8025`.
- `e2e/helpers/staffLogin.ts`, `e2e/helpers/borrowerLogin.ts` — drive each
  app's shared `CredentialsForm`/`OtpForm` (`packages/ui/src/auth/`) by
  accessible label (`getByLabel("Email")` etc.) and button role/name, then
  wait for the post-OTP redirect.
- `package.json` (root) — `@playwright/test` pinned to `1.62.0`
  (workspace-root devDependency, matches the cached `chromium-1234`),
  `@types/node` added for the new root `tsconfig.json`.
- `tsconfig.json` (root, new) — scoped to `playwright.config.ts` +
  `e2e/**/*.ts`.
- `.gitignore` — `test-results/`, `playwright-report/`, `blob-report/`,
  `playwright/.cache/`.
- `Makefile` — `e2e` target: `pnpm exec playwright test`. **Not** added to
  `make test` (per the brief — CI has no running stack).
- Each app's `vitest.config.ts` already scopes `include` to
  `src/**/*.test.{ts,tsx}`, so `e2e/**/*.spec.ts` was already excluded
  from `pnpm -r run test` without any change needed — verified by running
  the full frontend suite after adding the E2E files.

**Per-worktree env (D1 continuation)**

- `scripts/worktree-env.sh <slot>` (new, executable) — see "How workers
  use it" below for behavior; idempotent, guards against ever targeting
  `cq_dev`/`cq_test`/`cq_dev_p2`/`cq_test_p2`.
- `backend/app/workflows/constants.py` already read
  `get_settings().temporal_task_queue` (not a hardcoded constant) before
  this unit touched anything — confirmed by reading it; no change needed
  there. `TEMPORAL_TASK_QUEUE` in `.env` is respected as-is by
  `scripts/worktree-env.sh`.

## Test log

| Check | Command | Result |
| --- | --- | --- |
| Migration upgrade (clean DB) | `uv run alembic upgrade head` (fresh `cq_dev_s1`/`cq_test_s1`) | OK — `... -> bbd0e3150264, p3p4 foundation` |
| Migration downgrade | `uv run alembic upgrade head` → `downgrade -1` → `upgrade head` | OK, no errors either direction |
| `alembic heads` | `uv run alembic heads` | `bbd0e3150264 (head)` — exactly one head |
| New model tests | `uv run pytest backend/app/features/applications/tests/test_models.py backend/app/features/quotes/builder/tests/test_models.py backend/app/features/quotes/send/tests/test_models.py backend/tests/test_schema.py -q` | 36 passed |
| Full backend suite | `uv run pytest backend -q` | 356 passed |
| `uv sync` (weasyprint/jinja2 declared, unimported) | `uv sync` | Resolved/checked clean; `import weasyprint` confirmed to fail without `pango` (expected, not imported anywhere) |
| `make lint` | `make lint` | ruff check/format, mypy (267 files), `pnpm -r run lint`/`typecheck` (4 packages), `pnpm exec prettier --check .` — all clean |
| `make test` | `make test` | pytest backend (356) + pytest seed (27) + `pnpm -r run test` (all 4 packages) — all green |
| Root TS check (not wired into `make lint`) | `pnpm exec tsc --noEmit -p tsconfig.json` | clean |
| `make demo-reset` | `time make demo-reset` | ~1.7s total (well under the 60s budget), migrates to `bbd0e3150264`, seeds 4 staff / 10 personas / 10 borrower accounts / 200 background applications |
| E2E (slot 1, full recipe) | `LO_BASE_URL=http://localhost:3101 PORTAL_BASE_URL=http://localhost:3201 SEED_STAFF_PASSWORD=<slot 1's> make e2e`, against `uv run uvicorn app.main:app --port 8101`, `pnpm --filter @cq/lo-console exec next dev -p 3101`, `pnpm --filter @cq/borrower-portal exec next dev -p 3201` | 3 passed: both smoke specs + `staff-login.spec.ts` (real Mailpit OTP round-trip against seeded `jordan.lee@clearquote-demo.test`) |

## How workers use it

**Slots.** `scripts/worktree-env.sh <slot>` (run once per worktree, safe
to rerun) writes/updates the repo-root `.env` and both apps' `.env.local`
for slot `N`:

| Setting | Value |
| --- | --- |
| `DATABASE_URL` | `cq_dev_s<N>` (created if missing) |
| `TEST_DATABASE_URL` | `cq_test_s<N>` (created if missing) |
| `VALKEY_URL` | db `<N+2>` |
| `TEMPORAL_TASK_QUEUE` | `cq-s<N>` |
| `CORS_ORIGINS` | `http://localhost:<3100+N>,http://localhost:<3200+N>` |
| API port | `8100+N` |
| LO Console port | `3100+N` |
| Borrower Portal port | `3200+N` |

It also generates `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` (Fernet format) and
`SEED_STAFF_PASSWORD`/`SEED_BORROWER_PASSWORD` if blank, and never
regenerates them once set (idempotent). It refuses to ever resolve to
`cq_dev`, `cq_test`, `cq_dev_p2` or `cq_test_p2` even for a slot number
that would otherwise collide (defensive check, not just documentation).
Slot assignment (from `phase-p3-p4-plan.md`): foundation=1, CQ-021=2,
CQ-016=3, CQ-022=4, CQ-017=5, CQ-023=6, CQ-024=7, CQ-018=8, CQ-019=9,
CQ-020=10.

Run it, then:

```
scripts/worktree-env.sh <slot>
uv run alembic upgrade head
make demo-reset
uv run uvicorn app.main:app --port <8100+N>          # in the background
pnpm --filter @cq/lo-console exec next dev -p <3100+N>       # in the background
pnpm --filter @cq/borrower-portal exec next dev -p <3200+N>  # in the background
LO_BASE_URL=http://localhost:<3100+N> PORTAL_BASE_URL=http://localhost:<3200+N> make e2e
```

**E2E helpers.** `e2e/helpers/staffLogin.ts` / `borrowerLogin.ts` drive
the shared login UI (`packages/ui/src/auth/CredentialsForm.tsx` +
`OtpForm.tsx`) the same way a real user would: fill by accessible label
(`Email`, `Password`, `Verification code`), click by button role/name
(`Sign in`, `Verify`), then read the OTP out of Mailpit
(`e2e/helpers/mailpit.ts::readOtpCode`, matching the exact subject both
`auth/staff/service.py` and `auth/borrower/service.py` use: "Your Clear
Quote sign-in code") and wait for the post-verify redirect. `borrowerLogin`
takes an optional `next`/`expectUrl` for CQ-022's `/login?next=/report/
{token}` flow. Each later item (CQ-016–024) writes its own specs under
`e2e/lo-console/` or `e2e/borrower-portal/` per its spec.md's ACs, and can
import these helpers directly (no re-implementation).

**New columns/table.**

- `applications.last_pipeline_stage`: CQ-016 sets this from the pipeline
  activities so the workspace summary can poll status without a Temporal
  round trip.
- `applications.recommended_quote_id`: CQ-018 sets/clears this (the one
  recommended quote for an application); it's automatically cleared (not
  a constraint violation) if that quote is later deleted.
- `quotes.stale`: CQ-017 sets this `true` when a field-value
  override/revert changes an input a quote was priced from; CQ-018's
  pricing panel/quote builder surfaces it as "needs reprice".
- `quote_package_versions`: CQ-020's send workflow inserts one row per
  actual send (never updates an old row — `superseded` flips `true` on
  the prior row instead). CQ-022 (borrower report) and CQ-024 (borrower
  actions) read a specific row by `report_token`; `expired` is computed
  at request time (`now > expires_at`), not stored.
