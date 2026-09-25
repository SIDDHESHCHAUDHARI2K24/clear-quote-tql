# CQ-021 — Post-development notes

## Summary

Built the one `ReportViewModel` contract (Pydantic schema + pure `build_report_view_model`
builder, `backend/app/features/quotes/report/`) and the one set of report components
(`packages/ui/src/report/`) that CQ-019 (LO preview) and CQ-022 (borrower report) will both
render. `ReportViewModel` is registered as an OpenAPI component (no throwaway endpoint) so
`make api-client` generates its TypeScript type, which every component takes as its props type.
Six fixtures (Marcus Hale STR, Marcus Hale expired, Kathleen McReynolds LTR/TBD, Priya Nair
primary, Priya Nair superseded, Daniel Ortiz primary-with-MI) are built by a script that runs
the real `quote_engine` on each persona's seeded inputs — no number is hand-typed. Both apps'
`/gallery/report` pages render every fixture through a composed `ReportPage` component; verified
live in a headless browser with zero console errors/warnings on either app.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Gallery at `/_gallery/report` | `/gallery/report` | Both apps already have a `/gallery` route and `middleware.ts` `PUBLIC_PATHS` entry (CQ-005); followed that existing convention instead of introducing a second, differently-named public route. See plan.md Decision 5. |
| A staff-auth schema endpoint was called out as "not ideal" | Registered `ReportViewModel` as an OpenAPI `components/schemas` entry via `app.openapi` override (`backend/app/main.py::_register_report_view_model_schema`), no endpoint at all | Matches the spec's own steer toward "the least-invasive way ... prefer registering the model as a component." See plan.md Decision 1. |
| — (not specified) | `packages/ui` now depends on `@cq/api-client` (`workspace:*`) | Needed so report components can import `components["schemas"]["ReportViewModel"]` as their props type per spec's "generated TypeScript type ... is the component props type." Not circular. See plan.md Decision 3. |
| — (not specified) | `ReportOptionInput` carries `str_gross_annual_revenue` and `down_payment_pct`/`note_rate`/`discount_points_pct` alongside `QuoteComputation` | `QuoteComputation` doesn't expose the raw pre-expense-ratio STR revenue, the down-payment amount, or the scenario's note rate/points — only their downstream effects. The builder needs these for display (cashflow table's "gross" row, rate/points labels, down-payment breakdown line). See plan.md Decision 2 and builder.py's `_down_payment_amount`/`_gross_rent_monthly` docstrings. |
| AC6's Playwright spec `e2e/report-gallery.spec.ts` | Not added on this branch | No `playwright.config.ts` exists yet — the foundation unit sets it up in parallel and this branch was cut from `phase-p3-p4` before that merged, per the coordinator's own instructions ("Your AC6 e2e spec can't run until then"). Substituted: (1) Vitest console.error/warn spy tests in both apps' `page.test.tsx`, (2) a real headless-Chromium check (ad hoc, not committed — see "How to test manually") confirming zero console errors/warnings and the AC2/AC4 behaviors live. The coordinator should add the committed Playwright spec once the foundation unit merges. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/quotes/report/tests/test_builder.py::test_view_model_marcus_hale` — asserts P&I `"1913.05"`, `year1_tax_savings == "24275.78"`, `year1_tax_savings_monthly == "2023"`, negative STR cashflow. `packages/ui/src/report/HeroNumbers.test.tsx` asserts the rendered strings `"$24,276"` and `"≈ $2,023/mo"` and that the cashflow tile carries `text-status-danger`. Live screenshot: `evidence/lo-console-gallery-report.png` (Marcus Hale section). |
| AC2 | Met | `packages/ui/src/report/HeroNumbers.test.tsx` (Priya: exactly 3 `[data-testid="hero-numbers"] > div` tiles, no DSCR/cashflow/tax-savings text). `packages/ui/src/report/ReportGallery.primary-gating.test.tsx` (full-`ReportPage` DOM scan for Priya *and* Daniel-with-MI, both collapsibles expanded, asserts none of DSCR/cashflow/cap rate/cost segregation/prepayment penalty/tax savings/tax advice/rental income appear anywhere). Live-browser check (see below) independently confirms 3 tiles + no DSCR/cashflow text for Priya on the real rendered page. |
| AC3 | Met | `backend/.../test_builder.py::test_view_model_kathleen_mcreynolds_ltr_tbd` (`header.property_label == "Property to be determined"`, `cashflow.rent_label == "Market rent (LTR)"`). `ReportGallery.primary-gating.test.tsx` asserts `"Property to be determined"` renders and `/\bSTR\b/` never appears anywhere on Kathleen's page. Screenshot: `evidence/lo-console-gallery-report.png` (Kathleen section). |
| AC4 | Met | `backend/.../test_builder.py::test_switching_option_values_come_straight_from_the_fixture` (par vs. buydown differ; P&I is exactly the fixture's own value, not recomputed). `OptionSwitcher.test.tsx` (click updates selection). `ReportGallery.primary-gating.test.tsx` (clicking Buydown changes the rendered breakdown's P&I line to buydown's own fixture amount, old value gone). Live-browser check: hero-numbers block text differs before/after clicking the Buydown pill on the real page (see "How to test manually"). |
| AC5 | Met | `packages/ui/src/report/report-no-money-math.test.ts` — scans all 11 owned `.tsx` files (excludes `format.ts`/`types.ts`, the sanctioned formatters) for an arithmetic operator adjacent to a `ReportViewModel` field-path access; 0 matches. Approach documented in plan.md Decision 4 and the test file's own header comment. |
| AC6 | Partially automated, manually verified | react-doctor: `npx react-doctor -y --blocking error` on both apps — 2 pre-existing warnings, both in `src/app/page.tsx` (untouched by this item, not in `gallery/report`); 0 new findings. WCAG contrast: `text-status-danger` (`#c1392b`) on white = **5.40:1** (≥ 4.5:1 AA), computed directly from the token value (see calculation in plan.md's test-map row). Console errors: `apps/*/src/app/gallery/report/page.test.tsx` (Vitest `console.error`/`console.warn` spies, 0 calls) **and** a real headless-Chromium run against both dev servers on ports 3102/3202 — 0 console error/warning messages on either `/gallery/report` page (see "How to test manually" for the exact reproduction). Committed Playwright spec deferred — see Deviations. |
| AC7 | Met | `packages/ui/src/report/__fixtures__/view-model.types.test.ts` — every fixture narrows from `unknown` to `ReportViewModelData` via a runtime-checked type assertion (catches a wrong/missing `strategy`, not just a silent `as`), then a Vitest smoke assertion. `tsc --noEmit` is clean repo-wide (`pnpm -r run typecheck`), which is the actual compile-time enforcement. Verified `make api-client`'s generated `components["schemas"]["ReportViewModel"]` in `packages/api-client/src/schema.d.ts` matches the Pydantic schema field-for-field (spot-checked, see plan.md Decision 1). |

Screenshots: `docs/backlog/CQ-021-report-components/evidence/lo-console-gallery-report.png` (full page, all 6 fixtures), `borrower-portal-gallery-report.png` (same, other app), `borrower-portal-gallery-report-mobile.png` (390px viewport).

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (whole suite) | `uv run pytest backend` | 349 passed |
| Seed tests | `uv run pytest seed` | 27 passed |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 271 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 271 source files |
| Frontend tests (whole monorepo) | `pnpm -r run test` | 4/4 workspaces passed — api-client 2, ui 94, lo-console 21, borrower-portal 37 (154 total) |
| ESLint (whole monorepo) | `pnpm -r run lint` | 0 errors (2 informational eslint-config-next notices, pre-existing/expected for non-pages-router apps) |
| TypeScript (whole monorepo) | `pnpm -r run typecheck` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| react-doctor (lo-console) | `npx react-doctor -y --blocking error` | Score 83/100; 2 warnings, both pre-existing in `src/app/page.tsx` (not touched by this item) |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | Score 83/100; 2 warnings, both pre-existing in `src/app/page.tsx` (not touched by this item) |
| graphify | `graphify update .` | Rebuilt: 4103 nodes, 8586 edges, 384 communities |

`make api-client` was run once, mid-development, to regenerate `packages/api-client/{openapi.json,src/schema.d.ts}` after `ReportViewModel` was registered — verified `ReportViewModel` (and its 12 referenced sub-schemas) appear in the generated TypeScript.

## Review findings (stage 6)

Ran the `code-review` skill (medium effort) as a fresh, isolated pass over the full uncommitted diff (this worker's own session did not carry review context into that fork). No critical/major findings; 2 minor findings, both resolved or explicitly accepted:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Minor | `builder.py`'s `_down_payment_amount`/`_gross_rent_monthly` do Decimal math outside `quote_engine`, against AGENTS.md's "Money math lives only in `quote_engine`" rule read literally | Accepted as-is — already documented as a deliberate decision (plan.md Decision 2) with a concrete follow-up (add `down_payment_amount` to `QuoteComputation`). Both derivations only operate on already-engine-produced or raw-provider decimals, mirror math `quote_engine` itself already performs elsewhere, and are docstring-justified at the call site. Re-reviewed after the reviewer flagged it; judged non-blocking because the rule's intent (per AGENTS.md's own phrasing, paired with "Frontends never compute money") is aimed at frontend recomputation of engine numbers, not narrow backend display derivations of values the engine computed internally but didn't expose. |
| Minor | `ExplainerCards.tsx` hand-wrote 6 near-identical row blocks instead of the row-array + `.map()` pattern `CashflowTable.tsx`/`CostSegTable.tsx` already use | Fixed — refactored to a shared `RowList`/`Row[]` pattern matching the sibling components; re-ran `vitest`/`tsc`/`eslint`/`prettier` for `packages/ui`, all green (94/94 tests). |

The coordinator's own fresh-subagent review (a separate reviewer who did not write this code, per AGENTS.md's stage 6) is still expected before merge — this session's `code-review` pass is this worker's own stage-5/6 self-check, not a substitute for that.

## How to test manually

1. `cd` to this worktree; `.env` already points at slot-2 DBs/ports (see the worktree's own `.env`, not committed).
2. Backend: `uv run pytest backend/app/features/quotes/report -q` (5 tests) — or `uv run pytest backend seed -q` for everything.
3. Fixtures: `uv run python backend/scripts/build_report_fixtures.py` regenerates the 6 JSON files under `packages/ui/src/report/__fixtures__/`.
4. Frontend: `cd packages/ui && pnpm exec vitest run` (94 tests, includes AC1–AC5, AC7).
5. Live browser: `pnpm --filter @cq/lo-console exec next dev -p 3102 &` and `pnpm --filter @cq/borrower-portal exec next dev -p 3202 &`, then open `http://localhost:3102/gallery/report` and `http://localhost:3202/gallery/report`. Confirm: Marcus Hale shows red `-$709` cashflow and `$24,276` / `≈ $2,023/mo` tax savings; Priya Nair shows exactly 3 tiles with no DSCR/cashflow text; Kathleen McReynolds shows "Property to be determined" and no "STR" text; clicking the Buydown pill on any investment fixture changes every hero number and (once "See the full breakdown" is expanded) the breakdown table. Kill both dev servers (`lsof -ti:3102,3202 | xargs kill`) when done.

## Follow-ups

- Add `down_payment_amount` to `QuoteComputation` (backend/app/features/pricing/engine/types.py) so `builder.py::_down_payment_amount` doesn't need to reconstruct it via subtraction (see plan.md Decision 2).
- Add the committed `e2e/report-gallery.spec.ts` Playwright spec (console errors, axe, react-doctor via CI) once the foundation unit's Playwright setup merges into `phase-p3-p4` — the coordinator owns this follow-up per the worker instructions.
- CQ-023 will widen/replace `ReportMatch`'s placeholder shape (backend/app/features/quotes/report/schemas.py) and build `MatchCard.tsx`/`MatchList.tsx`/`ReportMatchesSlot.tsx`; `ReportPage.tsx` currently renders nothing for `matches` (always `[]` today) and will need a slot added for that, per phase-p3-p4-plan.md Decision D3.
