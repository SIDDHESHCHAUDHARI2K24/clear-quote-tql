# CQ-021 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | How does `ReportViewModel` reach `make api-client` with no DB-backed endpoint yet | `backend/app/main.py::_register_report_view_model_schema` overrides `app.openapi` to merge `ReportViewModel`'s (and every model it references) `components/schemas` entries into the generated OpenAPI dict, via `schemas.report_view_model_openapi_components()` (`ReportViewModel.model_json_schema(ref_template=...)`, splitting `$defs` into top-level components). No throwaway endpoint (spec.md explicitly calls that "not ideal"). Verified: `app.openapi()["components"]["schemas"]["ReportViewModel"]` is present, and `make api-client` generates the matching `components["schemas"]["ReportViewModel"]` TS type byte-for-byte. |
| 2 | Decision — **superseded by PR review M1, see the "PR review round" table below** | ~~`builder.py` derives two values `QuoteComputation` doesn't expose~~ | ~~AGENTS.md's "money math lives only in quote_engine" rule targets *frontend* recomputation...~~ **Resolved differently**: `down_payment_amount` and `str_gross_monthly_revenue` are now real fields on `QuoteComputation` itself (`backend/app/features/pricing/engine/types.py`), computed by `compute_quote` (`quote_engine.py`). `builder.py` reads them directly; the two derivation helpers this row originally justified (`_down_payment_amount`, `_gross_rent_monthly`) no longer exist. |
| 3 | Decision | `packages/ui` depends on `@cq/api-client` | Spec.md: "The generated TypeScript type from the api-client is the component props type." Added `"@cq/api-client": "workspace:*"` to `packages/ui/package.json` dependencies. Not circular (api-client has no `@cq/ui` dependency). |
| 4 | Decision (AC5 approach) | Static "no money math" check | A Vitest scan test (`packages/ui/src/report/report-no-money-math.test.ts`), not a custom eslint rule — no project-local eslint rule package/build step existed to hang a new rule off, and a scan test runs in the same `pnpm test` pass everything else does. Approach: for every `*.ts(x)` file this item owns (excluding tests, `format.ts`, `types.ts`), strip string/template literals and comments (so Tailwind classes like `px-4` and prose never false-positive), then regex-match an arithmetic operator (`+ - * /`) directly adjacent to a `ReportViewModel` field-path access (`option.hero.…`, `Number(...)`). Heuristic, not a full parser — documented in the test file's header comment. All 11 non-excluded files pass with zero matches today. |
| 5 | Decision | Gallery route path | Followed the existing `/gallery` convention (both apps' `src/app/gallery/page.tsx` already exist and `/gallery` is public in `middleware.ts`) instead of spec's literal `/_gallery/report` — added `/gallery/report/page.tsx` in both apps and added `/gallery/report` to each `middleware.ts`'s `PUBLIC_PATHS` (exact-match only; `isPublicPath` doesn't prefix-match `/gallery/*`). |
| 6 | Decision | `matches[]` element type | Spec says "empty here; filled by CQ-023" but doesn't pin a shape. Added a minimal `ReportMatch` schema (data-field-catalog §11 subset: id, image, address, bed/bath/sqft, deal grade, tagline, price) so `ReportViewModel`'s top-level shape is concrete today; CQ-023 (D3, phase-p3-p4-plan.md) can widen/adjust this schema without touching anything else in `ReportViewModel`. |
| 7 | Decision | `ReportPage.tsx` (not in spec.md's component table) | Added one composed component (`packages/ui/src/report/ReportPage.tsx`) that assembles every owned component in system-design.md's "Quote report" order, holding the `OptionSwitcher` selection state. Both apps' `/gallery/report` pages render it once per fixture (satisfies "renders every component with each fixture" structurally); CQ-019/CQ-022 can render the same component later so the LO preview and borrower report can never structurally diverge — spec.md's stated goal for this item. |
| 8 | Decision | Fixture note-rate/tax-rate/revenue inputs | Marcus Hale's par option uses purchase price $342,000 / 20% down / 7.500% note rate with `ConfigSnapshot()` defaults — the exact `test_golden.py` STR scenario — so AC1's pinned P&I ($1,913.05) and year-1 tax savings ($24,275.78) reproduce exactly. Tax/insurance/STR-revenue/market-rent inputs for all 4 personas come from the real seed provider tables (`seed/providers/tax_rates.yaml`, `str_revenue.yaml`, `rents.yaml`, keyed by each persona's county/zip), not hand-picked, per spec's "seed-independent fixtures ... built by running quote_engine on their persona inputs." |

No big gaps found; nothing raised in Kaneo.

## PR review round (fresh-subagent review, changes-requested)

PR #4's fresh review came back changes-requested with 2 major and 1 minor/nit finding. All addressed on the same branch (`cq-021-report-components`), pushed as new commits. Also merged `origin/phase-p3-p4` (the foundation unit, PR #3, had landed in the meantime) and added the committed Playwright spec AC6 had been deferred on.

| # | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| M1 | Major | `builder.py`'s `_down_payment_amount`/`_gross_rent_monthly` did Decimal arithmetic outside `quote_engine`, against AGENTS.md's literal "Money math lives only in `quote_engine`" rule | Added `down_payment_amount: Decimal` (always set, every strategy) and `str_gross_monthly_revenue: Decimal | None` (STR only) as real fields on `QuoteComputation` (`backend/app/features/pricing/engine/types.py`), computed by `compute_quote` in `quote_engine.py` (new `str_gross_monthly_revenue_amount` helper, reusing the exact `/12` conversion `underwritten_str_rent` already did internally). Engine tests: `test_down_payment_amount_marcus_hale_342k_20pct` (342000 × 20% → 68400.00, the Marcus Hale golden value the review asked for), `test_down_payment_amount_present_on_primary_too`, `test_str_gross_monthly_revenue_none_on_ltr`, plus assertions added to the existing `test_full_scenario_matches_all_pinned_golden_values`. All 44 engine tests green (3 new). `builder.py` now reads `computation.down_payment_amount`/`computation.str_gross_monthly_revenue` directly; the two derivation helpers and `ReportOptionInput.str_gross_annual_revenue` (no longer needed) are deleted. Regenerated fixtures are byte-identical (confirms the refactor is value-preserving, not just structurally different). `QuotePreviewResponse` (subclasses `QuoteComputation`, `pricing/scenarios/schemas.py`) gained the 2 fields too — `make api-client` regenerated, diff scoped to exactly those 2 additive fields. |
| M2 | Major | AC5's scan test only matched a fixed container-name allowlist (`hero\|breakdown\|cashflow\|...`) immediately preceded by `\w+\.` — missed destructured locals and loop variables, and used a hand-maintained field list | Rewrote `report-no-money-math.test.ts`: `FIELD_NAMES` is now derived dynamically from every fixture JSON (any leaf value shaped like a decimal string `^-?\d+(\.\d+)?$` has its key collected), so it self-updates as `ReportViewModel` evolves. The arithmetic-adjacency pattern now matches an optional identifier-dot-chain of any depth *or a bare identifier* ending in a `FIELD_NAMES` entry, so a destructured local (`const { monthly_payment } = option.hero`) or a loop variable (`for (const line of lines) line.amount`) is caught the same as a dotted access. Refactored the detector into an exported `containsForbiddenArithmetic()` function with 8 negative/positive self-tests proving it: catches `option.rate - 1`, destructured `monthly_payment - cash_to_close`, `line.amount + other.amount`, `Number(x) + 1`; does **not** flag `i + 1`, `items[i + 1]`, a plain `formatMoney(...)` call, or Tailwind classes/comments. 27/27 tests pass (was 15). |
| N1 | Minor | AC7's type test used a hand-rolled 3-field runtime check (`assertIsReportViewModel`) instead of real structural type-checking | Rewrote `view-model.types.test.ts` to do the direct assignment the review asked for (`const typed: ReportViewModelData = fixture`), with one narrow, *verified* carve-out: TypeScript's `resolveJsonModule` widens a JSON import's string-literal properties to plain `string`, so the single enum field (`strategy: "primary" \| "ltr" \| "str"`) can't assign directly — confirmed empirically (tried the literal assignment first; it fails with exactly one error, on that one field, nothing else). `LooseReportViewModel = Omit<ReportViewModelData, "strategy"> & { strategy: string }` loosens only that field; `assertValidStrategy` is a real runtime check (not a cast) that narrows it back. Verified this actually catches drift: temporarily deleted `header.purchase_price` from a fixture — `tsc --noEmit` failed at the assignment with a precise "Property 'purchase_price' is missing" error (reverted before committing). |
| N2 | Nit | Optional, not itemized by the coordinator | Not acted on separately — folded into the M1/M2 cleanup (e.g. `ReportOptionInput.str_gross_annual_revenue` removed as dead weight once M1 landed). |

**Merge**: `git merge origin/phase-p3-p4` (foundation PR #3 — Playwright config, `e2e/` helpers, the shared migration). Conflicts were confined to generated files (`graphify-out/*`, `pnpm-lock.yaml`); resolved by taking theirs then re-running `graphify update .`/`pnpm install`. `alembic heads` still resolves to one head (`bbd0e3150264`) after the merge.

**AC6 Playwright spec**: added `e2e/borrower-portal/report-gallery.spec.ts` (console/page-error check, AC2, AC3, AC4, and an `@axe-core/playwright` scan filtered to `critical`/`serious` impact) and `e2e/lo-console/report-gallery.spec.ts` (console/page-error check + the same axe scan). `@axe-core/playwright` added as a root devDependency — easy to add, so not skipped. Both specs run clean against real dev servers: 7/7 passed, including 0 critical/serious accessibility violations on either app.

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
| **Engine (PR review M1)** | `backend/app/features/pricing/engine/types.py` (modified: `QuoteComputation.down_payment_amount`/`str_gross_monthly_revenue`), `quote_engine.py` (modified: `compute_quote` sets both; new `str_gross_monthly_revenue_amount` helper), `tests/test_golden.py` (3 new tests) |
| **E2E (PR review round)** | `e2e/lo-console/report-gallery.spec.ts`, `e2e/borrower-portal/report-gallery.spec.ts` (new), root `package.json` (modified: add `@axe-core/playwright` devDependency) |

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
| AC5 | `packages/ui/src/report/report-no-money-math.test.ts` (27 tests: dynamic `FIELD_NAMES` derivation + `containsForbiddenArithmetic` self-tests + the real per-file scan) |
| AC6 | `apps/lo-console/src/app/gallery/report/page.test.tsx`, `apps/borrower-portal/.../page.test.tsx` (console.error/warn spy, Vitest-level); `e2e/lo-console/report-gallery.spec.ts`, `e2e/borrower-portal/report-gallery.spec.ts` (Playwright: console/page-error, AC2-AC4, `@axe-core/playwright` critical/serious scan — 7/7 passed against real dev servers); `react-doctor` (0 new findings — see post-dev.md); WCAG contrast for `text-status-danger` on white verified by calculation (5.40:1 ≥ 4.5:1, see post-dev.md) |
| AC7 | `packages/ui/src/report/__fixtures__/view-model.types.test.ts` — real structural assignment (`LooseReportViewModel`) + `tsc --noEmit` (verified it actually fails on a deleted field, see PR review round table above) |

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
- [x] T12 (PR review round) — M1: `down_payment_amount`/`str_gross_monthly_revenue` moved into `QuoteComputation`; builder consumes them directly; 3 new engine tests
- [x] T13 (PR review round) — M2: AC5 scan test hardened (dynamic field-name derivation, destructured/loop-variable detection, 8 self-tests)
- [x] T14 (PR review round) — N1: AC7 type test does a real structural assignment (`LooseReportViewModel` + narrow runtime check for the one enum field)
- [x] T15 (PR review round) — merged `origin/phase-p3-p4` (foundation), added committed Playwright specs for AC6 (console/page-error, axe, AC2-AC4) in both apps

## Follow-ups

- ~~`QuoteComputation` doesn't expose `down_payment_amount`~~ — **done** in the PR review round (M1): both `down_payment_amount` and `str_gross_monthly_revenue` are now real `QuoteComputation` fields.
- ~~AC6's Playwright spec could not be added~~ — **done** in the PR review round: `e2e/borrower-portal/report-gallery.spec.ts` and `e2e/lo-console/report-gallery.spec.ts`, both green against real dev servers (7/7 passed, 0 critical/serious axe violations).
- `report-no-money-math.test.ts`'s known limitation stands even after hardening: arithmetic written *inside* a template-literal interpolation (e.g. `` `${a.rate - b.rate}` ``) is not caught, because the whole template literal span is stripped before scanning. No code in this directory does that today; closing this precisely would need a real parser, which is disproportionate for a defense-in-depth check layered on top of code review and the engine/builder's own contract.
