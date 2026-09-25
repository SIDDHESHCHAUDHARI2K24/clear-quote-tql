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

**Review round.** PR #4's fresh review came back changes-requested (2 major, 1 minor/nit). All
three are resolved on this branch (see "Review findings" below and plan.md's "PR review round"
table for full detail): `down_payment_amount`/`str_gross_monthly_revenue` moved from
`builder.py` derivations into real `QuoteComputation` fields (M1); the AC5 scan test now derives
its field list dynamically and catches destructured/loop-variable arithmetic, not just dotted
access (M2); the AC7 type test does a real structural assignment instead of a shallow runtime
check (N1). The branch also merged the now-landed foundation unit (`origin/phase-p3-p4`, PR #3)
and adds the committed Playwright spec for AC6 that was previously deferred.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Gallery at `/_gallery/report` | `/gallery/report` | Both apps already have a `/gallery` route and `middleware.ts` `PUBLIC_PATHS` entry (CQ-005); followed that existing convention instead of introducing a second, differently-named public route. See plan.md Decision 5. |
| A staff-auth schema endpoint was called out as "not ideal" | Registered `ReportViewModel` as an OpenAPI `components/schemas` entry via `app.openapi` override (`backend/app/main.py::_register_report_view_model_schema`), no endpoint at all | Matches the spec's own steer toward "the least-invasive way ... prefer registering the model as a component." See plan.md Decision 1. |
| — (not specified) | `packages/ui` now depends on `@cq/api-client` (`workspace:*`) | Needed so report components can import `components["schemas"]["ReportViewModel"]` as their props type per spec's "generated TypeScript type ... is the component props type." Not circular. See plan.md Decision 3. |
| ~~`ReportOptionInput` carried `str_gross_annual_revenue` alongside `QuoteComputation`~~ | **Resolved in the review round (M1)** — removed. `QuoteComputation` now exposes `down_payment_amount` and `str_gross_monthly_revenue` directly; `ReportOptionInput` only carries `note_rate`/`down_payment_pct`/`discount_points_pct` (still needed for rate/points/down-payment-% *labels*, which aren't `QuoteComputation` fields) plus the computation itself. | See plan.md's "PR review round" table, M1. |
| AC6's Playwright spec `e2e/report-gallery.spec.ts` | **Added in the review round** — `e2e/lo-console/report-gallery.spec.ts` and `e2e/borrower-portal/report-gallery.spec.ts` | The foundation unit's Playwright setup (PR #3) merged into `phase-p3-p4` after this branch's first review pass; merged it in (`git merge origin/phase-p3-p4`) and added the committed specs. Both run clean against real dev servers: console/page-error check, AC2/AC3/AC4, and an `@axe-core/playwright` scan (0 critical/serious violations) — 7/7 passed. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/quotes/report/tests/test_builder.py::test_view_model_marcus_hale` — asserts P&I `"1913.05"`, `year1_tax_savings == "24275.78"`, `year1_tax_savings_monthly == "2023"`, negative STR cashflow. `packages/ui/src/report/HeroNumbers.test.tsx` asserts the rendered strings `"$24,276"` and `"≈ $2,023/mo"` and that the cashflow tile carries `text-status-danger`. Live screenshot: `evidence/lo-console-gallery-report.png` (Marcus Hale section). |
| AC2 | Met | `packages/ui/src/report/HeroNumbers.test.tsx` (Priya: exactly 3 `[data-testid="hero-numbers"] > div` tiles, no DSCR/cashflow/tax-savings text). `packages/ui/src/report/ReportGallery.primary-gating.test.tsx` (full-`ReportPage` DOM scan for Priya *and* Daniel-with-MI, both collapsibles expanded, asserts none of DSCR/cashflow/cap rate/cost segregation/prepayment penalty/tax savings/tax advice/rental income appear anywhere). Live-browser check (see below) independently confirms 3 tiles + no DSCR/cashflow text for Priya on the real rendered page. |
| AC3 | Met | `backend/.../test_builder.py::test_view_model_kathleen_mcreynolds_ltr_tbd` (`header.property_label == "Property to be determined"`, `cashflow.rent_label == "Market rent (LTR)"`). `ReportGallery.primary-gating.test.tsx` asserts `"Property to be determined"` renders and `/\bSTR\b/` never appears anywhere on Kathleen's page. Screenshot: `evidence/lo-console-gallery-report.png` (Kathleen section). |
| AC4 | Met | `backend/.../test_builder.py::test_switching_option_values_come_straight_from_the_fixture` (par vs. buydown differ; P&I is exactly the fixture's own value, not recomputed). `OptionSwitcher.test.tsx` (click updates selection). `ReportGallery.primary-gating.test.tsx` (clicking Buydown changes the rendered breakdown's P&I line to buydown's own fixture amount, old value gone). Live-browser check: hero-numbers block text differs before/after clicking the Buydown pill on the real page (see "How to test manually"). |
| AC5 | Met | `packages/ui/src/report/report-no-money-math.test.ts` (27 tests, hardened in the review round — M2): `FIELD_NAMES` derived dynamically from every fixture's numeric-shaped leaf values (self-updating), the detector (`containsForbiddenArithmetic`) matches dotted access, destructured locals and loop variables, 8 self-tests prove it catches `option.rate - 1`/`monthly_payment - cash_to_close`/`line.amount + other.amount`/`Number(x) + 1` and does not flag `i + 1`/array-index math/plain calls/Tailwind classes. Real scan over all 12 owned files: 0 matches. |
| AC6 | Met | `npx react-doctor -y --blocking error` on both apps — 2 pre-existing warnings, both in `src/app/page.tsx` (untouched by this item); 0 new findings. WCAG contrast: `text-status-danger` (`#c1392b`) on white = **5.40:1** (≥ 4.5:1 AA). Console errors: `apps/*/src/app/gallery/report/page.test.tsx` (Vitest spies, 0 calls). **Committed Playwright specs** (added in the review round): `e2e/lo-console/report-gallery.spec.ts`, `e2e/borrower-portal/report-gallery.spec.ts` — console/page-error check, AC2/AC3/AC4 assertions, `@axe-core/playwright` scan filtered to `critical`/`serious` impact. Run against real dev servers (`LO_BASE_URL=http://localhost:3102 PORTAL_BASE_URL=http://localhost:3202 pnpm exec playwright test e2e/lo-console/report-gallery.spec.ts e2e/borrower-portal/report-gallery.spec.ts`): **7/7 passed**, including 0 critical/serious accessibility violations on either app. |
| AC7 | Met | `packages/ui/src/report/__fixtures__/view-model.types.test.ts` (rewritten in the review round — N1): a real structural assignment (`const typed: ReportViewModelData = fixture`, via `LooseReportViewModel` which loosens only the one field JSON-import literal-widening can't satisfy — `strategy` — with a genuine runtime check narrowing it back). Verified this actually catches drift: temporarily deleted `header.purchase_price` from a fixture and confirmed `tsc --noEmit` failed with a precise "Property 'purchase_price' is missing" error at the assignment (reverted, not committed). `tsc --noEmit` clean repo-wide otherwise. `make api-client`'s generated `components["schemas"]["ReportViewModel"]` matches the Pydantic schema field-for-field. |

Screenshots: `docs/backlog/CQ-021-report-components/evidence/lo-console-gallery-report.png` (full page, all 6 fixtures), `borrower-portal-gallery-report.png` (same, other app), `borrower-portal-gallery-report-mobile.png` (390px viewport). Evidence predates the review round's engine-field move (M1) but the fixture JSON is byte-identical before/after (confirmed via `git diff`), so the screenshots still reflect current output exactly.

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (whole suite, post-merge + M1) | `uv run pytest backend seed` | 391 passed (was 376 pre-merge; +12 from the merged foundation unit, +3 new engine tests) |
| Engine tests only | `uv run pytest backend/app/features/pricing/engine` | 44 passed (was 41; +3 for M1: `down_payment_amount`/`str_gross_monthly_revenue`) |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 274 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 274 source files |
| Frontend tests (whole monorepo) | `pnpm -r run test` | 4/4 workspaces passed — api-client 2, ui 106, lo-console 21, borrower-portal 37 (166 total; ui was 94, +12 from the M2/N1 test hardening) |
| ESLint (whole monorepo) | `pnpm -r run lint` | 0 errors |
| ESLint (e2e/) | `pnpm exec eslint e2e` | 0 errors |
| TypeScript (whole monorepo) | `pnpm -r run typecheck` | 0 errors |
| TypeScript (root, covers e2e/) | `pnpm exec tsc -p tsconfig.json --noEmit` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| Playwright (report-gallery specs, both apps) | `LO_BASE_URL=http://localhost:3102 PORTAL_BASE_URL=http://localhost:3202 pnpm exec playwright test e2e/lo-console/report-gallery.spec.ts e2e/borrower-portal/report-gallery.spec.ts` | 7/7 passed (console/page-error, AC2, AC3, AC4, axe ×2) |
| react-doctor (lo-console) | `npx react-doctor -y --blocking error` | Score 83/100; 2 warnings, both pre-existing in `src/app/page.tsx` (not touched by this item) |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | Score 83/100; 2 warnings, both pre-existing in `src/app/page.tsx` (not touched by this item) |
| `alembic heads` (post-merge) | `uv run alembic heads` | `bbd0e3150264 (head)` — single head |
| graphify | `graphify update .` | Rebuilt: 4213 nodes, 8791 edges, 399 communities |

`make api-client` was run twice: once mid-development (registering `ReportViewModel`), once in the review round after M1 added `down_payment_amount`/`str_gross_monthly_revenue` to `QuoteComputation` — the diff is scoped to exactly those 2 additive fields on `QuotePreviewResponse` (which subclasses `QuoteComputation`); `ReportViewModel`'s own generated shape is unchanged both times.

Fixture regeneration after M1: `uv run python backend/scripts/build_report_fixtures.py` produced byte-identical JSON (`git diff --stat` showed zero changes), confirming the engine-field move is value-preserving, not just a structural refactor.

## Review findings (stage 6)

Ran the `code-review` skill (medium effort) as a fresh, isolated pass over the full uncommitted diff (this worker's own session did not carry review context into that fork). No critical/major findings; 2 minor findings, both resolved or explicitly accepted:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Minor | `builder.py`'s `_down_payment_amount`/`_gross_rent_monthly` do Decimal math outside `quote_engine`, against AGENTS.md's "Money math lives only in `quote_engine`" rule read literally | Accepted as-is — already documented as a deliberate decision (plan.md Decision 2) with a concrete follow-up (add `down_payment_amount` to `QuoteComputation`). Both derivations only operate on already-engine-produced or raw-provider decimals, mirror math `quote_engine` itself already performs elsewhere, and are docstring-justified at the call site. Re-reviewed after the reviewer flagged it; judged non-blocking because the rule's intent (per AGENTS.md's own phrasing, paired with "Frontends never compute money") is aimed at frontend recomputation of engine numbers, not narrow backend display derivations of values the engine computed internally but didn't expose. |
| Minor | `ExplainerCards.tsx` hand-wrote 6 near-identical row blocks instead of the row-array + `.map()` pattern `CashflowTable.tsx`/`CostSegTable.tsx` already use | Fixed — refactored to a shared `RowList`/`Row[]` pattern matching the sibling components; re-ran `vitest`/`tsc`/`eslint`/`prettier` for `packages/ui`, all green (94/94 tests). |

### Coordinator's fresh-subagent review (PR #4, changes-requested)

The coordinator's own fresh-subagent review of PR #4 landed after the above self-check, and it caught a real gap the self-check's "accept as documented" call on the down-payment/STR-revenue derivation had missed being too lenient on. Both majors are now fixed, not accepted-as-is:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major (M1) | `builder.py`'s `_down_payment_amount`/`_gross_rent_monthly` did Decimal arithmetic outside `quote_engine` | **Fixed, not just documented this time** — `down_payment_amount`/`str_gross_monthly_revenue` are now real `QuoteComputation` fields, computed by `compute_quote`. Full detail: plan.md's "PR review round" table, row M1. |
| Major (M2) | AC5's scan test's field-path matching was too narrow (fixed container-name allowlist, dotted-only) to catch destructured locals or loop variables | Rewrote with a dynamically-derived field list and a chain-or-bare-identifier pattern; added 8 self-tests proving the specific catches/non-catches the review asked for. Full detail: plan.md's "PR review round" table, row M2. |
| Minor/nit (N1) | AC7's type test's `assertIsReportViewModel` only shallow-checked 3 properties, not a real structural assignment | Rewrote to do the direct `const typed: ReportViewModelData = fixture` assignment, with one narrow, empirically-verified carve-out for JSON-import literal widening on the single enum field. Full detail: plan.md's "PR review round" table, row N1. |
| Nit (N2) | Not itemized by the coordinator | No separate action — see plan.md row N2. |

All four re-verified green after the fixes: 391 backend tests, 166 frontend tests, 44/44 engine tests, 27/27 AC5 tests, 2/2 AC7 tests, 7/7 Playwright, ruff/mypy/eslint/tsc/prettier all clean, `alembic heads` still one head. See the updated "Test log" above for exact commands/counts.

The coordinator's own fresh-subagent review (a separate reviewer who did not write this code, per AGENTS.md's stage 6) is still the gate this PR needs to clear before merge — this file records both review passes (this worker's own self-check, and the coordinator's independent one) so the audit trail is complete.

## How to test manually

1. `cd` to this worktree; `.env` already points at slot-2 DBs/ports (see the worktree's own `.env`, not committed).
2. Backend: `uv run pytest backend/app/features/quotes/report backend/app/features/pricing/engine -q` (5 + 44 tests) — or `uv run pytest backend seed -q` for everything (391).
3. Fixtures: `uv run python backend/scripts/build_report_fixtures.py` regenerates the 6 JSON files under `packages/ui/src/report/__fixtures__/`.
4. Frontend: `cd packages/ui && pnpm exec vitest run` (106 tests, includes AC1–AC5, AC7).
5. Live browser: `pnpm --filter @cq/lo-console exec next dev -p 3102 &` and `pnpm --filter @cq/borrower-portal exec next dev -p 3202 &`, then open `http://localhost:3102/gallery/report` and `http://localhost:3202/gallery/report`. Confirm: Marcus Hale shows red `-$709` cashflow and `$24,276` / `≈ $2,023/mo` tax savings; Priya Nair shows exactly 3 tiles with no DSCR/cashflow text; Kathleen McReynolds shows "Property to be determined" and no "STR" text; clicking the Buydown pill on any investment fixture changes every hero number and (once "See the full breakdown" is expanded) the breakdown table.
6. Playwright (same servers as step 5 still running): `LO_BASE_URL=http://localhost:3102 PORTAL_BASE_URL=http://localhost:3202 pnpm exec playwright test e2e/lo-console/report-gallery.spec.ts e2e/borrower-portal/report-gallery.spec.ts` (7 tests: console errors, AC2–AC4, axe). Kill both dev servers (`lsof -ti:3102,3202 | xargs kill`) when done.

## Follow-ups

- ~~Add `down_payment_amount` to `QuoteComputation`~~ — **done** (review round M1); `str_gross_monthly_revenue` added alongside it.
- ~~Add the committed Playwright spec~~ — **done** (review round); `e2e/lo-console/report-gallery.spec.ts` and `e2e/borrower-portal/report-gallery.spec.ts`.
- CQ-023 will widen/replace `ReportMatch`'s placeholder shape (backend/app/features/quotes/report/schemas.py) and build `MatchCard.tsx`/`MatchList.tsx`/`ReportMatchesSlot.tsx`; `ReportPage.tsx` currently renders nothing for `matches` (always `[]` today) and will need a slot added for that, per phase-p3-p4-plan.md Decision D3.
- `report-no-money-math.test.ts`'s known limitation: arithmetic inside a template-literal interpolation isn't caught (the whole literal span is stripped before scanning). Not a risk in this directory's current code; would need a real parser to close precisely.
