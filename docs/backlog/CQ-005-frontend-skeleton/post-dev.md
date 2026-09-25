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

Fresh-subagent review, 2026-09-25. Verdict: **APPROVE** (no critical/major findings).

Re-ran verification (all pass, matching the claims in this file):

| Command | Result |
| --- | --- |
| `pnpm -r test` | 4 projects, 10 test files, 34 tests, all green |
| `pnpm -r exec tsc --noEmit` | Clean, no output |
| `pnpm -r run lint` (eslint) | 0 errors (same pre-existing "Pages directory cannot be found" notices on non-Next packages) |
| `pnpm exec prettier --check .` | All matched files use Prettier code style |
| `npx react-doctor -y --blocking error` | Exit 0; Score 90/100; 1 Accessibility warning (`prefer-html-dialog` on `Overlay.tsx:43`), 0 errors |
| `make lint` | Exit 0 (ruff, ruff format, mypy, eslint, tsc, prettier all pass) |
| `make test` | Exit 0 (pytest + `pnpm -r test`) |
| `make api-client` | Exit 0; prints the "not found yet (CQ-004)" fallback line, regenerates `schema.d.ts` from the checked-in stub with the pinned `// GENERATED FILE` banner intact; `git status` shows no diff after regeneration (output is reproducible / not hand-edited) |
| `pnpm --filter lo-console dev` + `curl localhost:3010/`, `/gallery` | Both 200 |
| `pnpm --filter borrower-portal dev` + `curl localhost:3020/`, `/gallery` | Both 200 |
| `grep -- "--color-navy-500\|--color-sage-500\|--status-danger" tokens.css` | All 3 present (AC3) |
| Dev servers stopped afterward | Confirmed ports 3010/3020 free |

Spot-checked contracts: `ApplicationStatus` (12 values) and `SourceBadgeSource`/`FieldSource` (12 values) in `packages/ui/src/types.ts` match `docs/backlog/CQ-007-data-model/spec.md` lines 40 and 50 exactly, including the `StatusPill` tone map. The `/health` OpenAPI stub's shape (`status`/`checks.{database,valkey,minio,temporal}`, 200/503) matches `docs/backlog/CQ-004-backend-skeleton/spec.md`'s pinned response body exactly. `make api-client`'s fallback (Makefile lines checking for `backend/scripts/export_openapi.py`) will switch to the real export automatically once CQ-004 lands — no code change needed, confirmed by reading the Makefile logic. Grepped the whole frontend tree for `parseFloat`/`parseInt`/`Number(` — none found; `MoneyInput`/`PercentInput` only ever pass through the raw string from `e.target.value`, confirmed by their tests asserting the exact typed string with no reformatting.

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `packages/ui/src/components/Overlay/Overlay.tsx:22-67` | `Overlay` implements Escape-to-close but has no focus trap: `Tab`/`Shift+Tab` can move focus to elements behind the backdrop, and focus is not moved into the dialog on open or restored to the trigger on close. Not covered by react-doctor (which only flagged `prefer-html-dialog`) or by `Overlay.test.tsx`. Not an AC violation today (AC4 only pins the prop signature), but CQ-018 builds the real Add/Edit quote overlay on top of this primitive, so the gap should be closed before then. | Add a simple focus trap (move focus to the panel/first focusable child on open, cycle Tab/Shift+Tab within the dialog, restore focus to the trigger element on close) or adopt native `<dialog>`/`showModal()` per react-doctor's suggestion. |
| 2 | minor | `packages/ui/src/components/Overlay/Overlay.test.tsx` | No test asserts that pressing `Escape` calls `onClose`, even though the component implements it (`Overlay.tsx:25-27`). | Add a `userEvent.keyboard("{Escape}")` test. |
| 3 | minor | `packages/ui/src/components/Tabs/Tabs.tsx:39-67` | Tabs use `role="tablist"`/`role="tab"` but every tab is a separately-tabbable native `<button>` with no roving-tabindex/arrow-key navigation, so the implementation doesn't match the ARIA tabs authoring pattern implied by those roles (screen readers may announce arrow-key support that isn't there). Keyboard operation still works via `Tab` + `Enter`/`Space` (native button semantics). | Add left/right arrow-key handling with a single tabbable tab (roving `tabIndex`), or drop the `tablist`/`tab` roles if the simpler interaction model is intentional for P0. |
| 4 | minor | `apps/lo-console/src/app/page.tsx:18-25`, `apps/borrower-portal/src/app/page.tsx` (same) | `api.GET("/health")` resolves (does not reject) on a `503` "degraded" response from `openapi-fetch`, since only network-level failures reject the promise. The `.then()` branch runs for any resolved response, so a degraded backend would still render "API reachable." AC8 only requires "reachable"/"unreachable" without throwing regardless of whether the backend is running, and both existing tests (resolved 200 / rejected network error) pass, so this isn't an AC failure — but it's a latent correctness gap for later screens that display health status. | Check the response's `error`/`response.ok` (or HTTP status) before deciding "reachable," not just promise resolution. |
| 5 | nit | `apps/lo-console/src/app/gallery/page.test.tsx:42-44` (and borrower-portal's copy) | The gallery integration test asserts only that "Encompass" text is present and that `SOURCE_BADGE_SOURCES.length === 12`, rather than asserting all 12 source labels are actually rendered (unlike the `StatusPill` loop directly above it). AC6's dedicated `SourceBadge.test.tsx` already covers all 12 values at the unit level, so this doesn't leave AC7 unverified overall, just weaker than it looks. | Loop over `SOURCE_BADGE_SOURCES` the same way the `StatusPill` assertion above it does. |

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
