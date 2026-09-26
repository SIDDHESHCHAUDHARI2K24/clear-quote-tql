# CQ-029 Timeline, Outbox, Integration panel

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016, CQ-009 |
| Kaneo task | CQ-029 in Kaneo (task id `j8prs6rvebstcxromc0hu8rv`) |
| Branch | `cq-029-timeline-outbox-panel` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

Four supporting screens that make the automation visible and the demo reliable: a timeline of everything that happened to an application, an outbox of every email sent, an admin panel to watch (and deliberately break) the mock integrations, and a read-only view of the pricing settings.

## Scope

**Timeline**

- `GET /api/applications/{id}/activity?page=` → events newest first (actor: system, LO name or borrower; type; human-readable message; payload summary; time).
- `ActivityTimeline` component in `apps/lo-console/src/features/activity/`: grouped by day, icon per event type (import, flag, pricing, override, send, view, borrower action, email, consent), "system" events visually quieter than people's actions.
- Shown as a right-hand drawer in the application workspace ("Activity" button in the header) and on the client detail page (CQ-026 swaps its simple list for this component).

**Outbox**

- `GET /api/outbox?q=&type=&application_id=&page=` → emails (to, subject, type, application, status, sent at); `GET /api/outbox/{id}` → HTML body and attachment list; `GET /api/outbox/{id}/attachments/{key}` streams the file (LO must have access to the application).
- `/outbox` page: table with search and type filter; detail view renders the HTML in a sandboxed iframe with attachment downloads. Linked from CQ-020's "Open in Outbox".

**Integration panel (Admin only)**

- `GET /api/admin/integrations` → for each of the 9 adapters: name, provider it emulates, last call time, last latency, last result (ok / error code), calls in the last hour, and `force_failure` state.
- `PUT /api/admin/integrations/{adapter}` with `{force_failure: bool}` toggles the CQ-009 failure switch (reuse it; if CQ-009 exposes it differently, adapt and log a `Decision:`).
- `POST /api/admin/jobs/stale-check` runs the CQ-030 stale job now (button hidden until CQ-030 exists).
- `/admin/integrations` page with a status row per adapter and the toggle; a banner warns while any failure is forced.

**Settings (Admin, read-only)**

- `GET /api/admin/settings` → fee constants, default down payments, insurance rate, STR expense ratio, land and accelerated percentages, bonus depreciation, marginal tax rate, reserves months, stale days.
- `/admin/settings` page listing them with their source (seed/config). No editing in this prototype.

## Out of scope

- Editing settings, resending emails, CRM sync UI.

## References

- `docs/design/system-design.md` — Emulated integrations (Demo controls), LO Console → Outbox, Data model (`activity_events`, `outbox_emails`, `settings`).
- Built code to check in stage 1: CQ-009 adapters and failure toggles, event types written by CQ-011, CQ-017–CQ-024.

## Acceptance criteria

- [ ] AC1 — Marcus Hale's timeline shows, in order, import, verification, enrichment, pricing, send, view and any borrower action, each with a readable message; system events are visually distinct.
- [ ] AC2 — The outbox lists every email in `outbox_emails` after a demo reset plus one send; opening Marcus Hale's quote email shows the HTML and downloads the PDF.
- [ ] AC3 — An LO cannot open an outbox email or attachment for another LO's application (403).
- [ ] AC4 — As Admin, forcing `PricingClient` to fail and re-pricing any application moves it to Needs Attention with the named error; turning the toggle off and re-pricing succeeds (live demo path).
- [ ] AC5 — The integration panel shows last latency and result for each adapter after a pipeline run; non-admins get 403 and no menu entry.
- [ ] AC6 — The settings page values equal the config snapshot stored on a newly created scenario.
- [ ] AC7 — react-doctor passes; the email iframe runs no scripts.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | API test + component test | `test_activity_order_marcus_hale`, `ActivityTimeline.test.tsx` |
| AC2, AC3 | API tests | `test_outbox_list_and_detail`, `test_outbox_access` |
| AC4 | Integration test + Playwright | `test_forced_pricing_failure_path`, `e2e/integration-panel.spec.ts` |
| AC5 | API test by role | `test_integrations_admin_only` |
| AC6 | API test | `test_settings_match_snapshot` |
| AC7 | react-doctor + DOM assertion | evidence in post-dev.md |

## Notes for the agent

- The four screens are independent after wave 1 (endpoints + api-client); run them as parallel subagents.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
