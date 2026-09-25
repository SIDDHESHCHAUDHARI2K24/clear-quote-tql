# CQ-017 Pricing panel

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-016, CQ-013 |
| Kaneo task | CQ-017 in Kaneo (task id `lky9qv864ao119rajk7ujqd8`) |
| Branch | `cq-017-pricing-panel` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The top half of the Pricing tab: every number behind the monthly payment and cash to close, already filled in by the pipeline, each showing where it came from. The LO changes only what they disagree with and sees the breakdown update instantly. This is the "automate by default, edit by exception" moment of the demo.

## Scope

**Consumes (expected from CQ-013, which is already built)** — in stage 1, check the actual CQ-013 routes with codegraph. Where names or shapes differ, use the built ones and log a `Decision:`; where an endpoint is missing, add it in this item.

- `GET /api/applications/{id}/pricing` → the current scenario inputs and every enriched field as `{field_key, value, source, source_ref, overridden: bool, original_value}`, plus the engine output (breakdown).
- `PUT /api/applications/{id}/fields/{field_key}` with `{value}` → stores an LO override; `DELETE` on the same path reverts to the source value. Both write an activity event and mark existing quotes stale when the field affects pricing.
- `POST /api/quotes/preview` with scenario inputs (+ optional rate) → full engine output, no persistence, < 300 ms.

**Frontend (`apps/lo-console`, Pricing tab, top section)**

- Input group (left): purchase price (MoneyInput); down payment as linked % ⇄ $ (editing either updates the other, rounded to cents); loan amount and LTV (read-only, computed); PPP select (investment only: None, 1, 2, 3, 5 years); note rate (read-only until quotes exist; then shows the recommended quote's rate).
- Payment breakdown (right): P&I, taxes (monthly $ + annual rate + SourceBadge), insurance (SourceBadge; default 0.5% of price/yr), MI (primary only, shown only when LTV > 80%), HOA, **total monthly payment** emphasised.
- Investment block (LTR or STR only, never both): LTR → market rent + source; STR → gross monthly STR revenue + source, 20% expense ratio, underwritten rent. Then DSCR (2 dp, coloured: ≥ 1.25 green, 1.00–1.24 neutral, < 1.00 amber) and break-even rent.
- Cash to close block: down payment, lender fees ($1,790), discount points (from recommended quote, else $0), title (0.7%), prepaids, credits, **cash to close** emphasised; appraisal "~$600–900, paid before closing" as a note.
- Every enriched value: SourceBadge (Encompass, AirDNA, RentCast, SmartAsset, Steadily, Default, LO override). Click → inline edit. Overridden values show "LO override" + a revert icon that restores the source value.
- Live recalculation: input changes call `/quotes/preview` debounced 250 ms; the breakdown updates without a page reload; a subtle "recalculating" state shows if a call takes > 300 ms.
- Stale marker: when an edit affects pricing, a banner "Quotes are out of date — Re-price" appears above the quote builder area (the action itself is wired in CQ-018).

## Out of scope

- Quote cards, overlay, AutoQuote (CQ-018).
- Any money math in TypeScript: the panel only displays API output.

## References

- `docs/design/system-design.md` — Automation-first input model, LO Console → Pricing panel, Calculation engine, Hero numbers.
- `docs/design/data-field-catalog.md` — §5, §7, §8, §9 (field keys and defaults).
- Reference screens: `docs/design/reference/01-loan-advisor-excel-dscr.png`, `07-quote-breakdown.png`.

## Acceptance criteria

- [ ] AC1 — For Marcus Hale at 7.500%, 20% down on $342,000, the panel shows loan amount $273,600.00, LTV 80.00% and P&I $1,913.05; totals equal the engine output for his seeded tax and insurance values.
- [ ] AC2 — Typing 25% in down payment updates the $ field to $85,500.00 and the breakdown within one debounce cycle; typing $68,400 sets 20.00%.
- [ ] AC3 — Overriding property tax on Marcus Hale shows "LO override", recomputes the total, and marks his quotes stale (banner visible; API shows quotes `stale=true`). Reverting restores the SmartAsset value and badge.
- [ ] AC4 — Priya Nair (primary) shows no investment block and no PPP; Daniel Ortiz (primary, 5% down) shows an MI line; Marcus Hale shows the STR block only; Kathleen McReynolds shows the LTR block only.
- [ ] AC5 — Marcus Hale's DSCR shows 0.90 (or his engine value) in amber; Asheville Holdings shows ≥ 1.25 in green.
- [ ] AC6 — No arithmetic on money values exists in the frontend code for this panel (review check: all figures come from API responses).
- [ ] AC7 — The p95 time from last keystroke to updated breakdown is under 600 ms locally (250 ms debounce + < 300 ms preview + render).
- [ ] AC8 — react-doctor passes; inputs are keyboard-accessible with visible focus and labelled for screen readers.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC5 | API test (golden values) + component test with fixture | `test_pricing_marcus_hale`, `PricingPanel.test.tsx` |
| AC2 | Component test | `DownPaymentLinkedInput.test.tsx` |
| AC3 | API test + component test | `test_override_and_revert_marks_stale`, `SourceBadge.test.tsx` |
| AC4 | Component tests over 4 persona fixtures | `PricingPanel.strategy-gating.test.tsx` |
| AC6 | Code review item + grep for arithmetic in panel files | review notes in post-dev.md |
| AC7 | Playwright timing script | `e2e/pricing-latency.spec.ts` |
| AC8 | react-doctor + axe check | evidence in post-dev.md |

## Notes for the agent

- Fixtures for component tests come from real API responses captured after `make demo-reset`, stored under `apps/lo-console/src/features/pricing/__fixtures__/`.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
