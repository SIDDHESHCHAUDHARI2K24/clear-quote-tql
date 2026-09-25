# CQ-023 Property matches

| Field | Value |
| --- | --- |
| Phase | P4 Borrower Tier A |
| Depends on | CQ-022, CQ-013 |
| Kaneo task | CQ-023 in Kaneo (task id `yslb0ydz5pswvy6a107dums4`) |
| Branch | `cq-023-property-matches` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

A borrower with no property yet gets three real-looking homes they can afford, in the markets they chose, each run through the same numbers as their quote. It turns the pre-approval into a next step.

## Scope

**Backend (owned by this item)**

- Service `find_matches(application, recommended_option) -> list[Match]`:
  1. Runs only when the property is TBD and `recommend_matches` is on (default on when TBD, from CQ-028's Property tab toggle; seeded values until then).
  2. Price band: 70%–100% of the approved purchase price (hard floor and ceiling).
  3. Geography: listings in the application's `buy_box_states` and `buy_box_market_cities`.
  4. Strategy fit: primary → owner-occupant listings; LTR → ranked by monthly cashflow; STR → ranked by DSCR, STR-permitted listings only.
  5. For each candidate, runs `quote_engine` with the recommended option's terms (down payment %, rate, points, PPP) and the listing's price, tax rate, insurance, HOA, and market rent or STR revenue from the mock providers.
  6. Returns the top 3 with: listing id, image URL, address, beds/baths/sqft, deal grade, tagline, total monthly payment, rent estimate (LTR or STR, labelled), monthly cashflow, cash to close, cap rate, year-1 cost-seg tax savings (investment only).
- `GET /api/applications/{id}/matches` (LO auth) returns the current matches.
- Package integration: when a package draft is built (CQ-019) or a version is frozen (CQ-020), matches are computed and stored in `ReportViewModel.matches`; they are frozen with the version. If CQ-019/CQ-020 are not merged yet, add the hook behind a function the send workflow calls and log a `Decision:`.

**Components and page**

- `MatchCard` and `MatchList` in `packages/ui/src/report/` ("Your top 3 property matches", subtitle "Selected for your budget and markets, each run through the same numbers"). Primary matches omit rent, cashflow, cap rate and tax savings.
- Rendered in the report page slot (CQ-022) and therefore in the LO preview (CQ-019).
- Empty state: section hidden entirely when there are no matches.

## Out of scope

- Real listing search; the mock `PropertySearchClient` and seeded listings (CQ-009, CQ-010) are the source.
- Listing detail pages or external links.

## References

- `docs/design/system-design.md` — Borrower Portal → Quote report item 8, Emulated integrations (PropertySearchClient).
- `docs/design/data-field-catalog.md` — §4 buy-box fields, §11 property match engine fields.
- Reference screen: `11-property-matches.png`.

## Acceptance criteria

- [ ] AC1 — Kathleen McReynolds (LTR, TBD, $300,000 approved) gets exactly 3 matches, each priced from $210,000 to $300,000, inside her buy-box metros, sorted by monthly cashflow descending.
- [ ] AC2 — Each match's payment and cash to close equal `quote_engine` output for that listing with her recommended option's terms (API test recomputes them).
- [ ] AC3 — Priya Nair (specific address) gets no matches and her report has no matches section.
- [ ] AC4 — Turning `recommend_matches` off for a TBD persona removes the section from the next package draft.
- [ ] AC5 — An STR TBD persona's matches are STR-permitted and sorted by DSCR; primary matches show no rental fields.
- [ ] AC6 — A listing at 69% or 101% of the approved price is never returned (unit test with boundary listings).
- [ ] AC7 — Matches are frozen with the sent version: changing seeded listings after send does not change the borrower's report.
- [ ] AC8 — react-doctor passes; cards are readable at 375 px (one column) and 1120 px (three columns).

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | Service + API tests on seeded data | `test_matches_kathleen`, `test_match_numbers_match_engine` |
| AC3, AC4 | API tests | `test_no_matches_with_address`, `test_matches_toggle_off` |
| AC5 | Service test with STR and primary fixtures | `test_match_ranking_by_strategy` |
| AC6 | Unit test | `test_price_band_boundaries` |
| AC7 | Integration test | `test_matches_frozen_in_version` |
| AC8 | Playwright viewports + react-doctor | `e2e/report-matches.spec.ts` |

## Notes for the agent

- If CQ-010's seed lacks enough listings in a persona's buy-box to reach 3 results, add listings to the seed in this item and note it in post-dev.md.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
