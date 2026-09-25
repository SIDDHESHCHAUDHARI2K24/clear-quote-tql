# CQ-018 Quote builder

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-017 |
| Kaneo task | CQ-018 in Kaneo (task id `oruvrbeiljm8tu8ohnjfhxu5`) |
| Branch | `cq-018-quote-builder` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The bottom half of the Pricing tab. When the LO arrives, the pipeline has already priced the default scenarios, so the quotes are waiting as cards. The LO can compare them, change inputs and AutoQuote again, or pick a specific product from the rate grid, without leaving the screen.

## Scope

**Consumes (expected from CQ-013, which is already built)** — in stage 1, check the actual CQ-013 routes with codegraph. Where names or shapes differ, use the built ones and log a `Decision:`; where an endpoint is missing, add it in this item.

- `GET /api/applications/{id}/scenarios` → scenarios with their quotes (label, investor, product, rate, points %, points $, lock days, priced_at, stale, engine output).
- `POST /api/applications/{id}/scenarios` with inputs → creates a scenario; `PUT /api/scenarios/{id}` updates inputs.
- `POST /api/scenarios/{id}/autoquote` → prices via the mock OB adapter, keeps the best par and best buydown (lowest rate for ≤ 1.00 point), returns the quotes. A missing required OB field returns 422 `{code: "missing_field", field}`.
- `GET /api/scenarios/{id}/products` → the full mock OB result grid.
- `POST /api/scenarios/{id}/quotes` with `{product_row_id}` → saves a manual pick; `DELETE /api/quotes/{id}`.
- `POST /api/quotes/{id}/recommend` → marks one quote recommended per application (sets the header note rate).
- `POST /api/applications/{id}/reprice` → re-runs AutoQuote for every scenario (used by the stale banner).

**Frontend (Pricing tab, bottom section)**

- Default groups, as seeded by the pipeline:
  - Investment: "At DSCR 1.00" → Par, Buydown; "At your DSCR (x.xx)" → Par, Buydown. When both DSCRs fall in the same pricing bucket, show one group with the note "Your DSCR prices the same as 1.00".
  - Primary: "At {down}% down" → Par, Buydown; "At {next step}% down" → Par (the step that removes MI, or 20%).
- Quote card: label, rate, points (% and $, credits shown as negative in green), monthly payment, cash to close, DSCR and cashflow (investment only), investor/product (secondary text), lock days, "Recommended" star toggle, edit, delete.
- Add/Edit overlay: all scenario inputs (price, down payment, PPP, strategy, FICO, lock days, assumed DSCR bucket for investment), live preview of payment and cash to close, and two actions: **Save & AutoQuote** and **Choose manually**.
- Choose manually: sortable grid (investor, product, rate, price, points, P&I, lock days) with par and buydown rows tagged; selecting a row saves it as a quote.
- Compare: select 2–3 cards → side-by-side table with the same rows as the borrower's comparison table.
- Stale banner (from CQ-017) → "Re-price" calls `/reprice`; the cards show a loading state and refresh.
- Error state: a pricing 422 shows "Cannot price: missing {Field}" with a link to the tab that owns the field.

## Out of scope

- Selecting quotes to send (CQ-019).
- Real Optimal Blue; mock only.

## References

- `docs/design/system-design.md` — LO Console → Quote Builder, DSCR pricing loop, Emulated integrations (PricingClient).
- `docs/design/data-field-catalog.md` — §6 OB request/response fields, §10 scenario comparison fields.
- Reference screens: `06-report-pricing-options.png`, `01-loan-advisor-excel-dscr.png`.

## Acceptance criteria

- [ ] AC1 — After `make demo-reset`, Marcus Hale's Pricing tab shows 4 quotes in 2 groups (DSCR 1.00 and his computed DSCR) with no user action, or 2 quotes in 1 group with the same-bucket note if his DSCR buckets match 1.00.
- [ ] AC2 — Every card's payment and cash to close equal the engine output for that quote (API test over all seeded quotes).
- [ ] AC3 — Editing Marcus Hale's scenario to 25% down and pressing Save & AutoQuote replaces that scenario's quotes with a new par and buydown; the new par rate is ≤ the old par rate or equal per the mock rate sheet.
- [ ] AC4 — Choose manually lists ≥ 8 products; picking a row adds a quote card with that rate and points; deleting it removes the card.
- [ ] AC5 — Starring a quote sets it as recommended, unstars any other, and the header note rate updates (CQ-016 header).
- [ ] AC6 — Aisha Coleman's Save & AutoQuote shows "Cannot price: missing Occupancy" and links to the Borrowers/Property tab that owns the field; no quotes are created.
- [ ] AC7 — Priya Nair shows primary groups (no DSCR text anywhere on the cards); Daniel Ortiz's second group is at the down-payment step that removes MI.
- [ ] AC8 — After an override from CQ-017, "Re-price" clears the stale banner and updates `priced_at` on every quote.
- [ ] AC9 — react-doctor passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC7 | API test on seeded data + component test | `test_default_scenario_groups`, `QuoteGroups.test.tsx` |
| AC2 | API test over all seeded quotes | `test_quote_cards_match_engine` |
| AC3, AC4 | Playwright | `e2e/quote-builder.spec.ts` |
| AC5 | API test + component test | `test_single_recommended_quote` |
| AC6 | API test + Playwright | `test_autoquote_missing_occupancy` |
| AC8 | Playwright | `e2e/reprice-after-override.spec.ts` |
| AC9 | react-doctor | evidence in post-dev.md |

## Notes for the agent

- The default groups are created by the pipeline (CQ-011 draft-quote-set stage); this item renders and edits them. If the pipeline does not yet create them, log a `Decision:` and raise it in Kaneo rather than creating them from the frontend.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
