# CQ-026 — Post-development notes

## Summary

Built `GET /api/v1/clients` (search, LO/date-range/active filters, sort, role-scoped pagination) and `GET /api/v1/clients/{id}` (contact details, applications reusing CQ-027's `ApplicationRow`, sent quote versions with the recommended option and a status derived from the frozen snapshot, and a merged activity timeline built on CQ-029's `list_activity`). The frontend adds `/clients` (filter bar, sortable table, pagination, all state in the URL) and `/clients/[id]` (header, Applications, Quotes sent, Activity — reusing `ApplicationRow` and a lightly-extended `ActivityTimeline`), replacing both `(staff)/clients` stub routes. `make api-client` was regenerated and the router registered in `core/registry.py`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET /api/clients...` | `GET /api/v1/clients...` | AGENTS.md: every spec path is under `/api/v1` (matches CQ-027's own precedent). |
| "report link for the LO preview" | A relative `/report/{token}` path, rendered as a link | No LO-authenticated report-preview route exists yet (`/portal/reports/{token}` requires a borrower session); building that auth path is out of this item's scope (plan.md Decision 11). |
| "the merged activity timeline" | Built by calling the public `list_activity()` once per application and merging in Python | `applications/timeline/service.py`'s own docstring invites this reuse; its private helpers (`describe_event`, `_resolve_actor`) were not imported, matching this codebase's own precedent of not importing another feature's private symbols (`portal/reports/versions.py`) (plan.md Decision 7). |
| `ActivityTimeline` reuse | Given an optional `events` prop (pre-fetched, merged list) alongside the existing `applicationId` fetch mode | Logged per spec's "Notes for the agent" allowance for a small, cross-owned component edit (plan.md Decision 8). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/clients/tests/test_search.py::test_client_search` — "hale"/"HALE"/email-substring/no-match, all case-insensitive |
| AC2 | Met | `backend/app/features/clients/tests/test_filters.py` (created-date range, has_active, sort=name/-created_at/-last_activity with NULLS LAST, unknown sort 422, pagination) — each expectation computed independently from the fixtures' own attributes |
| AC3 | Met | `backend/app/features/clients/tests/test_scoping.py` — LO sees only clients with an application of their own (including the zero-application "orphan" case), LO's own `lo_id` param is ignored, Manager sees all and can filter by `lo_id`, detail 404s out of scope |
| AC4 | Met | `backend/app/features/clients/tests/test_detail.py::test_client_detail_marcus_hale` — real seeded Marcus Hale persona: 1 application, 1 sent version with a non-empty recommended option label, activity newest-first |
| AC5 | Met | `backend/app/features/clients/tests/test_latency.py` — list (250 clients, 4 filter/sort combos) and detail (1 client, 15 applications, 150 activity events, 15 sent versions) each asserted < 300 ms; also observed in the e2e run (list/detail pages render well under a second against the demo-reset seed) |
| AC6 | Met | `e2e/lo-console/clients-list.spec.ts` (4/4 passed against a live API + LO console, slot 20): filter bar renders, search updates the URL and survives reload + back-navigation, Clear filters resets to a bare `/clients`, row click opens `/clients/{id}` with all three sections visible |
| AC7 | Met | `npx react-doctor -y --blocking error` in `apps/lo-console`: exit 0, score 81/100, 6 pre-existing warnings (none introduced by this item — see Test log) |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (clients) | `uv run pytest backend/app/features/clients -q` | 18 passed |
| Backend tests (full) | `uv run pytest backend -q` | 835 passed |
| Backend lint | `uv run ruff check backend` | All checks passed |
| Backend types | `uv run mypy backend` | Success: no issues found in 478 source files |
| Frontend types | `pnpm --filter @cq/lo-console run typecheck` | 0 errors |
| Frontend lint | `pnpm --filter @cq/lo-console run lint` | 0 errors |
| Frontend tests | `pnpm --filter @cq/lo-console run test` | 219 passed (49 files), including 8 new clients-feature test files |
| react-doctor | `npx react-doctor -y --blocking error` (in `apps/lo-console`) | Exit 0. 6 warnings, all pre-existing/out of owned files: `ActivityTimeline.tsx:75` (`formatTime`, unchanged by this item's edit — only line numbers shifted), `IntegrationsPanel.tsx`, `SettingsPanel.tsx`, `ApplicationsFilterBar.tsx`, `DefaultTabRedirect.tsx`, `WorkspaceProvider.tsx` |
| e2e (this item) | `pnpm exec playwright test e2e/lo-console/clients-list.spec.ts` (slot 20, live API+LO console) | 4 passed |
| e2e (regression) | `pnpm exec playwright test e2e/lo-console/shell.spec.ts` (slot 20) | 4 passed (confirms the Clients stub-row removal didn't break the shell spec) |

## Review findings (stage 6)

`code-review` skill run at low effort over the full diff (a fresh forked review, `@code-review`).

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `service.py`'s `_application_rows` used the *client's* assigned-LO name for every application row's `lo_name`, instead of each application's own `lo_id`. Visible for a client whose applications belong to different LOs. | Fixed: batch-looks-up each distinct `lo_id` among the client's applications. Added a regression assertion in `test_client_detail_scoping_needs_active_application` checking each row's `lo_name` independently. |
| Major | `report_link` was a bare relative `/report/{token}` path; the LO console and borrower portal are separate origins, so the "Preview" link 404s outside a same-origin dev setup. | Fixed: builds the full URL from `core.config.settings.portal_base_url`, the same setting `applications/sections/credit.py` already uses for its own borrower-portal link. `test_client_detail_marcus_hale` updated accordingly. |
| Minor | `ClientsTable`'s `aria-sort` derived direction from the globally active `sort` string (copied from `ApplicationsTable`'s toggle-column pattern), mislabeling the always-ascending `name` column as "descending" whenever it was active. | Fixed: direction is now derived from each column's own fixed `sortValue` (every CQ-026 sort token has exactly one direction, spec.md). Added a regression test. |
| Reviewed, no change | `get_client_detail`'s `lo = await db.get(User, client.assigned_lo_id); lo_name = ... "Unknown"` fallback implies `assigned_lo_id` could be null, while `_base_query()`'s inner join would then silently drop that client from `list_clients`. | `Client.assigned_lo_id` is `Mapped[uuid.UUID]` (not `| None`) in `clients/models.py` -- not nullable at the schema or DB level, so this case cannot occur; the fallback is defensive-only and left as-is. |

All findings addressed before commit; verified with a second `uv run pytest backend/app/features/clients -q` (18 passed), `uv run ruff check` / `uv run mypy` (clean), and `pnpm --filter @cq/lo-console run test` (219 passed) after the fixes.

## Review round 1 (post-merge fix pass, PR #29)

A fresh review of the merged PR (not the stage-6 review above, which ran before merge) found one critical and one major backend issue plus a batching cleanup. Fixed on `cq-026-fix`, branch pushed back onto this PR.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Cross-LO data leak: `get_client_detail` checked that the requesting LO owned *at least one* of the client's applications, then returned **every** application on the client (and, derived from that unscoped list, every sent version and the merged activity across all of them) — including other LOs' — contradicting `core/auth.py::scope_applications`'s "an LO only ever sees their own applications". | `_application_rows_for_client(db, client_id, user)` now runs through `scope_applications`, the same helper every other application-scoped route uses. The gate simplified: an LO with zero in-scope applications for the client 404s (no separate existence check needed). Manager/Admin unaffected. `test_client_detail_scoping_needs_active_application` rewritten to assert the LO sees only their own application, not the other LO's; `test_client_detail_manager_sees_every_lo_application` added for the Manager side (plan.md Decision 14). **Correction (review round 2):** neither test yet asserted `sent_versions`/`activity` were scoped too at this point, even though the fix above scopes them the same way (they derive from the same result) — see the round 2 table below. |
| Major | LIKE wildcards not escaped in `q` (`clients/service.py`'s client search, and the same bug in `applications/listing/service.py`'s CQ-027 search) — a literal `%`/`_` acted as a SQL wildcard instead of matching literally, same class of bug the outbox's own `q` had before its earlier code-review fix. | Moved `notifications/outbox/service.py`'s `_escape_like`/`_LIKE_ESCAPE` into a new `backend/app/core/sql.py` (`escape_like`/`LIKE_ESCAPE_CHAR`) and reused it in the outbox, clients and applications-listing searches. Tests: `test_client_search_escapes_like_wildcards` (`foo_bar` vs. `fooXbar`, and a bare `%`), `test_q_filter_escapes_like_wildcards` (applications listing, same two cases, plan.md Decision 17). |
| Decision (list aggregates) | `application_count`/`active_status`/`last_activity` on `GET /clients` were computed over a client's *entire* application set regardless of who asked, which could reveal another LO's application count/status on a shared client even without opening the detail page. | Scoped to the requesting LO's own applications when `user.role == LO` (`_application_scope_clauses(lo_scope)`); unscoped for Manager/Admin, including when they filter by `lo_id` (that filter narrows which clients appear, not what a Manager who can already see everything is told about them). Tests: `test_client_list_aggregates_scoped_to_lo_own_applications`, `test_client_list_aggregates_unscoped_for_manager` (plan.md Decision 15). **Correction (review round 2):** `has_active` was left unscoped at this point, reasoned as out of scope for "the three named aggregates" — that reasoning was wrong; see finding 1 in the round 2 table below. |
| Minor | `_merged_activity` called the single-application `list_activity` once per application on the client (each call re-fetching the client row, each over-fetching per application before a Python re-sort/truncate to 50). | Added a batched `applications.timeline.service.list_activity_for_applications(db, applications, limit=50)`: one query across every application's events (`ORDER BY at DESC, id DESC LIMIT 50`) plus one staff-name lookup, sharing a new `_events_to_out` helper with `list_activity`. `get_client_detail` now calls it directly (plan.md Decision 16). |

Verification after the fixes: `uv run pytest backend -q` (840 passed), `uv run pytest seed -q` (32 passed), `uv run ruff check backend` / `uv run ruff format --check backend` / `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (all clean), `pnpm -r run lint` / `pnpm -r run typecheck` / `pnpm exec prettier --check .` (all clean), `pnpm -r run test` (541 frontend tests passed across `@cq/ui`, `@cq/api-client`, `apps/lo-console`, `apps/borrower-portal`, plus 1 pre-existing skip), and a second `code-review` skill pass (low effort) over the fix diff, which reported no new findings. `e2e/lo-console/clients-list.spec.ts` (4/4) and `e2e/lo-console/shell.spec.ts` (4/4) passed against a live API + LO console + portal (slot 20, after `make demo-reset` and an API restart).

## Review round 2 (second post-merge fix pass, PR #29)

A second review of the round-1 fix found one major issue it missed and three minors, all in the same area (LO scoping and the new batched activity helper). Fixed on the same `cq-026-fix` branch.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `_client_active_exists` (the `has_active` filter) was still unscoped for an LO, even though round 1 scoped the other three list-level aggregates. Scenario: LO A has a closed application on a shared client, LO B has a priced one — `has_active=true` would show the client to LO A (leaking that *someone's* application is active) and `has_active=false` would hide it (when, from LO A's own point of view, their own application isn't active, so it should show). | `_client_active_exists(lo_scope)` now takes the same `lo_scope` `_base_query` already threads through `_application_scope_clauses`. Tests: `test_client_has_active_filter_scoped_to_lo_own_applications` (both `true` and `false` in the exact leak scenario), `test_client_has_active_filter_unscoped_for_manager` (plan.md Decision 15, amended). |
| Minor | `test_client_detail_scoping_needs_active_application`/`test_client_detail_manager_sees_every_lo_application` only asserted on `applications`, not `sent_versions`/`activity`, even though decision #14's fix scopes all three (they derive from the same application list). | Both tests now add a sent `QuotePackageVersion` and an `ActivityEvent` to each of the shared client's two applications and assert the LO's response contains only their own version/event ids (Manager: both) — both passed immediately, confirming round 1's fix already covered `sent_versions`/`activity` correctly; only the test coverage was missing (plan.md Decision 18). |
| Minor | `test_client_list_aggregates_scoped_to_lo_own_applications` didn't cover `last_activity` itself (only `application_count`/`active_status`), despite `last_activity` being one of the three aggregates the decision names. | Gave the other LO's application a newer event than the requesting LO's own. Added assertions that the client row's `last_activity` equals the LO's own (older) event, not the other LO's newer one, and that `-last_activity` ordering reflects that scoped value too (a second, wholly-owned client's own activity sorts ahead of the shared client under the scoped value, but would sort behind it under the unscoped one). Passed immediately — confirming round 1's `last_activity` scoping was already correct, only the test coverage was missing. |
| Minor | `list_activity_for_applications` inferred `client` from `applications[0].client_id` and documented an unchecked assumption ("all `applications` are assumed to share one client") instead of enforcing it. | `list_activity_for_applications(db, client, applications, limit=50)` now takes `client` explicitly (the only caller, `get_client_detail`, already has it) and asserts every application belongs to it, failing loudly on a caller bug instead of silently mislabeling the borrower name or merging out-of-scope events. New direct unit tests in `backend/app/features/applications/timeline/tests/test_service.py` (new file): merge order across two applications, `limit`, empty input, and the assertion firing when an application from a different client is passed. |

Verification after the round-2 fixes: `uv run pytest backend -q` (846 passed, +6 from round 2: 2 `has_active` scoping, 4 `list_activity_for_applications` unit tests), `uv run pytest seed -q` (32 passed), `uv run ruff check backend` / `uv run ruff format --check backend` / `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (all clean), `make lint` and `make test` both green end-to-end, and `e2e/lo-console/clients-list.spec.ts` + `e2e/lo-console/shell.spec.ts` (8/8) against a live API + LO console + portal (slot 20, after a fresh `make demo-reset` and API restart).

## How to test manually

1. `bash scripts/worktree-env.sh 20`, `uv run python -m seed.reset`.
2. Start the API (`uv run uvicorn app.main:app --app-dir backend --port 8120`), LO console (`pnpm --filter @cq/lo-console exec next dev -p 3120`) and borrower portal (`pnpm --filter @cq/borrower-portal exec next dev -p 3220`, needed by Playwright's global setup even for lo-console-only specs).
3. Sign in as `casey.nguyen@clearquote-demo.test` (Manager) at `http://localhost:3120`, open **Clients**, search "hale", open Marcus Hale's detail page.
4. Sign in as an LO (`jordan.lee@clearquote-demo.test`) and confirm the client list only shows clients with an application of theirs, and the LO filter is hidden.
5. To exercise the review round 1/2 fixes directly: as Manager, create (or find in the seed) two applications on the same client assigned to two different LOs, each with a sent version and an activity event; sign in as one of those LOs and open that client's detail page — only that LO's own application, sent version and activity event should appear, and the list's `application_count`/`active_status`/`last_activity`/`has_active` for that client should all reflect only that LO's application.

## Follow-ups

- No LO-authenticated report-preview route exists yet for the "Quotes sent" report links (plan.md Decision 11) — a future item could add one instead of linking to the borrower-only `/report/{token}` route.
- `active application status`/`application_count` semantics (plan.md Decisions 2–3, refined for LO scoping by Decision 15) are this item's own reasonable reading of the spec's brief wording; flag if product wants a different definition (e.g. active-only application counts).
