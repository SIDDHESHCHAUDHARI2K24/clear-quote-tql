# CQ-027 Applications list

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016 |
| Kaneo task | CQ-027 in Kaneo (task id `n44hsne4d6fminjygqwy0et2`) |
| Branch | `cq-027-applications-list` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

Every loan application in one filterable table, so the LO (or a manager) can slice the pipeline by status, strategy, amount, place or person and jump straight into a file.

## Scope

**Backend (owned by this item)**

- `GET /api/applications` with:

| Parameter | Behaviour |
| --- | --- |
| `q` | Client name or email, partial, case-insensitive |
| `lo_id` | Manager/Admin only; LOs are always scoped to themselves |
| `status` | Comma list of status values, plus the alias `sent_or_later` (Sent, Viewed, Inquiry, OptionSelected, and Stale after a send) |
| `strategy` | Comma list of `primary`, `ltr`, `str` |
| `amount_min`, `amount_max` | Purchase price range |
| `state` | Subject state (2 letters); TBD properties match on buy-box states |
| `has_property` | `true` = specific address, `false` = TBD |
| `created_from`, `created_to` | Created date range |
| `sort` | `-updated_at` (default), `amount`, `-amount`, `client`, `status` |
| `page`, `page_size` | Default 25, max 100 |

- Row: application id, client name, property label (address or "TBD · {metros}"), strategy, purchase price, status, open flag count, assigned LO, updated at.

**Frontend (`apps/lo-console`)**

- `/applications`: filter bar (search, status multi-select, strategy chips, amount range, state select, has-property toggle, date range, LO select for Manager/Admin), "Clear filters", sortable table using the shared `ApplicationRow`, pagination, row click → `/applications/[id]`.
- Status pills use the same colours as the workspace header (CQ-016). Flag count shows as a red badge when > 0.
- All filters in the URL; dashboard tile links (CQ-025) land here with filters applied.

## Out of scope

- Bulk actions, CSV export.

## References

- `docs/design/system-design.md` — LO Console → Applications; Application status machine.
- Built code to check in stage 1: CQ-016 summary endpoint and header components (reuse the status pill), CQ-014 scoping.

## Acceptance criteria

- [ ] AC1 — Each filter alone, and three combined (e.g. `status=Priced&strategy=str&state=FL`), return exactly the rows of the equivalent SQL over the seed.
- [ ] AC2 — `status=NeedsAttention` includes Aisha Coleman with flag count ≥ 1; `status=Stale` includes Grace Kim; `has_property=false` includes Kathleen McReynolds labelled "TBD · …".
- [ ] AC3 — `status=sent_or_later` returns the same count as the dashboard "Pre-approvals sent" tile.
- [ ] AC4 — An LO passing another LO's `lo_id` still gets only their own rows.
- [ ] AC5 — The endpoint responds in under 300 ms for any filter combination on the seed (indexes added where needed).
- [ ] AC6 — Filters survive reload and back navigation; "Clear filters" resets the URL.
- [ ] AC7 — react-doctor passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Parametrized API test vs SQL | `test_application_filters_match_sql` |
| AC2 | API test on personas | `test_application_list_personas` |
| AC3 | API test | `test_sent_or_later_matches_dashboard` |
| AC4 | API test | `test_application_list_scoping` |
| AC5 | API timing test | `test_application_list_latency` |
| AC6 | Playwright | `e2e/applications-list.spec.ts` |
| AC7 | react-doctor | evidence in post-dev.md |

## Notes for the agent

- If CQ-025 is already built, match its tile link parameters exactly.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
