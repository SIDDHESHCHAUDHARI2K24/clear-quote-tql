# CQ-021 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | How does `ReportViewModel` reach `make api-client` with no DB-backed endpoint yet | `backend/app/main.py::_register_report_view_model_schema` overrides `app.openapi` to merge `ReportViewModel`'s (and every model it references) `components/schemas` entries into the generated OpenAPI dict, via `schemas.report_view_model_openapi_components()` (`ReportViewModel.model_json_schema(ref_template=...)`, splitting `$defs` into top-level components). No throwaway endpoint (spec.md explicitly calls that "not ideal"). Verified: `app.openapi()["components"]["schemas"]["ReportViewModel"]` is present, and `make api-client` generates the matching `components["schemas"]["ReportViewModel"]` TS type byte-for-byte. |
| 2 | Decision | `builder.py` derives two values `QuoteComputation` doesn't expose (`down_payment_amount = purchase_price - loan_amount`; STR "gross" monthly revenue = `str_gross_annual_revenue / 12`) | AGENTS.md's "money math lives only in quote_engine" rule targets *frontend* recomputation of engine numbers; these two Python-side derivations only ever operate on already-engine-produced or raw-provider decimals, mirror math the engine itself already does elsewhere (`down_payment` is computed internally by `compute_quote` but not returned; the `/12` conversion mirrors `underwritten_str_rent`'s own math), and are documented on `_down_payment_amount`/`_gross_rent_monthly` in builder.py. Follow-up filed in "Follow-ups" below: add `down_payment_amount` to `QuoteComputation` directly so no consumer needs this helper. |
| 3 | Decision | `packages/ui` depends on `@cq/api-client` | Spec.md: "The generated TypeScript type from the api-client is the component props type." Added `"@cq/api-client": "workspace:*"` to `packages/ui/package.json` dependencies. Not circular (api-client has no `@cq/ui` dependency). |
| 4 | Decision (AC5 approach) | Static "no money math" check | A Vitest scan test (`packages/ui/src/report/report-no-money-math.test.ts`), not a custom eslint rule — no project-local eslint rule package/build step existed to hang a new rule off, and a scan test runs in the same `pnpm test` pass everything else does. Approach: for every `*.ts(x)` file this item owns (excluding tests, `format.ts`, `types.ts`), strip string/template literals and comments (so Tailwind classes like `px-4` and prose never false-positive), then regex-match an arithmetic operator (`+ - * /`) directly adjacent to a `ReportViewModel` field-path access (`option.hero.…`, `Number(...)`). Heuristic, not a full parser — documented in the test file's header comment. All 11 non-excluded files pass with zero matches today. |
| 5 | Decision | Gallery route path | Followed the existing `/gallery` convention (both apps' `src/app/gallery/page.tsx` already exist and `/gallery` is public in `middleware.ts`) instead of spec's literal `/_gallery/report` — added `/gallery/report/page.tsx` in both apps and added `/gallery/report` to each `middleware.ts`'s `PUBLIC_PATHS` (exact-match only; `isPublicPath` doesn't prefix-match `/gallery/*`). |
| 6 | Decision | `matches[]` element type | Spec says "empty here; filled by CQ-023" but doesn't pin a shape. Added a minimal `ReportMatch` schema (data-field-catalog §11 subset: id, image, address, bed/bath/sqft, deal grade, tagline, price) so `ReportViewModel`'s top-level shape is concrete today; CQ-023 (D3, phase-p3-p4-plan.md) can widen/adjust this schema without touching anything else in `ReportViewModel`. |
| 7 | Decision | `ReportPage.tsx` (not in spec.md's component table) | Added one composed component (`packages/ui/src/report/ReportPage.tsx`) that assembles every owned component in system-design.md's "Quote report" order, holding the `OptionSwitcher` selection state. Both apps' `/gallery/report` pages render it once per fixture (satisfies "renders every component with each fixture" structurally); CQ-019/CQ-022 can render the same component later so the LO preview and borrower report can never structurally diverge — spec.md's stated goal for this item. |
| 8 | Decision | Fixture note-rate/tax-rate/revenue inputs | Marcus Hale's par option uses purchase price $342,000 / 20% down / 7.500% note rate with `ConfigSnapshot()` defaults — the exact `test_golden.py` STR scenario — so AC1's pinned P&I ($1,913.05) and year-1 tax savings ($24,275.78) reproduce exactly. Tax/insurance/STR-revenue/market-rent inputs for all 4 personas come from the real seed provider tables (`seed/providers/tax_rates.yaml`, `str_revenue.yaml`, `rents.yaml`, keyed by each persona's county/zip), not hand-picked, per spec's "seed-independent fixtures ... built by running quote_engine on their persona inputs." |

No big gaps found; nothing raised in Kaneo.

## Why

CQ-019 (LO preview) and CQ-022 (borrower report) both need to render the exact same numbers from the exact same components, per system-design.md principle 3 ("One calculation engine ... the LO preview, borrower report and PDFs render the same numbers") and this item's own charter ("If the LO preview and the borrower page ever differ, it is a bug in this item's contract"). This item builds that one contract (`ReportViewModel` + pure builder) and the one set of presentation components, with fixtures built by the real engine (never hand-typed), so downstream items only ever map their own data into `ReportInputs` and render `ReportPage` — they can't accidentally diverge.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend contract | `backend/app/features/quotes/report/{inputs,schemas,builder}.py`, `tests/test_builder.py` (new) |
| OpenAPI wiring | `backend/app/main.py` (modified: `_register_report_view_model_schema`) |
| Fixtures | `backend/scripts/build_report_fixtures.py` (new), `packages/ui/src/report/__fixtures__/*.json` (generated) |
| Frontend components | `packages/ui/src/report/*.tsx` (11 components + `ReportPage`), `format.ts`, `types.ts`, `fixtures.ts` (new) |
| Frontend tests | `packages/ui/src/report/*.test.ts(x)` (new) |
| Barrel export | `packages/ui/src/index.ts` (modified) |
| Package deps | `packages/ui/package.json` (modified: add `@cq/api-client`) |
| Gallery pages | `apps/lo-console/src/app/gallery/report/page.tsx` (+`page.test.tsx`), `apps/borrower-portal/src/app/gallery/report/page.tsx` (+`page.test.tsx`) (new) |
| Middleware | `apps/lo-console/src/middleware.ts`, `apps/borrower-portal/src/middleware.ts` (modified: add `/gallery/report` to `PUBLIC_PATHS`) |
| Generated | `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts` (regenerated via `make api-client`) |

No DB migrations (the builder does not read the DB, per spec.md and this item's charter).

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | `ReportInputs`/`ReportOptionInput`/`ReportMatchInput` dataclasses | — | `report/inputs.py` | exercised by T2's tests |
| T2 | `ReportViewModel` Pydantic schema + OpenAPI component registration | T1 | `report/schemas.py`, `main.py` | `app.openapi()` contains `ReportViewModel` (verified manually + via `make api-client` diff) |
| T3 | `build_report_view_model` pure builder | T1, T2 | `report/builder.py` | `test_builder.py` (5 tests: Marcus Hale, Kathleen, Priya, Daniel/ordering, AC4 switching) |
| T4 | Fixture generator script | T3 | `scripts/build_report_fixtures.py` | run manually; asserted against by frontend type/AC1 tests |
| T5 | `make api-client` regen | T2 | `packages/api-client/*` (generated) | `pnpm --filter @cq/api-client test` |
| T6 | Format helpers + types re-export | T5 | `report/format.ts`, `report/types.ts` | exercised by component tests |
| T7 | 11 components + `ReportPage` | T6 | `report/*.tsx` | component tests below |
| T8 | AC5 scan test | T7 | `report/report-no-money-math.test.ts` | itself |
| T9 | AC7 type test | T5, T4 | `report/__fixtures__/view-model.types.test.ts` | itself (+ `tsc --noEmit`) |
| T10 | Barrel export + `@cq/api-client` dep | T7 | `index.ts`, `package.json` | `index.test.ts` (existing, unmodified — still green) |
| T11 | Gallery pages + middleware | T10 | `apps/*/src/app/gallery/report/*`, `apps/*/src/middleware.ts` | `page.test.tsx` ×2, `middleware.test.ts` (existing, unmodified — still green) |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Contract/schema first |
| 2 | T3 | Builder depends on the contract |
| 3 | T4, T5 | Fixtures need the builder; api-client regen needs the schema registered |
| 4 | T6, T7, T8 | Components need the generated type + fixtures |
| 5 | T9, T10, T11 | Type test needs fixtures + generated type; gallery needs components + barrel export |

(Executed serially in one session rather than literally parallel subagents — the whole item is one cohesive contract-then-consumer chain with no independent workstreams worth splitting across agents.)

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/quotes/report/tests/test_builder.py::test_view_model_marcus_hale`; `packages/ui/src/report/HeroNumbers.test.tsx` ("AC1: Marcus Hale's par option...") |
| AC2 | `packages/ui/src/report/HeroNumbers.test.tsx` ("AC2: Priya Nair's (primary) hero..."); `packages/ui/src/report/ReportGallery.primary-gating.test.tsx` (full-page DOM scan, both Priya and Daniel/MI) |
| AC3 | `backend/.../test_builder.py::test_view_model_kathleen_mcreynolds_ltr_tbd`; `packages/ui/src/report/ReportGallery.primary-gating.test.tsx` ("AC3: Kathleen McReynolds...") |
| AC4 | `backend/.../test_builder.py::test_switching_option_values_come_straight_from_the_fixture`; `packages/ui/src/report/OptionSwitcher.test.tsx`; `packages/ui/src/report/ReportGallery.primary-gating.test.tsx` ("AC4: switching options...") |
| AC5 | `packages/ui/src/report/report-no-money-math.test.ts` |
| AC6 | `apps/lo-console/src/app/gallery/report/page.test.tsx`, `apps/borrower-portal/.../page.test.tsx` (console.error/warn spy, Vitest-level today); `react-doctor` (0 new findings — see post-dev.md); WCAG contrast for `text-status-danger` on white verified by calculation (5.41:1 ≥ 4.5:1, see post-dev.md); full Playwright console+axe spec (`e2e/report-gallery.spec.ts`) deferred until the foundation unit's Playwright setup merges (not on this branch's base yet, per worker instructions) |
| AC7 | `packages/ui/src/report/__fixtures__/view-model.types.test.ts` + `tsc --noEmit` |

## Progress

- [x] T1 — `ReportInputs`/`ReportOptionInput`/`ReportMatchInput`
- [x] T2 — `ReportViewModel` schema + OpenAPI registration
- [x] T3 — `build_report_view_model` (5/5 builder tests green)
- [x] T4 — fixture generator (6 fixtures written)
- [x] T5 — `make api-client` regenerated, `ReportViewModel` present
- [x] T6 — format/types helpers
- [x] T7 — 11 components + `ReportPage`
- [x] T8 — AC5 scan test (16 assertions, all pass)
- [x] T9 — AC7 type test (passes + `tsc --noEmit` clean repo-wide)
- [x] T10 — barrel export + dependency
- [x] T11 — gallery pages + middleware

## Follow-ups

- `QuoteComputation` (backend/app/features/pricing/engine/types.py) doesn't expose `down_payment_amount` even though `compute_quote` computes it internally; `builder.py::_down_payment_amount` reconstructs it via `purchase_price - loan_amount`. Whoever next touches the engine's public contract (CQ-008 owner) could add the field directly so this reconstruction isn't needed.
- AC6's Playwright console/axe/react-doctor spec (`e2e/report-gallery.spec.ts`) could not be added — no `playwright.config.ts` exists on this branch yet (the foundation unit sets it up in parallel, per the coordinator's instructions). Vitest-level console.error/warn checks cover the same class of bug today; the coordinator should follow up once the foundation unit merges.
