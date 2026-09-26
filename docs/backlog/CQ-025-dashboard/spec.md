# CQ-025 Dashboard

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016 |
| Kaneo task | CQ-025 in Kaneo (task id `xkbost5i2wf96mdm8k1r0k6k`) |
| Branch | `cq-025-dashboard` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The LO's landing page after login answers "what needs me today?" in one glance: how many files are in each state, which ones are waiting on the LO, which quotes are going stale, and what just happened. Every number is a link into the filtered list.

## Scope

**Backend (owned by this item)**

- `GET /api/dashboard?lo_id=` (LO: always their own files; Manager/Admin: all files, or one LO when `lo_id` is set). Returns:
  - `tiles`: counts for the statuses in the table below.
  - `attention`: up to 10 applications in NeedsAttention, Inquiry or OptionSelected, oldest status change first, each with client name, status, reason (flag message, inquiry note excerpt or selected option label) and age.
  - `stale`: up to 10 applications whose recommended quote or sent version is older than 21 days, with days old.
  - `activity`: the latest 20 activity events across the LO's applications (actor, type, application, time).
- Tile definitions (one query each, all scoped by role):

| Tile | Definition | Links to |
| --- | --- | --- |
| Clients | Distinct clients with ≥ 1 application in scope | `/clients` |
| Applications | Applications not Withdrawn or Closed | `/applications` |
| Pre-approvals sent | Status in Sent, Viewed, Inquiry, OptionSelected, or Stale after a send | `/applications?status=sent_or_later` |
| With a property | Property is a specific address (not TBD) | `/applications?has_property=true` |
| Awaiting your review | Status in Priced, Inquiry, OptionSelected | `/applications?status=Priced,Inquiry,OptionSelected` |
| Needs attention | Status NeedsAttention | `/applications?status=NeedsAttention` |
| Stale quotes | Status Stale | `/applications?status=Stale` |

**Frontend (`apps/lo-console`)**

- Route `/` (after login) → Dashboard. Top nav: Dashboard, Clients, Applications, Outbox; Settings and Integration panel in the user menu for Admin.
- Seven tiles in one responsive row (wraps at < 1280 px); each tile is a link.
- "Needs your attention" list, "Going stale" list and "Recent activity" feed, each with an empty state ("Nothing needs you right now").
- Manager/Admin: an LO filter (select) above the tiles; the choice stays in the URL.
- Refresh every 30 s while the tab is visible.

## Out of scope

- Charts or trends over time.
- The list pages the tiles link to (CQ-026, CQ-027) beyond agreeing the query parameters.

## References

- `docs/design/system-design.md` — Application status machine (Dashboard tiles), LO Console → Dashboard.
- Built code to check in stage 1: status enum and activity events (CQ-007, CQ-011), role scoping (CQ-014).

## Acceptance criteria

- [x] AC1 — After `make demo-reset`, every tile count for a Manager equals a direct SQL count of the definition above (test computes both).
- [x] AC2 — An LO sees only counts for their own files; a Manager filtering by that LO sees the same numbers.
- [x] AC3 — Aisha Coleman appears in "Needs your attention" with her missing-field reason; Luis Romero appears with his selected option; Grace Kim appears in "Going stale" with her age in days.
- [ ] AC4 — Each tile's link opens the Applications list with the matching filter and the list shows exactly the tile's count (Playwright, once CQ-027 is merged; before that, assert the URL). **pending — re-check after CQ-027** (today: hrefs asserted, unit + live e2e)
- [ ] AC5 — Resolving Aisha's flag (CQ-028, or directly via API) removes her from the attention list within one refresh. **pending — re-check after CQ-028** (today: resolved directly in the DB per the coordinator's E2E note)
- [x] AC6 — `GET /api/dashboard` responds in under 300 ms with the ~200 seeded applications.
- [x] AC7 — react-doctor passes; tiles and lists are keyboard navigable.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | API test comparing to SQL | `test_dashboard_tiles_match_sql` |
| AC2 | API test by role | `test_dashboard_scoping` |
| AC3 | API test on seeded personas | `test_dashboard_lists_personas` |
| AC4 | Playwright | `e2e/dashboard-tiles.spec.ts` |
| AC5 | Integration test | `test_attention_list_updates_after_resolve` |
| AC6 | API timing test | `test_dashboard_latency` |
| AC7 | react-doctor + keyboard check | evidence in post-dev.md |

## Notes for the agent

- Agree the list query parameter names with CQ-027 in your plan (the table above is the proposal); if CQ-027 is already built, use its names.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
