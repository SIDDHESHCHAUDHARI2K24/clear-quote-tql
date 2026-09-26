# CQ-026 Clients

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016 |
| Kaneo task | CQ-026 in Kaneo (task id `k5qicjm8rto4hu78purdun43`) |
| Branch | `cq-026-clients` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The LO can find any borrower TQL has worked with and see their whole relationship on one page: contact details, every application, every quote sent, and what happened when.

## Scope

**Backend (owned by this item)**

- `GET /api/clients` with `q` (name or email, case-insensitive, partial), `lo_id`, `created_from`, `created_to`, `has_active` (bool), `sort` (`name`, `-created_at`, `-last_activity`), `page`, `page_size` (default 25, max 100). Returns rows: client id, name, email, phone, assigned LO, application count, active application status, last activity. Role scoping as in CQ-014.
- `GET /api/clients/{id}` → contact details, applications (same row shape as the CQ-027 list), sent versions across applications (sent date, recommended option label, status, report link for the LO preview), and the merged activity timeline (latest 50 events).

**Frontend (`apps/lo-console`)**

- `/clients`: search box (debounced 300 ms), filters (assigned LO for Manager/Admin, created date range, active only), sortable table, pagination. Filters and page in the URL.
- `/clients/[id]`: header with name, contact details and assigned LO; sections "Applications" (shared `ApplicationRow` component, also used by CQ-027), "Quotes sent", "Activity" (timeline component from CQ-029 if merged, otherwise a simple list to be swapped later — log a `Decision:`).
- Empty states for no results and no applications.

## Out of scope

- Creating or editing clients (clients come from import or the borrower portal).
- CRM sync UI.

## References

- `docs/design/system-design.md` — LO Console → Clients; Data model (`clients`, `applications`, `quote_package_versions`, `activity_events`).
- Built code to check in stage 1: models (CQ-007), role scoping (CQ-014), `ApplicationRow` if CQ-027 already built it.

## Acceptance criteria

- [ ] AC1 — Searching "hale" returns Marcus Hale; searching part of an email returns its client; results are case-insensitive.
- [ ] AC2 — Each filter and each sort returns exactly the rows a direct SQL query returns (parametrized test over the seed).
- [ ] AC3 — An LO never sees clients whose applications all belong to other LOs; a Manager sees all and can filter by LO.
- [ ] AC4 — Marcus Hale's detail page lists his application(s), his sent version(s) with the recommended option, and his timeline in reverse time order.
- [ ] AC5 — The list and detail endpoints each respond in under 300 ms on the seeded data.
- [ ] AC6 — Filters and page survive a reload and the browser back button.
- [ ] AC7 — react-doctor passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | API tests over seed | `test_client_search`, `test_client_filters_match_sql` |
| AC3 | API test by role | `test_client_scoping` |
| AC4 | API + component test | `test_client_detail_marcus_hale` |
| AC5 | API timing test | `test_clients_latency` |
| AC6 | Playwright | `e2e/clients-list.spec.ts` |
| AC7 | react-doctor | evidence in post-dev.md |

## Notes for the agent

- `ApplicationRow` belongs in `apps/lo-console/src/features/applications/components/`; whichever of CQ-026/CQ-027 runs first creates it, the other reuses it.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
