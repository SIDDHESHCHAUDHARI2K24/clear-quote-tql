# CQ-026 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Scoping basis | "An LO never sees clients whose applications all belong to other LOs" is evaluated against `Application.lo_id` (an `EXISTS` over the client's applications), not `Client.assigned_lo_id` — matches the spec's own wording. A client with zero applications is therefore invisible to a scoped LO (vacuously "all belong to other LOs") but still visible to an unscoped Manager/Admin. |
| 2 | Decision | `application_count` | Total application count for the client (all statuses), matching the Goal's "every application". |
| 3 | Decision | `active application status` | The status of the client's most-recently-updated *active* application (status not in `{withdrawn, closed}`); `null` when the client has none. `has_active` filters on "at least one active application exists". |
| 4 | Decision | `sort` values | Exactly the three spec tokens (`name`, `-created_at`, `-last_activity`) are accepted; anything else 422s, same style as `listing.service._order_by`. Default is `-last_activity` (most relationship-relevant first) — not specified by spec.md, small necessity. |
| 5 | Decision | `last_activity` | `MAX(activity_events.at)` across every application the client has (correlated subquery), not just the most recent application — matches "what happened when" in the Goal. |
| 6 | Decision | Applications section (detail) | Re-derives `ApplicationRow` rows locally (small, scoped duplication of `listing/service.py`'s field mapping) rather than importing its private `_base_query`/`_row_to_schema` — mirrors `portal/reports/versions.py`'s own precedent ("duplicated here as a small, feature-local helper rather than importing another feature's underscore-prefixed symbol"). `ApplicationRow` (the schema) is still imported and reused unchanged (E9). |
| 7 | Decision | Activity section (detail) | `applications/timeline/service.py`'s docstring invites CQ-026 to reuse *the service*: originally called the public `list_activity(db, application, page=1, page_size=50)` once per application and merged/sorted/truncated to 50 in Python. Superseded by decision #16 (review round 1): a new public `list_activity_for_applications(db, applications, limit=50)` in that same module does the merge in one query instead. No new backend endpoint either way. |
| 8 | Decision | `ActivityTimeline` (frontend) reuse | Extended with an optional `events` prop: when given, the component renders that pre-fetched, already-merged list directly (no fetch, no per-application pagination — spec.md's "latest 50" needs none) instead of fetching by `applicationId`. `applicationId` becomes optional; exactly one of `applicationId`/`events` is expected per usage. Logged per spec's "Notes for the agent" allowance for a small `ActivityTimeline` prop edit. |
| 9 | Decision | Sent-version `status` | Derived, not stored: `superseded` (flag set) > `expired` (`expired_at` set, or `now >= expires_at`) > the `borrower_action["type"]` string when present (`option_selected`/`move_forward`/`ask_other`/`ask_updated`/`inquiry`) > `viewed` (`viewed_at` set) > `sent`. |
| 10 | Decision | Sent-version `recommended option label` | Read from the frozen `snapshot` JSON's `options[]` (CQ-021 `ReportOption.label`/`.recommended`); the option with `recommended: true`, or `null` if the snapshot has none. |
| 11 | Decision | "report link for the LO preview" | No LO-authenticated report preview exists yet (`/portal/reports/{token}` requires `CurrentBorrower`). Returns the borrower-portal's full URL `{portal_base_url}/report/{token}` as `report_link` (code review round 1: a bare relative path 404s from the LO console's own origin since the two Next.js apps run on separate ports/origins -- fixed to reuse `core.config.settings.portal_base_url`, the same setting `applications/sections/credit.py` already uses for its consent-request link). Building an LO-authenticated preview path is out of this item's scope. |
| 12 | Decision | `phone` nullability | `clients.phone` is nullable in the model; rows/detail pass it through as `null` when unset — frontend shows "—". |
| 13 | Fix (code review round 1) | `ApplicationRow.lo_name` in the detail's "Applications" section | Originally passed the *client's* assigned-LO name for every row. A client can have applications assigned to different LOs over time, and `ApplicationRow.lo_id` is per-application (E9's own shape) -- fixed `_application_rows` to batch-look-up each application's own `lo_id` -> name, and added a regression test (`test_client_detail_scoping_needs_active_application` now asserts each row's `lo_name` independently). |
| 14 | Fix (review round 1, critical) | Cross-LO data leak in `get_client_detail` | `_application_rows_for_client` returned *every* application on the client regardless of role, so an LO viewing a client shared with another LO saw the other LO's applications, sent versions and activity too -- contradicting `core/auth.py::scope_applications`'s "an LO only ever sees their own applications" (CQ-014). Fixed: `_application_rows_for_client(db, client_id, user)` now runs its query through `scope_applications`, the same helper every other application-scoped route uses. The gate simplified to "no in-scope applications for an LO -> 404" (no separate existence check needed -- `scope_applications` already answers it). Manager/Admin unaffected (still see every application). `test_client_detail_scoping_needs_active_application` rewritten to assert the LO sees only their own application/version/activity; `test_client_detail_manager_sees_every_lo_application` added for the Manager side. |
| 15 | Decision (review round 1) | List-level aggregates (`application_count`/`active_status`/`last_activity`) for an LO | Scoped to the requesting LO's own applications only (`_application_scope_clauses(lo_scope)`, `lo_scope = user.id` when `user.role == LO`), so a shared client's row doesn't reveal another LO's application count or active status to the LO. A Manager/Admin's aggregates stay unscoped even when filtering by `lo_id` -- that filter narrows which clients appear, not what a Manager (who can already see everything) is told about them. Tested: `test_client_list_aggregates_scoped_to_lo_own_applications`, `test_client_list_aggregates_unscoped_for_manager`. `has_active`'s filter predicate (`_client_active_exists`) was left unscoped -- out of the three named aggregates, and the existing `has_active` tests already pass unscoped as a Manager; revisit if a future item needs an LO-scoped `has_active` too. |
| 16 | Fix (review round 1, minor) | `_merged_activity` batching | Called `list_activity` once per application (each re-fetching the client row, each over-fetching up to `limit` per application before a Python re-sort/truncate). Replaced with a new public `applications.timeline.service.list_activity_for_applications(db, applications, limit=50)`: one query across every scoped application's events (`ORDER BY at DESC, id DESC LIMIT 50`, matching `list_activity`'s own order) and one batched staff-name lookup, sharing a new `_events_to_out` helper with `list_activity`. |
| 17 | Fix (review round 1, small necessity) | Unescaped `q` LIKE wildcards | `clients/service.py`'s `q` (and `applications/listing/service.py`'s own `q`, CQ-027) built an unescaped `ILIKE` pattern, so a literal `%`/`_` in the search text acted as a SQL wildcard instead of matching literally -- same bug the outbox's `q` had before its own code-review fix. `notifications/outbox/service.py::_escape_like`/`_LIKE_ESCAPE` moved to a new `core/sql.py` (`escape_like`/`LIKE_ESCAPE_CHAR`) and reused by all three (outbox, clients, applications listing) instead of three copies. Tested: `test_client_search_escapes_like_wildcards`, `test_q_filter_escapes_like_wildcards` (applications listing). |

No big gaps found against spec.md; CQ-027 (`ApplicationRow`, `/applications/los`) and CQ-029 (`ActivityTimeline`, `list_activity`) are already merged, so nothing here is blocked.

## Why

The LO/Manager needs one page per borrower relationship — contact info, every application, every sent quote, and the combined timeline — instead of hunting through the applications list per client. CQ-026 also removes the last `(staff)` shell stub.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend | `backend/app/features/clients/schemas.py` (new), `service.py` (new), `router.py` (new), `tests/conftest.py`, `tests/test_search.py`, `tests/test_filters.py`, `tests/test_scoping.py`, `tests/test_detail.py`, `tests/test_latency.py` (all new); `backend/app/core/registry.py` (append one line) |
| Frontend | `apps/lo-console/src/features/clients/**` (new: `types.ts`, `api.ts`, `filters.ts`, `useClientFilters.ts`, `format.ts`, `components/ClientsTable.tsx`, `components/ClientsFilterBar.tsx`, `components/ClientDetailHeader.tsx`, `components/SentVersionsTable.tsx`, `index.ts`, plus `.test.tsx`/`.test.ts`), `apps/lo-console/src/app/(staff)/clients/page.tsx` (replace stub), `.../clients/[id]/page.tsx` (new) |
| Small necessity | `apps/lo-console/src/features/activity/ActivityTimeline.tsx` (optional `events` prop, logged Decision 8); `apps/lo-console/src/app/(staff)/page.test.tsx` and `e2e/lo-console/shell.spec.ts` (remove the Clients stub-row assertions) |
| Contract | `make api-client` regeneration after the backend lands |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Schemas: `ClientRow`, `ClientListResponse`, `ApplicationSentVersion`, `ClientDetail` | — | `clients/schemas.py` | — |
| T2 | Service: `list_clients` (search/filters/sort/scoping/pagination), `get_client_detail` (contact + applications + sent versions + merged activity, 404 scoping) | T1 | `clients/service.py` | test_search, test_filters, test_scoping, test_detail |
| T3 | Router: `GET /clients`, `GET /clients/{id}` | T2 | `clients/router.py`, `core/registry.py` | test_detail (404 path), latency |
| T4 | Backend tests | T2, T3 | `clients/tests/**` | all 5 named tests |
| T5 | `make api-client` | T3 | `packages/api-client/**` | tsc |
| T6 | Frontend data layer: types/api/filters/useClientFilters/format | T5 | `features/clients/{types,api,filters,useClientFilters,format}.ts` | vitest |
| T7 | Frontend list UI: `ClientsTable`, `ClientsFilterBar`, `/clients` page | T6 | `features/clients/components/{ClientsTable,ClientsFilterBar}.tsx`, `app/(staff)/clients/page.tsx` | vitest, e2e AC6 |
| T8 | Frontend detail UI: header, applications (reused `ApplicationRow`), sent versions, activity (reused `ActivityTimeline`), empty states, `/clients/[id]` page | T6 | `features/clients/components/{ClientDetailHeader,SentVersionsTable}.tsx`, `app/(staff)/clients/[id]/page.tsx` | vitest |
| T9 | `ActivityTimeline` `events` prop | — | `features/activity/ActivityTimeline.tsx` | vitest |
| T10 | Remove stub-row assertions | T7 | `(staff)/page.test.tsx`, `e2e/lo-console/shell.spec.ts` | vitest |
| T11 | `e2e/lo-console/clients-list.spec.ts` | T7 | e2e spec | Playwright |

## Wave schedule (stage 3)

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2, T3, T4 | Contract first — schema/service/router/tests before anything consumes them |
| 2 | T5 | Regenerate api-client from the new OpenAPI schema |
| 3 | T6, T9 | Frontend data layer + the small `ActivityTimeline` edit, independent of each other |
| 4 | T7, T8 | List and detail UI, both depend on T6 only, no shared files |
| 5 | T10, T11 | Cleanup + e2e, after the real pages exist |

(Single-agent execution in practice — tasks run sequentially in this session, not dispatched to parallel subagents, given the size of the item.)

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_client_search` (name substring, email substring, case-insensitivity) |
| AC2 | `test_client_filters_match_sql` (parametrized: each filter/sort vs. a direct SQL/Python-computed expectation) |
| AC3 | `test_client_scoping` (LO sees only clients with an application of their own; Manager sees all and can filter by `lo_id`) |
| AC4 | `test_client_detail_marcus_hale` (applications, sent version + recommended option, timeline newest-first) |
| AC5 | `test_clients_latency` (list + detail under 300 ms on a ~250-row fixture set) |
| AC6 | `e2e/lo-console/clients-list.spec.ts` (filters/page survive reload + back) |
| AC7 | `npx react-doctor -y --blocking error`, logged in post-dev.md |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
- [x] T8
- [x] T9
- [x] T10
- [x] T11
