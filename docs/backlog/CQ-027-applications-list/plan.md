# CQ-027 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Route path | `GET /applications` (→ `/api/v1/applications`) lives in a new `features/applications/listing/router.py`, separate from `applications/router.py` (pipeline) and `applications/summary/router.py`, both already registered. |
| 2 | Decision | `state` filter source | `applications.subject_state` exists on the model (P5/P6 foundation denorm column) but nothing populates it anywhere in the codebase yet — populating it is out of my owned files (`property/service.py`, pipeline activities). Decided: compute `state` by joining `properties` directly — `properties.state` for a specific address, `ANY(properties.buy_box_states)` for TBD — matching the spec text "TBD properties match on buy-box states" exactly and needing no other feature's files touched. `applications.subject_state` is left as-is (unused by this endpoint; a later item may wire it up). |
| 3 | Decision | `has_property` semantics | Mirrors CQ-025's tile ("Property is a specific address (not TBD)"): `true` = a `properties` row exists with `address_status = specific_address`; `false` = anything else (TBD row, or — for the ~200 bare background-seed applications that never get a `properties` row — no row at all). |
| 4 | Decision | `strategy=primary` | `Strategy` enum has only `ltr`/`str`; `primary` is a third filter value per spec's own list. `core/enums.py`'s own `Strategy` docstring: "Null on `applications.strategy` when `occupancy = primary`". Decided: `strategy=primary` ⇔ `applications.strategy IS NULL`, not `occupancy = 'primary'` — Aisha Coleman's `occupancy` is `NULL` (her missing-field flag) while her `strategy` is `ltr`, so an occupancy-based rule would put her under neither `primary` nor `ltr`; the strategy-field rule keeps the filter and the row's own displayed `strategy` (`"primary" \| "ltr" \| "str"`) using one consistent source. |
| 5 | Decision | `amount` | Spec calls it "purchase price range" — `applications.requested_price`. `sort=amount/-amount` and `amount_min/amount_max` both use this column. |
| 6 | Decision | `sent_or_later` / Stale-after-a-send | Spec: "Sent, Viewed, Inquiry, OptionSelected, and Stale after a send". Per CQ-030 spec.md, an application can reach `Stale` from `Priced` alone (never sent) or from `Sent`/`Viewed` — so `status=stale` alone is not sufficient. Decided: "sent" = `EXISTS` a `quote_package_versions` row (via `quote_packages.application_id`) — every send freezes exactly one version (P3/P4 foundation D2), so this is the authoritative "has this application ever been sent" signal, cheaper than joining `quote_packages.sent_at`. Exposed as `listing.service.build_sent_or_later_filter()` (a SQLAlchemy boolean expression on `Application`/a correlated `EXISTS`) for CQ-025 to import verbatim (AC3, E10). |
| 7 | Decision | Status URL labels | Dashboard tile links (CQ-025 spec, E10) use the spec's PascalCase labels (`NeedsAttention`, `Stale`, `Priced,Inquiry,OptionSelected`, `sent_or_later`). Decided: `status=` accepts a comma list of either the PascalCase labels or the raw snake_case enum values (defensive — the two are trivially different strings), plus the `sent_or_later` alias (case-sensitive, lowercase, exactly as CQ-025 spec.md writes it). Unknown tokens → 422 `ValidationAppError`. |
| 8 | Decision | Property label | `{street_address}, {city}, {state}` (parts joined, skipping any missing part) when a specific address exists; `"TBD · " + ", ".join(buy_box_metros)` when TBD (metros = `buy_box_metros`, matching Kathleen McReynolds' `buy_box_market_cities: [Davenport, Orlando]` → `"TBD · Davenport, Orlando"`); `None` when no `properties` row exists (the ~200 bare background rows) — frontend renders "—". |
| 9 | Decision | Flag count | `COUNT(flags.id)` where `flags.application_id = applications.id AND flags.resolved_at IS NULL` (a correlated scalar subquery), using the existing `ix_flags_application_id_resolved_at` index. |
| 10 | Decision | AC2 "status=Stale includes Grace Kim" vs current seed | `make demo-reset` seeds Grace with `status=sent` (CQ-030's stale job — a wave-2 sibling — is what would actually flip her to `stale`; nothing in today's seed/reset path calls it). Decided (stage 7 rule for an unbuilt sibling): verify the `status=Stale` *filter* itself with a test fixture that sets an application's status to `stale` directly (with and without a sent `quote_package_version`, to also pin the AC6 `sent_or_later` boundary) rather than relying on `make demo-reset` output. Logged as "pending — re-check after CQ-030" in post-dev.md for the true end-to-end demo-reset case. |
| 11 | Decision | Indexes (AC5) | `applications.lo_id`, `.status`, `.client_id` are already indexed; `flags` has the composite index above. Added: `ix_applications_updated_at` (default sort), `ix_applications_created_at` (date-range filter), `ix_applications_requested_price` (amount-range filter) — one small migration chained off `3b55187d53d7`. |

No big gaps.

## Why

Every loan file needs to be findable from one filterable, sortable, paginated table so an LO or manager can jump straight into a file instead of scanning the dashboard. This item also owns the `ApplicationRow` component and row schema that CQ-026 (Clients) reuses in the next wave, and the `sent_or_later` query definition that CQ-025 (Dashboard) must match exactly (AC3).

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend | create `backend/app/features/applications/listing/{__init__,router,schemas,service}.py` + `listing/tests/{__init__,test_router,test_service,test_latency}.py`; modify `backend/app/core/registry.py` (+1 line) |
| Migration | create `alembic/versions/<rev>_applications_list_indexes.py` (down_revision `3b55187d53d7`) |
| Frontend | create `apps/lo-console/src/features/applications/{api,filters,ApplicationRow-row-schema types}.ts`, `components/ApplicationRow.tsx` (+ test), `ApplicationsFilterBar.tsx` (+ test), `ApplicationsTable.tsx` (+ test), `useApplicationFilters.ts` (URL state, + test), `index.ts`; modify `apps/lo-console/src/app/(staff)/applications/page.tsx` |
| e2e | create `e2e/lo-console/applications-list.spec.ts` |
| Generated | `packages/api-client` via `make api-client` |
| Docs | this `plan.md`, `post-dev.md`, `handoff.md` if needed |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration: 3 indexes | — | migration file | `alembic upgrade head` / `alembic check` clean; `alembic heads` = 1 |
| T2 | `listing/schemas.py`: `ApplicationRow`, `ApplicationListResponse` (`Page[ApplicationRow]`) | — | schemas.py | covered by T4 |
| T3 | `listing/service.py`: `list_applications(db, user, ...)`, `build_sent_or_later_filter()`, status/strategy/property-label helpers | T1 | service.py | `test_service.py` |
| T4 | `listing/router.py`: `GET /applications`, query-param parsing/validation, register in `registry.py` | T2, T3 | router.py, registry.py | `test_router.py` (AC1, AC2, AC4, AC6) |
| T5 | Latency test | T4 | test_latency.py | `test_latency.py` (AC5) |
| T6 | `make api-client` | T4 | packages/api-client | generated diff only |
| T7 | `ApplicationRow` component + list row types | T6 | components/ApplicationRow.tsx | `ApplicationRow.test.tsx` |
| T8 | Filter bar, table, pagination, URL state hook | T7 | remaining `src/features/applications/**` | Vitest per component |
| T9 | `(staff)/applications/page.tsx` | T8 | page.tsx | `page.test.tsx` |
| T10 | e2e spec | T9 | e2e/lo-console/applications-list.spec.ts | Playwright (AC6) |

## Wave schedule (stage 3)

Single worker, sequential (no sub-agents needed for a unit this size).

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2, T3 | Migration and service before anything depends on them |
| 2 | T4, T5 | Router wraps the service; latency needs the router |
| 3 | T6 | Regenerate client before the frontend imports types |
| 4 | T7, T8, T9 | Frontend, component first (CQ-026 dependency) |
| 5 | T10 | e2e last |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_router.py::test_application_filters_match_sql` (parametrized, each filter alone + 3 combos, vs raw SQL over a fixture dataset built in the test) |
| AC2 | `test_router.py::test_application_list_personas` (Aisha/flag count, Kathleen/TBD label; Grace/Stale via fixture per Decision 10) |
| AC3 | `test_service.py::test_sent_or_later_matches_dashboard_definition` (SQL-equivalence check per E2E_NOTE; cross-check against the real CQ-025 endpoint marked pending — re-check after CQ-025) |
| AC4 | `test_router.py::test_application_list_scoping` |
| AC5 | `test_latency.py::test_application_list_latency` |
| AC6 | `e2e/lo-console/applications-list.spec.ts` |
| AC7 | react-doctor, evidence in post-dev.md |

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
