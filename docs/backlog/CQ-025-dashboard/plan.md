# CQ-025 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Attention-list ordering ("oldest status change first") | No dedicated `status_changed_at` column exists and adding one is a migration outside this item's owned files. `Application.updated_at` is bumped by `_transition_status`/portal-action status writes at the moment the status changes, and nothing else touches an application row once it sits in NeedsAttention/Inquiry/OptionSelected. Decided: order the attention list by `Application.updated_at ASC` as the "oldest status change" proxy. |
| 2 | Decision | Attention reason source per status | NeedsAttention → the earliest unresolved `Flag.message` (`created_at ASC`) for that application, falling back to a generic string if none is found (defensive). Inquiry → the latest `QuotePackageVersion.borrower_action["message"]` for the application's package (trimmed to 140 chars as an "excerpt"). OptionSelected → the latest `QuotePackageVersion.borrower_action["quote_id"]` looked up against that version's `snapshot.options[].label`. Both the real runtime `type` values (`move_forward`/`ask_other`/`ask_updated`, written by `portal/actions/service.py`) and the seed fixture's literal `option_selected` value are treated the same way — the reason is derived from the *application status* + `quote_id`/`message` presence, not the `type` string, so the seed rows (`option_selected`) and real portal actions (`move_forward`, `ask_other`, `ask_updated`) both resolve correctly. |
| 3 | Decision | "Stale" list reference date (spec: "recommended quote or latest sent version older than 21 days") | Decided: `reference_at = COALESCE(latest_sent_QuotePackageVersion.sent_at, recommended_Quote.priced_at)` — the sent version is the customer-facing freshness marker and takes priority when one exists (an app that's been sent but never re-priced is "stale" from when it was sent, not from the older internal priced_at); falls back to the recommended quote's `priced_at` for an app that's been priced but never sent. An app with neither (no recommended quote, never sent) is excluded — there's nothing to be "stale". `days_old = floor((core.clock.now() - reference_at))`. Verified against the seed fixture: Grace Kim's `QuotePackageVersion.sent_at` is backdated 25 real days (seed's `apply_send_fixture` uses wall-clock `datetime.now(UTC)`, not `core.clock.now()`), so she is stale under `core.clock.now()` too as long as `make demo-reset` ran recently; Luis Romero's version is 3 days old (not stale); the other priced-only personas have a recent `priced_at` and no sent version (not stale). |
| 4 | Decision | Tile definitions not fully pinned by spec | "Clients" and "Applications" tiles count *all* applications in scope for the client/application-existence check (no property/quote requirement); "Applications" excludes Withdrawn/Closed per spec table; "Clients" does not exclude any status per its literal definition ("≥ 1 application in scope"). "With a property" checks `properties.address_status == specific_address` with no status filter (spec doesn't ask for one). |
| 5 | Decision | Tile `href`s and the LO filter | Tile hrefs use exactly the CQ-025 spec table's parameter names (E10) verbatim, e.g. `/applications?status=sent_or_later`. When a Manager/Admin has an LO selected (not "All"), every tile href additionally carries `&lo_id=<id>` so the destination list is pre-filtered to match the tile's count — otherwise the counts and the list would disagree (AC4). `los` (id + name for every `lo` user) is returned in the dashboard response only for Manager/Admin callers (`null` for an LO), so the frontend never needs a second endpoint for the filter `Select`. |
| 6 | Decision | `GET /api/dashboard` route path vs. spec | Spec literally says `/api/dashboard`; every other feature in this repo mounts under `/api/v1` (AGENTS.md: "spec path `/api/x` means `/api/v1/x`"). Decided: `/api/v1/dashboard`, matching AGENTS.md's documented convention, not a literal reading of the spec's `/api/dashboard`. |

No big gaps.

## Why

The LO's post-login landing page: seven scoped tile counts (link into CQ-027's list, once it exists) plus three short lists (needing attention, going stale, recent activity) so an LO or Manager can answer "what needs me today?" in one glance, per spec.md.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend | create `backend/app/features/dashboard/{__init__,router,schemas,service}.py`, `backend/app/features/dashboard/tests/{__init__,test_dashboard}.py`; modify `backend/app/core/registry.py` (one line) |
| Frontend | modify `apps/lo-console/src/app/(staff)/page.tsx`, `apps/lo-console/src/app/(staff)/page.test.tsx` (remove the Dashboard stub row — real page now, tested separately in the same file); create `apps/lo-console/src/features/dashboard/{api,DashboardPage,Tiles,AttentionList,StaleList,ActivityFeed,LoFilter}.tsx` + `.test.tsx` per component |
| e2e | create `e2e/lo-console/dashboard-tiles.spec.ts` |
| Generated | `packages/api-client` via `make api-client` |
| Docs | `docs/backlog/CQ-025-dashboard/{plan,post-dev}.md` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Schemas + router skeleton | — | `dashboard/{schemas,router,__init__}.py`, `core/registry.py` | endpoint reachable, 401 without auth |
| T2 | Tile counts (scoped) | T1 | `dashboard/service.py` | `test_dashboard_tiles_match_sql`, `test_dashboard_scoping` |
| T3 | Attention list | T1 | `dashboard/service.py` | `test_dashboard_lists_personas` (Aisha, Luis) |
| T4 | Stale list | T1 | `dashboard/service.py` | `test_dashboard_lists_personas` (Grace) |
| T5 | Activity feed + `los` filter list | T1 | `dashboard/service.py` | activity ordering test |
| T6 | Latency check | T2–T5 | — | `test_dashboard_latency` |
| T7 | `make api-client` | T1–T6 | `packages/api-client` | typecheck |
| T8 | Frontend `DashboardPage` + subcomponents | T7 | `apps/lo-console/src/features/dashboard/**`, `(staff)/page.tsx` | Vitest per component |
| T9 | e2e tiles spec | T8 | `e2e/lo-console/dashboard-tiles.spec.ts` | Playwright (AC4 pending, AC5 pending) |

## Wave schedule (stage 3)

Single worker, sequential (no sub-agents) — the backend contract must exist before the frontend/api-client tasks.

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2, T3, T4, T5 | Backend contract + service logic first |
| 2 | T6, T7 | Latency check, then regenerate the client once the contract is stable |
| 3 | T8 | Frontend consumes the generated client |
| 4 | T9 | e2e last |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_dashboard_tiles_match_sql` |
| AC2 | `test_dashboard_scoping` |
| AC3 | `test_dashboard_lists_personas` |
| AC4 | `e2e/lo-console/dashboard-tiles.spec.ts` (hrefs only — pending re-check after CQ-027) |
| AC5 | `test_attention_list_updates_after_resolve` (pending re-check after CQ-028) |
| AC6 | `test_dashboard_latency` |
| AC7 | react-doctor + keyboard check, evidence in post-dev.md |

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
