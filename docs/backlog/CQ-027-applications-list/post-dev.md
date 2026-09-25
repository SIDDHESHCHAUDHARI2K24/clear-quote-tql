# CQ-027 — Post-development notes

## Summary

`GET /api/v1/applications` (`backend/app/features/applications/listing/`) is
a scoped, filtered, sorted, paginated list over `core/pagination.Page`,
covering every spec.md parameter including the `sent_or_later` alias
(exposed as `build_sent_or_later_filter()` for CQ-025 to reuse verbatim,
AC3/E10) and the comma-separated lists. A small in-scope addition,
`GET /applications/los`, backs the Manager/Admin-only LO filter (nothing
else in the backend exposed a role=lo user list). One migration adds three
indexes (`updated_at`, `created_at`, `requested_price`) for the filter/sort
columns that weren't already indexed. The frontend fills the `(staff)/
applications` stub: a filter bar (search, status multi-select, strategy
chips, amount range, state select, has-property toggle, date range, LO
select), a sortable table built from the shared `ApplicationRow` (E9,
exported cleanly from `src/features/applications/index.ts` for CQ-026),
`Pagination`, and a row click into `/applications/[id]`. Every filter lives
in the URL via `useApplicationFilters`, including the exact parameter forms
CQ-025's dashboard tile links use.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET /api/applications` | `GET /api/v1/applications` | AGENTS.md/plan.md: every spec `/api/...` path is `/api/v1/...` under `core/registry.py`. |
| `strategy` filter list: `primary`, `ltr`, `str` | `strategy=primary` ⇔ `applications.strategy IS NULL`, not `occupancy = 'primary'` | Aisha Coleman's `occupancy` is `NULL` (her missing-field flag) while her `strategy` is `ltr` -- an occupancy-based rule would put her under neither `primary` nor `ltr`. `core/enums.py`'s own `Strategy` docstring says `strategy` is null exactly when the loan is Primary, so the filter and the row's displayed `strategy` both use that one field (plan.md Decision #4). |
| `state`: "Subject state ... TBD properties match on buy-box states" | Computed by joining `properties` directly (`properties.state` / `ANY(properties.buy_box_states)`), not `applications.subject_state` | `applications.subject_state` exists on the model (a P5/P6-foundation denorm column) but nothing in the codebase populates it; wiring that up would mean editing `property/service.py` and pipeline activities, outside this item's owned files (plan.md Decision #2). |
| — (not in spec's table) | Added `GET /applications/los` | The spec's own "Frontend" scope requires an "LO Select for Manager/Admin" filter, and nothing else in the backend lists `role=lo` users. Small, logged addition inside owned files. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 -- each filter alone + 3 combined match equivalent SQL | ✅ | `backend/app/features/applications/listing/tests/test_router.py`: `test_status_filter_matches_expected_rows`, `test_strategy_filter_matches_expected_rows`, `test_amount_range_filter`, `test_state_filter_matches_specific_and_tbd_buy_box`, `test_has_property_filter`, `test_created_date_range_filter`, `test_q_filter_matches_name_and_email`, `test_combined_filters` (status+strategy+state), `test_pascal_case_comma_list_status`; each computes its expected id set directly from the fixture's own Python attributes, independent of the query under test. Cross-checked against the real seeded DB (slot 13, `make demo-reset`) via curl for `q=aisha`, `q=kathleen`, `q=grace`, `status=sent_or_later`, combined filters -- see "How to test manually". |
| AC2 -- Aisha (NeedsAttention, flag_count ≥ 1), Grace (Stale), Kathleen (TBD, `has_property=false`) | ✅ (Grace: fixture-verified, pending real demo-reset re-check) | `test_router.py::test_needs_attention_and_tbd_personas` (Aisha, Kathleen); `test_status_stale_includes_a_fixture_set_stale`. Live curl against slot 13's real seed confirmed Aisha (`flag_count: 1`) and Kathleen (`property_label: "TBD · Davenport, Orlando"`). Grace: `make demo-reset` seeds her `status=sent`, not `stale` -- CQ-030 (a wave-2 sibling, not yet merged) is what actually runs the stale job; nothing in today's seed/reset path calls it (plan.md Decision #10). The `status=Stale` *filter itself* is verified with a fixture set to `stale` directly (`test_status_stale_includes_a_fixture_set_stale`) and, separately, `test_sent_or_later_matches_dashboard_definition` pins the Stale-after-a-send vs Stale-from-Priced distinction. **Pending -- re-check Grace via `make demo-reset` + `status=Stale` after CQ-030 merges.** |
| AC3 -- `sent_or_later` matches the dashboard's "Pre-approvals sent" tile | ✅ definition; pending cross-check | `listing/tests/test_service.py::test_sent_or_later_matches_dashboard_definition` pins the exact spec.md definition against a SQL-equivalent fixture (Sent/Viewed/Inquiry/OptionSelected always count; Stale counts only when a `quote_package_versions` row exists, i.e. it was actually sent; Stale-from-Priced-never-sent does not count). `build_sent_or_later_filter()` is exported from `listing/service.py` for CQ-025 to import verbatim. **E2E_NOTE: pending -- re-check against the real CQ-025 `/api/v1/dashboard` endpoint once merged** (built in parallel). |
| AC4 -- an LO passing another LO's `lo_id` still gets only their own rows | ✅ | `test_router.py::test_lo_scoping_ignores_other_lo_id`. Live curl (slot 13): `jordan.lee` (LO) got `total: 105` both with no `lo_id` and with `lo_id=<morgan.reyes's id>`. |
| AC5 -- under 300 ms for any filter combination | ✅ | `listing/tests/test_latency.py::test_application_list_latency` (250 synthetic applications, 6 filter combos, each asserted < 300 ms). Live curl against slot 13's real seed (~410 applications: 10 personas + 200 background + prior sibling test data): no filters 13 ms, `status=Priced,Inquiry,OptionSelected&strategy=ltr&state=FL` 19 ms, `amount_min/amount_max&has_property=true&sort=amount&page_size=100` 16 ms. Migration `f1a2b3c4d5e6` adds `ix_applications_{updated_at,created_at,requested_price}`. |
| AC6 -- filters survive reload/back nav; Clear filters resets the URL | ✅ | `e2e/lo-console/applications-list.spec.ts` (Playwright, slot 13, live servers): all 5 tests pass -- filter bar/table/pagination render; a status filter round-trips through reload and `goBack()`; Clear filters resets to a bare `/applications`; a dashboard-style tile link (`?status=NeedsAttention`) is accepted; a row click opens `/applications/{id}`. Also `apps/lo-console/src/features/applications/useApplicationFilters.test.ts` (Vitest, URL parse/push logic) and `filters.test.ts` (round-trip + CQ-025's exact link forms). |
| AC7 -- react-doctor passes | ✅ | `npx react-doctor -y --blocking error` on `apps/lo-console`: score 86/100, **0 errors**; 2 pre-existing warnings, both in unrelated `features/workspace/*` files (not touched by this item). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | 519 passed |
| Seed tests | `uv run pytest seed` | 32 passed |
| Lint / types (backend) | `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | clean |
| Frontend | `pnpm -r run test` | api-client 2, ui 163, lo-console 90 (+36 new), borrower-portal 95 -- all passed |
| Frontend lint/types | `pnpm -r run lint && pnpm -r run typecheck && pnpm exec prettier --check .` | clean |
| react-doctor | `npx react-doctor -y --blocking error` (lo-console) | 86/100, 0 errors |
| Migration | `alembic upgrade head` + `alembic check` | "No new upgrade operations detected"; `alembic heads` -> `f1a2b3c4d5e6 (head)` (single head) |
| `make demo-reset` | `uv run python -m seed.reset` (slot 13) | 2.6 s |
| `make lint` | full repo | clean |
| `make test` | full repo | backend 519, seed 32, frontend 350 -- all passed |
| e2e | `pnpm exec playwright test e2e/lo-console/applications-list.spec.ts --workers=1` (slot 13) | 5 passed |
| e2e (shared spec regression check) | `pnpm exec playwright test e2e/lo-console/shell.spec.ts --workers=1` (slot 13) | 4 passed (confirms the small `shell.spec.ts` edit, see below, didn't break it) |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| -- | `code-review` (medium effort) against the full diff: route ordering, pagination/scoping helpers, status/sort token mapping between frontend and backend, migration revision chain, and the money-formatting rule all checked and found correct | No findings -- clean run, `[]` |

## How to test manually

1. `source scripts/worktree-env.sh 13 && make demo-reset`
2. Start the API (`uv run uvicorn app.main:app --port 8113` from the repo root) and the LO console (`pnpm --filter @cq/lo-console exec next dev -p 3113`).
3. Sign in at `http://localhost:3113/login` as `casey.nguyen@clearquote-demo.test` (Manager, password `SEED_STAFF_PASSWORD`) via the OTP flow (code from Mailpit `http://localhost:8025`).
4. `/applications`: search "aisha" -> Aisha Coleman, flag badge "1"; search "kathleen" -> property label "TBD · Davenport, Orlando"; `?status=sent_or_later` -> Grace Kim (status Sent) plus every Sent/Viewed/Inquiry/OptionSelected row; select a Status + Strategy + State combo, reload the page, use browser Back, click Clear filters.
5. Sign in as `jordan.lee@clearquote-demo.test` (LO): no LO select in the filter bar; `?lo_id=<morgan.reyes's id>` still returns only Jordan's own applications.

## Follow-ups

- AC2 (Grace Kim) and the `sent_or_later` cross-check (AC3) are marked pending above -- re-verify once CQ-030 (stale job) and CQ-025 (dashboard) merge into `phase-p5-p6`, per the orchestrator's phase-verification step.
- `applications.subject_state` (P5/P6 foundation column) is still unpopulated; this item's `state` filter joins `properties` directly instead (Decision #2). A later item could populate it and switch the filter to the indexed column if profiling ever shows the join is a bottleneck at full seed scale -- not needed today (AC5 measured 13-19 ms).
