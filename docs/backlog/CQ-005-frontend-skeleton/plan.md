# CQ-005 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

Gap-checked against spec.md; no big product gaps found. Small gaps decided below.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | CQ-004 doesn't exist yet, so `make api-client`'s first step (`export_openapi.py`) has nothing to export | Hand-write a minimal `packages/api-client/openapi.json` stub containing only `GET /health` in the exact response shape pinned in CQ-004's spec.md (`{status, checks: {database, valkey, minio, temporal}}`, 200/503). `make api-client` runs `openapi-typescript` against this stub (skipping the `uv run python backend/scripts/export_openapi.py` step, which fails today because the script doesn't exist). Once CQ-004 lands, its script overwrites this stub and regenerates the real client — no consumer code changes since the `/health` shape is pinned identically. |
| 2 | Decision | Makefile parallel-work boundary | Only the `api-client` target is edited in the Makefile (per orchestrator instructions); `up`/`down`/`logs` are CQ-003's. |
| 3 | Decision | `docs/backlog/README.md` | Not edited (orchestrator owns status updates); overrides the generic brief instruction to update it. |
| 4 | Decision | Tailwind v4 wiring for `@cq/ui` tokens | `packages/ui` ships `src/styles/tokens.css` with a package.json `exports` map (`"./styles/tokens.css": "./src/styles/tokens.css"`) so each app's `globals.css` can `@import "@cq/ui/styles/tokens.css";` then `@import "tailwindcss";`. Each app gets `tailwindcss` + `@tailwindcss/postcss` + `postcss.config.mjs`. |
| 5 | Decision | Vitest + React component testing | Add `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `@vitejs/plugin-react` to `packages/ui` and both apps; switch `vitest.config.ts` `environment` to `"jsdom"` and add a `vitest.setup.ts` importing `@testing-library/jest-dom`. |
| 6 | Decision | Dev ports | Confirmed no local process is bound to 3010/3020 before starting servers; apps' `package.json` `dev`/`start` scripts pin `next dev -p 3010` / `-p 3020` (env-independent, not left to Next's default 3000). |
| 7 | Decision | `NEXT_PUBLIC_API_URL` | Each app gets its own `.env.example` with `NEXT_PUBLIC_API_URL=http://localhost:8000`; `src/lib/api-client.ts` falls back to that same default so the placeholder home page works without `.env.local`. |
| 8 | Decision | Overlay component | Implemented as a controlled, dependency-free modal (fixed-position backdrop + panel, closes on backdrop click / Escape) — no portal library dependency needed for a P0 primitive; CQ-018 can swap internals later without changing `OverlayProps`. |

## Why

Both Next.js apps need to boot and prove the API pipe works, and every later screen (CQ-016+) is built from `@cq/ui` components whose props are contracts. This item ships the tokens, the 9 pinned components with fixture-driven galleries, and a generated typed API client so downstream items don't re-invent any of this.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Tokens | `packages/ui/src/styles/tokens.css`, `packages/ui/package.json` (exports) |
| Components | `packages/ui/src/components/{Button,MoneyInput,PercentInput,Table,Tabs,StatusPill,SourceBadge,Card,Overlay}/*.tsx` + `.test.tsx`, `packages/ui/src/types.ts` (ApplicationStatus, SourceBadgeSource), `packages/ui/src/index.ts` |
| api-client | `packages/api-client/openapi.json` (stub), `packages/api-client/src/schema.d.ts` (generated), `packages/api-client/src/client.ts`, `packages/api-client/src/index.ts`, `packages/api-client/package.json` (deps + generate script) |
| lo-console | `apps/lo-console/src/app/globals.css`, `layout.tsx`, `page.tsx`, `page.test.tsx`, `app/gallery/page.tsx` + test, `src/lib/api-client.ts`, `postcss.config.mjs`, `.env.example`, `package.json`, `vitest.config.ts`, `vitest.setup.ts` |
| borrower-portal | same set mirrored |
| Root | `Makefile` (`api-client` target only) |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Tokens + Tailwind wiring in `@cq/ui` | — | `packages/ui/src/styles/tokens.css`, `packages/ui/package.json` | AC3 grep |
| T2 | Types (`ApplicationStatus`, `SourceBadgeSource`) | — | `packages/ui/src/types.ts` | compiled by component tests |
| T3 | Button, Card, Overlay | T1 | `packages/ui/src/components/{Button,Card,Overlay}/*` | render tests |
| T4 | MoneyInput, PercentInput | T1, T2 | `packages/ui/src/components/{MoneyInput,PercentInput}/*` | raw-decimal-string tests (AC5) |
| T5 | Table, Tabs | T1 | `packages/ui/src/components/{Table,Tabs}/*` | render tests |
| T6 | StatusPill, SourceBadge | T1, T2 | `packages/ui/src/components/{StatusPill,SourceBadge}/*` | all-12-values tests (AC6) |
| T7 | `@cq/ui` index exports | T3–T6 | `packages/ui/src/index.ts` | import smoke test |
| T8 | api-client stub + generation | — | `packages/api-client/openapi.json`, `src/schema.d.ts`, `src/client.ts`, `src/index.ts` | AC9 |
| T9 | lo-console: globals.css, layout, home page, api-client wiring | T1, T8 | `apps/lo-console/src/{app/{globals.css,layout.tsx,page.tsx,page.test.tsx},lib/api-client.ts}` | AC8 |
| T10 | borrower-portal: mirror T9 | T1, T8 | same paths under `apps/borrower-portal` | AC8 |
| T11 | lo-console `/gallery` | T7 | `apps/lo-console/src/app/gallery/{page.tsx,page.test.tsx}` | AC7 |
| T12 | borrower-portal `/gallery` | T7 | `apps/borrower-portal/src/app/gallery/{page.tsx,page.test.tsx}` | AC7 |
| T13 | Makefile `api-client` target | T8 | `Makefile` | AC9 |
| T14 | Full verification pass | T1–T13 | — | AC2, AC10, AC11 |

## Wave schedule (stage 3)

Single-agent sequential execution (no parallel subagents dispatched — the component set is small and tightly coupled through shared tokens/types). Order: T1, T2 → T3–T6 (components) → T7 → T8 → T9, T10 → T11, T12 → T13 → T14.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `pnpm --filter lo-console test`, `pnpm --filter borrower-portal test` (gallery render tests) + `npx react-doctor -y --blocking error` |
| AC2 | `pnpm --filter lo-console dev` / `pnpm --filter borrower-portal dev` manual boot; `pnpm -r exec tsc --noEmit` |
| AC3 | `grep -n "\-\-color-navy-500\|\-\-color-sage-500\|\-\-status-danger" packages/ui/src/styles/tokens.css` |
| AC4 | one `.test.tsx` per component under `packages/ui/src/components/**` |
| AC5 | `MoneyInput.test.tsx`, `PercentInput.test.tsx` — "emits raw decimal string" |
| AC6 | `StatusPill.test.tsx`, `SourceBadge.test.tsx` — all values + revert-only-on-lo_override |
| AC7 | `gallery/page.test.tsx` in both apps |
| AC8 | `page.test.tsx` in both apps, mocked `@cq/api-client` |
| AC9 | `make api-client`; `head -1 packages/api-client/src/schema.d.ts` |
| AC10 | `pnpm -r test` |
| AC11 | `npx react-doctor -y --blocking error` |

## Progress

- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [x] T6  - [x] T7
- [x] T8  - [x] T9  - [x] T10 - [x] T11 - [x] T12 - [x] T13 - [x] T14

## Notes from execution

- Tailwind v4 build (Lightning CSS) failed with "Unterminated string" /
  "@theme blocks must only contain custom properties" errors caused by
  apostrophes and comments inside the `@theme` block in `tokens.css`.
  Fixed by moving all explanatory comments outside `@theme` and removing
  apostrophes/quote characters from CSS comments entirely (an
  undocumented Lightning CSS/Tailwind v4 import-bundler quirk).
- Tailwind v4's automatic content (class-usage) detection only scans each
  app's own directory tree; it does not follow the `@cq/ui` workspace
  symlink into `packages/ui/src`. Added an explicit
  `@source "../../../../packages/ui/src";` to each app's `globals.css` so
  utility classes used only inside `@cq/ui` components (e.g. `bg-navy-500`)
  are generated. Verified by inspecting the compiled CSS chunk for both
  apps' `/gallery` route.
- `next dev` regenerates `next-env.d.ts` with a triple-slash reference to
  `.next/types/routes.d.ts` on Next.js 15.5, which trips
  `@typescript-eslint/triple-slash-reference`. Added `**/next-env.d.ts` to
  `eslint.config.mjs` ignores (the file says "should not be edited" and is
  regenerated by Next on every dev/build run).
- `react-doctor` flagged one Accessibility warning (Overlay: "prefer
  html-dialog" over a custom backdrop+panel modal) — left as-is; switching
  to native `<dialog>` risks jsdom `showModal()` incompatibilities in tests
  for a warning-level, non-blocking finding. Logged as a follow-up.
