# CQ-005 — Post-development notes

## Summary

Both Next.js apps (`lo-console` on 3010, `borrower-portal` on 3020) now boot on Tailwind v4 with a shared token file and 9 pinned `@cq/ui` components (Button, MoneyInput, PercentInput, Table, Tabs, StatusPill, SourceBadge, Card, Overlay), each exported from `@cq/ui` and exercised on a `/gallery` route in both apps. `@cq/api-client` generates a typed client via `openapi-typescript` + `openapi-fetch` from a hand-written `packages/api-client/openapi.json` stub (CQ-004 does not exist yet); each app's `/` page calls `GET /health` through it and renders "API reachable"/"API unreachable" without throwing either way. `make api-client` finds CQ-004's export script when present and falls back to the stub otherwise, so no further Makefile edit is needed once CQ-004 lands.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `make api-client` runs `uv run python backend/scripts/export_openapi.py` then the generate script | The target now checks whether `backend/scripts/export_openapi.py` exists; if not, it skips straight to generation against the checked-in `packages/api-client/openapi.json` stub | CQ-004 (which creates that script) has not landed yet; this keeps `make api-client` usable today and self-heals once CQ-004 merges (Decision #1 in plan.md) |
| (implicit) Tailwind v4 zero-config content detection | Added explicit `@source "../../../../packages/ui/src";` to both apps' `globals.css` | Tailwind v4's automatic scan does not follow the `@cq/ui` workspace symlink into a sibling package; without it, utility classes used only inside `@cq/ui` components (e.g. `bg-navy-500`) never compile. Verified by inspecting the compiled CSS chunk for `/gallery` in both apps |
| (implicit) CSS comment style in tokens.css | No apostrophes/quote characters inside CSS comments; comments moved outside the `@theme` block | Lightning CSS's import bundler (used by `@tailwindcss/postcss`) mis-tokenizes apostrophes inside comments as unterminated string literals, and disallows comments inside `@theme` blocks — both caused hard build failures, not just warnings |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `/gallery` renders in both apps (`apps/lo-console/src/app/gallery/page.tsx`, `apps/borrower-portal/src/app/gallery/page.tsx`); gallery render tests green (see AC7); `npx react-doctor -y --blocking error` exit code 0, score 90/100, 1 non-blocking Accessibility warning, 0 errors |
| AC2 | Pass | `pnpm --filter lo-console dev` served `http://localhost:3010` (curl 200 on `/` and `/gallery`); `pnpm --filter borrower-portal dev` served `http://localhost:3020` (curl 200 on `/` and `/gallery`); both `tsconfig.json` have `"strict": true` (pre-existing from CQ-002, unchanged); `pnpm -r exec tsc --noEmit` — clean, no output |
| AC3 | Pass | `grep -n "\-\-color-navy-500\|\-\-color-sage-500\|\-\-status-danger" packages/ui/src/styles/tokens.css` matches all three; compiled CSS chunk for `/gallery` (both apps) contains `.bg-navy-500 { background-color: var(--color-navy-500); }` and `.text-status-danger { color: var(--color-status-danger); }` |
| AC4 | Pass | All 9 components exist under `packages/ui/src/components/<Name>/<Name>.tsx` with the pinned prop signatures, each with a co-located `.test.tsx`; all exported from `packages/ui/src/index.ts` (`@cq/ui`) |
| AC5 | Pass | `MoneyInput.test.tsx::"emits raw decimal string typed, never a number or reformatted string"` — types `1234.5`, asserts last `onChange` call is the string `"1234.5"`, never comma-formatted; `PercentInput.test.tsx::"emits raw decimal string typed, never a number"` — types `7.500`, asserts `"7.500"` |
| AC6 | Pass | `StatusPill.test.tsx::"renders every ApplicationStatus with its pinned tone"` iterates all 12 values against the pinned tone map; `SourceBadge.test.tsx::"renders every SourceBadgeSource, revert affordance only on lo_override"` iterates all 12 values, asserting the revert button exists only for `lo_override` |
| AC7 | Pass | `gallery/page.test.tsx` in both apps — one test rendering every component with ≥2 fixture states each (Button variants, MoneyInput filled/empty/invalid/sourced, PercentInput filled/empty, Table rows/empty state, all 12 StatusPill values, all 12 SourceBadge values, closed Overlay) |
| AC8 | Pass | `page.test.tsx` in both apps mocks `@cq/api-client`'s `createApiClient`; one test resolves `GET /health` → asserts "API reachable"; one test rejects the call → asserts render does not throw and shows "API unreachable" |
| AC9 | Pass | `make api-client` output: `api-client: backend/scripts/export_openapi.py not found yet (CQ-004) -- generating from the packages/api-client/openapi.json stub instead` then `openapi-typescript openapi.json -o src/schema.d.ts`; `head -1 packages/api-client/src/schema.d.ts` → `// GENERATED FILE — run \`make api-client\` to regenerate. Do not hand-edit.`; file is listed in `eslint.config.mjs` ignores and never hand-edited |
| AC10 | Pass | `pnpm -r test` — 4 projects, 10+2+2 test files, 34 tests, all green |
| AC11 | Pass | `npx react-doctor -y --blocking error` → exit code 0; Score 90/100 (Great); 1 Accessibility warning (Overlay vs. native `<dialog>`), 0 errors |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (placeholder, pre-existing) | `uv run pytest backend` | 1 passed |
| Frontend tests | `pnpm -r test` | 4 projects, 34 tests passed (packages/api-client: 1, packages/ui: 27, apps/lo-console: 3, apps/borrower-portal: 3) |
| Typecheck | `pnpm -r exec tsc --noEmit` | Clean, no output |
| ESLint | `pnpm -r run lint` | 0 errors (Next.js "Pages directory cannot be found" notices on non-Next packages are pre-existing config noise, not failures) |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| Full backend lint | `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app` | All pass (backend is still CQ-002's placeholder; unaffected by this item) |
| `make lint` | `make lint` | Exit 0, all steps pass |
| `make test` | `make test` | Exit 0, all steps pass |
| `make api-client` | `make api-client` | Exit 0; regenerates `packages/api-client/src/schema.d.ts` with the pinned banner |
| react-doctor | `npx react-doctor -y --blocking error` | Exit 0; Score 90/100; 1 warning, 0 errors |
| Dev servers | `pnpm --filter lo-console dev`, `pnpm --filter borrower-portal dev` | Both boot; `curl` 200 on `/` and `/gallery` for each; both stopped before finishing (`pkill -f "next dev -p 3010"` / `3020`), ports 3010/3020 confirmed free afterward |

## Review findings (stage 6)

_(left for the fresh-subagent reviewer — stage 6 has not run yet)_

| Severity | Finding | Resolution |
| --- | --- | --- |

## How to test manually

1. `pnpm install` at the repo root.
2. `pnpm --filter lo-console dev` (port 3010) and, in another terminal, `pnpm --filter borrower-portal dev` (port 3020).
3. Visit `http://localhost:3010/` and `http://localhost:3020/` — each shows "API unreachable" (no backend yet) without a crash.
4. Visit `http://localhost:3010/gallery` and `http://localhost:3020/gallery` — every component renders with its fixture states; try the Overlay open/close and Tabs click interactions.
5. `make api-client` — regenerates `packages/api-client/src/schema.d.ts` from the `openapi.json` stub (or from CQ-004's real export, once it exists).
6. `npx react-doctor -y --blocking error` from the repo root — score and findings.

## Follow-ups

- Overlay uses a custom backdrop+panel modal rather than the native `<dialog>` element (react-doctor `prefer-html-dialog`, warning-level only). Revisit when CQ-018 builds the real Add/Edit quote overlay on top of this primitive — watch for jsdom `HTMLDialogElement.showModal()` support before converting.
- CQ-004 must overwrite `packages/api-client/openapi.json` with the real `app.openapi()` export (its own scope); once that lands, `make api-client`'s existence-check branch simply stops triggering — no code change needed here.
- CQ-007 must keep `ApplicationStatus`/`SourceBadgeSource` string values in `packages/ui/src/types.ts` in sync with its Postgres enum values (already pinned identically in this item).
