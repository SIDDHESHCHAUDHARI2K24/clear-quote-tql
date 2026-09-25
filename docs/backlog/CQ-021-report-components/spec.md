# CQ-021 Shared report components

| Field | Value |
| --- | --- |
| Phase | P4 Borrower Tier A |
| Depends on | CQ-005, CQ-008 |
| Kaneo task | CQ-021 in Kaneo (task id `lvwt21rt5zfrpqmok65ix005`) |
| Branch | `cq-021-report-components` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

One set of report components and one data contract, used by both the LO preview (CQ-019) and the borrower portal (CQ-022). This is where "complex numbers made simple" is decided visually. If the LO preview and the borrower page ever differ, it is a bug in this item's contract.

## Scope

**Contract (owned by this item)**

- Pydantic schema `ReportViewModel` in `backend/app/features/quotes/report/schemas.py` and a pure builder `build_report_view_model(inputs: ReportInputs) -> ReportViewModel`, where `ReportInputs` is a plain dataclass (borrower first name, property, strategy, options with engine outputs, recommendation, LO, dates, flags, matches). It does not read the database, so this item does not wait for CQ-007; CQ-019 and CQ-022 map their models into `ReportInputs`. Shape:
  - `header`: first_name, property_label (address or "Property to be determined"), purchase_price, prepared_at, rates_as_of, expires_at, expired, superseded.
  - `strategy`: `primary` | `ltr` | `str`.
  - `options[]` (recommended first): quote_id, label (Par pricing / Buydown / …), recommended, rate, points_pct, points_amount, down_payment_pct, prepay_label, `hero` (monthly_payment, cash_to_close; primary adds loan_amount; investment adds monthly_cashflow, year1_tax_savings, year1_tax_savings_monthly), `breakdown` (payment lines, cash-to-close lines), `cashflow` (investment only: gross revenue or market rent, expense ratio, qualifying rent, PITIA, monthly and annual cashflow, DSCR, cap rate, cashflow incl. tax benefit), `cost_seg` (investment only: price, land 20%, basis, accelerated 25%, bonus %, year-1 deduction, marginal rate, savings).
  - `recommendation`: text, lo_note.
  - `matches[]`: empty here; filled by CQ-023.
  - `disclosures`: core (always), investment (investment only), tax (investment only).
  - `lo`: name, title, nmls, phone, email.
- Money values are decimal strings from the engine. The frontend formats them but never adds, subtracts or rounds them.
- The generated TypeScript type from the api-client is the component props type.

**Components (`packages/ui/src/report/`)**

| Component | Content |
| --- | --- |
| `ReportHeader` | "{First name}, here are your numbers", property label, purchase price, prepared date, "Rates as of" date, Save as PDF button (calls `window.print`) |
| `OptionSwitcher` | One pill per option, recommended first with a star; controlled component (`selectedId`, `onChange`) |
| `HeroNumbers` | 3 tiles for primary (payment, cash to close, loan amount + rate), 4 for investment (payment, cash to close, cashflow labelled LTR/STR and red when negative, year-1 tax savings with "≈ $X/mo") |
| `RecommendationCard` | "What we recommend" text + LO note |
| `ExplainerCards` | Investment only: "Why the rental income works" (rent vs payment, DSCR) and "Estimated year-one tax savings" with "Estimate only, not tax advice" |
| `ComparisonTable` | All options side by side; rows follow the reference pricing-options screen; recommended column highlighted; strategy-gated rows hidden for primary |
| `BreakdownTable` | Payment and cash-to-close lines for the selected option |
| `CashflowTable`, `CostSegTable` | Investment only |
| `Collapsible` | "See all N options we priced" / "See the full breakdown" |
| `Disclosures` | Footer text by strategy |
| `ExpiredBanner`, `SupersededBanner` | States from the header flags |

**Fixtures and gallery**

- `seed`-independent fixtures: a script builds `ReportViewModel` JSON for Marcus Hale (STR), Kathleen McReynolds (LTR, TBD), Priya Nair (primary) and Daniel Ortiz (primary with MI) by running `quote_engine` on their persona inputs; saved under `packages/ui/src/report/__fixtures__/`.
- Gallery page `/_gallery/report` in both apps renders every component with each fixture, plus expired and superseded variants.

## Out of scope

- Data fetching, routing, auth (CQ-019, CQ-022).
- Property match cards (CQ-023).
- Print-stylesheet tuning (CQ-022), beyond components not breaking in print.

## References

- `docs/design/system-design.md` — Hero numbers, Borrower Portal → Quote report, Calculation engine (golden tests), principle 4 (strategy gating).
- `docs/design/data-field-catalog.md` — §8, §9, §10.
- Reference screens: `04-report-summary.png` to `10-cost-segregation.png` (field set and grouping, not pixel targets; their numbers are not authoritative).

## Acceptance criteria

- [ ] AC1 — The Marcus Hale fixture, built by the engine, has P&I "1913.05" on the 7.500% par option, year-1 tax savings "24275.78" and "≈ $2,023/mo" displayed, and cashflow displayed in red with the STR label.
- [ ] AC2 — The Priya Nair fixture renders exactly 3 hero tiles and no DSCR, rent, cashflow, cost-seg, PPP or investment disclosure anywhere on the page (DOM assertion over the whole gallery page).
- [ ] AC3 — Kathleen McReynolds shows "Property to be determined" and the LTR label; no STR text appears.
- [ ] AC4 — Switching options in `OptionSwitcher` changes every hero number, the breakdown and the cashflow table to the selected option's values, with no recomputation in the frontend (values match the fixture's option exactly).
- [ ] AC5 — A static check fails the build if any file in `packages/ui/src/report/` performs arithmetic on money props (lint rule or test that scans for `+ - * /` on those fields; document the approach in plan.md).
- [ ] AC6 — Gallery renders with no console errors in both apps; react-doctor passes; components meet WCAG AA contrast (negative cashflow red on white ≥ 4.5:1).
- [ ] AC7 — `ReportViewModel` round-trips: the Pydantic model's JSON validates against the generated TypeScript type in a type test.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC3 | Builder unit tests + component tests | `test_view_model_marcus_hale`, `HeroNumbers.test.tsx` |
| AC2 | Component test on full gallery render | `ReportGallery.primary-gating.test.tsx` |
| AC4 | Component test | `OptionSwitcher.test.tsx` |
| AC5 | Lint rule or scan test | `report-no-money-math.test.ts` |
| AC6 | Playwright console check + axe + react-doctor | `e2e/report-gallery.spec.ts` |
| AC7 | Type test | `view-model.types.test.ts` |

## Notes for the agent

- Build the builder and schema first (wave 1), then fixtures, then components in parallel.
- Visual direction: navy header, sage accents, mono numerals for money, generous whitespace; 3–4 hero numbers are the largest text on the page.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
