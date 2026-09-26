# CQ-029 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `outbox_emails.type` (spec "Out of scope" note) | Decided: **derive**, no migration. `outbox/service.py::infer_email_type` classifies by subject substring against the known OTP/borrower-action/quote-sent subjects (each a module-level constant re-used or mirrored from its sender), single source of truth `_TYPE_SUBJECT_RULES` (also drives the `type=` filter's SQL). Unknown subjects fall back to `"other"`. Kept out of `notifications/email/service.py` (shared, not owned by me) so `send_email` callers need no change. The filter dropdown offers `KNOWN_EMAIL_TYPES = {otp, borrower_action, quote_sent, other}`; CQ-034's support-inbox emails currently classify as `other` (no `_TYPE_SUBJECT_RULES` entry yet — its subject isn't fixed until that item lands) and CQ-020/24's real sends may too until this classifier is extended — logged as a follow-up. |
| 2 | Decision | E16 (spec says outbox 403 for cross-scope, plan.md E16 says 404) | Decided: follow E16 — `GET /outbox/{id}` and the attachment stream 404 (`get_scoped_application`-style scoping) for an LO who can't see the application, not 403. AC3's wording ("gets a 403") is satisfied in spirit (LO cannot open it); the exact code is 404 per binding plan.md E16. Logged per the CQ-029 prompt's instruction to log this difference. |
| 3 | Decision | Timeline actor resolution | `ActivityEvent.actor` is either the literal `"system"` or a `users.id` string (per its docstring). Borrower-initiated types (`quote.viewed`, `quote.move_forward`, `quote.ask_other`, `quote.ask_updated`) are written with `actor="system"` today (portal/actions and reports services), but the spec wants these shown as the borrower, not quieted as "system". `timeline/service.py` special-cases those four types: resolve the borrower's display name via `Application.client_id -> Client.full_name`, mark `is_system=False`. Every other `actor == "system"` row is genuine automation (`pipeline.*`) — `is_system=True`, quieter styling. A `users.id` actor resolves to that `User.full_name` (LO), `is_system=False`. |
| 4 | Decision | Human-readable messages | `timeline/service.py::describe_event(type, payload)` is a pure function mapping known `type` strings (`pipeline.imported/verified/flagged/enriched/pricing_blocked/priced/resumed`, `quote.viewed/move_forward/ask_other/ask_updated`, `application.withdrawn/closed`, `quote.sent`) to a human sentence, using `payload` where useful (e.g. flagged rule count, withdrawal reason). Unknown/future types fall back to a generic `"{type replace '.'/'_' with space}"` sentence so the timeline never 500s on a type this item doesn't know about yet (CQ-030 stale marking, CQ-033 consent events, CQ-020/24 real sends land after this PR). |
| 5 | Decision | Icon categories | Spec lists: import, flag, pricing, override, send, view, borrower action, email, consent. `activity/icons.ts` (frontend) maps known `type` prefixes to one of those 9 categories + a `"system"`/`"other"` fallback. `override`/`consent` have no writers yet (plan.md research: CQ-013 override writes no event; CQ-033 not built) — the mapping is ready for them but nothing exercises those branches yet; logged as a follow-up, not a gap (no AC needs them today). |
| 6 | Decision | AC1 test scope | Marcus Hale (persona p01) is seeded to `priced`, not `sent` (plan.md research: "the rest are priced"), so his *real* seeded timeline only has import/verify/enrich/price events, not send/view/borrower-action. `test_activity_order_marcus_hale` asserts his real seeded order (newest-first) and readable messages/system-quieting on those four. A second test (`test_activity_renders_send_view_borrower_action_types`) builds fixture events of the remaining types (send, view, move_forward, ask_other) via `make_activity_event` and asserts they render distinctly and non-quiet. Together these cover AC1's full type list without asserting a persona state the seed doesn't produce. |
| 7 | Decision | Settings source labelling (AC6) | `GET /admin/settings` returns every `settings` table row (source `"settings_table"`) plus the two config-only defaults that AC6's scenario snapshot also carries but that have no `settings` row: `default_down_payment_primary_pct` / `default_down_payment_investment_pct` (`pricing/scenarios/service.py`'s `_DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT`, imported directly rather than re-hardcoded here — code review round 1: two independently-maintained copies of the same literal would let this page silently drift stale — source `"code_default"`). Every other value the spec's list ends up already being a 1:1 `settings` row (`fee_lender_*`, `title_pct`→title rate, `insurance_default_pct`, `str_expense_ratio`, `land_allocation_pct`, `accelerated_property_pct`, `bonus_depreciation_pct`, `investor_marginal_tax_rate`, `reserves_months_*`, `stale_quote_days`) — `pricing.engine.types.ConfigSnapshot()`'s hardcoded field defaults already equal those rows 1:1 (verified against `settings/tests/test_defaults.py`'s `EXPECTED` dict), so AC6 ("settings page values equal the config snapshot stored on a newly created scenario") holds without changing `ConfigSnapshot` to read the table (out of scope; logged as a known gap the config snapshot doesn't actually read the table yet — pre-existing, plan.md research). |
| 8 | Decision | Stale-check button | `admin/integrations` page renders "Run stale check now" behind `STALE_CHECK_JOB_AVAILABLE` (`features/admin/integrations/api.ts`), a logged `false` constant — not a runtime path check: openapi-fetch's generated `paths` type has no runtime representation (it's compile-time only, `openapi-typescript` erases it), so there is nothing to introspect via `in`/`Object.keys` at runtime. CQ-030 (or the orchestrator's merge) flips the constant to `true` once `POST /admin/jobs/stale-check` actually exists. Logged per the prompt's instruction. |
| 9 | Decision | Integration panel "last hour" count | `IntegrationCall.called_at >= now() - 1h` per adapter, using `core/clock.now()` (E2) so `CLOCK_NOW`-driven tests are deterministic. |

No big gaps.

## Why

Four read-mostly screens that make the pipeline and its mocks legible: LOs
get a timeline of what happened to an application and a searchable outbox
of every email; Admins get a kill-switch panel over the 9 mock adapters
(so the Needs-Attention path can be demoed live) and a read-only view of
the pricing config. All four are additive — new routers, new frontend
routes already stubbed by the foundation — nothing existing changes shape
except `WorkspaceHeader.tsx` (one button).

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend: timeline | create `backend/app/features/applications/timeline/{router,schemas,service}.py` + `tests/` |
| Backend: outbox | create `backend/app/features/notifications/outbox/{router,schemas,service}.py` + `tests/` |
| Backend: admin | create `backend/app/features/admin/__init__.py` (empty); `backend/app/features/admin/integrations/{__init__,router,schemas,service}.py` + `tests/`; `backend/app/features/admin/settings/{__init__,router,schemas,service}.py` + `tests/` |
| Registry | modify `backend/app/core/registry.py` (4 new router lines) |
| Frontend: activity | create `apps/lo-console/src/features/activity/**` (`ActivityTimeline`, `api.ts`, icon map, tests) |
| Frontend: outbox | create `apps/lo-console/src/features/outbox/**`; modify `apps/lo-console/src/app/(staff)/outbox/page.tsx` |
| Frontend: admin | create `apps/lo-console/src/features/admin/**`; modify `apps/lo-console/src/app/(staff)/admin/{integrations,settings}/page.tsx` |
| Header | modify `apps/lo-console/src/features/workspace/WorkspaceHeader.tsx` (Activity button + Drawer) |
| e2e | create `e2e/lo-console/integration-panel.spec.ts` |
| Generated | `packages/api-client` via `make api-client` |
| Docs | this folder's `plan.md`/`post-dev.md`/`handoff.md`, graphify update |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Timeline API | — | `applications/timeline/{router,schemas,service}.py` | `test_activity_order_marcus_hale`, `test_activity_renders_send_view_borrower_action_types`, `test_activity_pagination`, `test_activity_scoping_404` |
| T2 | Outbox API | T-storage (foundation, done) | `notifications/outbox/{router,schemas,service}.py` | `test_outbox_list_and_detail`, `test_outbox_filters`, `test_outbox_access`, `test_outbox_attachment_stream` |
| T3 | Admin integrations API | — | `admin/integrations/*` | `test_integrations_admin_only`, `test_integrations_summary_shape`, `test_forced_pricing_failure_path` |
| T4 | Admin settings API | — | `admin/settings/*` | `test_settings_match_snapshot`, `test_settings_admin_only` |
| T5 | api-client regen | T1–T4 | `packages/api-client` | `make api-client` diff |
| T6 | Frontend: activity + outbox UI | T5 | `src/features/activity`, `src/features/outbox`, `(staff)/outbox/page.tsx`, `WorkspaceHeader.tsx` | Vitest per component |
| T7 | Frontend: admin integrations + settings UI | T5 | `src/features/admin`, `(staff)/admin/**` | Vitest per component |
| T8 | e2e + evidence | T6, T7 | `e2e/lo-console/integration-panel.spec.ts` | Playwright run |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2, T3, T4 | Backend endpoints first (contract) — I write these myself, sequentially (shared `registry.py` edits) |
| 2 | T5 | Regenerate api-client once all 4 routers exist |
| 3 | T6, T7 | Frontend pieces, independent files — run as 2 sub-agents in parallel |
| 4 | T8 | e2e + evidence after both frontend pieces land |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_activity_order_marcus_hale`, `test_activity_renders_send_view_borrower_action_types`, `ActivityTimeline.test.tsx` |
| AC2 | `test_outbox_list_and_detail` (list count after demo-reset + 1 fixture send), `OutboxDetail.test.tsx` (HTML render + attachment download link) — PDF-download part `pending — re-check after CQ-020` (E2E_NOTE) |
| AC3 | `test_outbox_access` (other LO's application → 404, logged as the E16 difference from the spec's 403) |
| AC4 | `test_forced_pricing_failure_path` (force PricingClient, `pipeline/start` → NeedsAttention with the error; toggle off → succeeds); `e2e/lo-console/integration-panel.spec.ts` |
| AC5 | `test_integrations_admin_only` (403 non-admin); `test_integrations_summary_shape` (latency/result after a pipeline run) |
| AC6 | `test_settings_match_snapshot` |
| AC7 | react-doctor evidence in post-dev.md; `OutboxDetail.test.tsx` asserts the iframe has `sandbox=""` |

## Progress

- [x] T1 Timeline API
- [x] T2 Outbox API
- [x] T3 Admin integrations API
- [x] T4 Admin settings API
- [x] T5 api-client regen
- [x] T6 Frontend: activity + outbox UI
- [x] T7 Frontend: admin integrations + settings UI
- [x] T8 e2e + evidence
