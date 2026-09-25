# CQ-016 Application workspace shell

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-014, CQ-011 |
| Kaneo task | CQ-016 in Kaneo (task id `ns44zsvwb9gtn4vyyi2om3h0`) |
| Branch | `cq-016-application-workspace` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

An LO opens any application and immediately sees where it stands: the key numbers, the pipeline status, and which of the seven tabs need attention. Every other LO screen in P3 and P5 lives inside this shell, so it sets the look of the demo.

## Scope

**Backend (owned by this item)**

- `GET /api/applications/{id}/summary` returns the header data: client name, program, occupancy/strategy, location (city, state, zip), purchasing power, down payment (% and $), PPP (investment only), note rate (null until a quote is marked recommended), status, `last_pipeline_stage`, and per-tab `{tab, state: ok|flagged|pending, flag_count}` for the 7 tabs.
- `PATCH /api/applications/{id}/status` accepts only `Withdrawn` or `Closed` (with an optional reason) from any non-terminal status; any other value returns 422. The change writes an activity event.
- Access: LO sees only assigned applications (403 otherwise); Manager and Admin see all (from CQ-014).

**Frontend (`apps/lo-console`)**

- Route `/applications/[id]` with a nested route per tab: `borrowers`, `housing`, `credit`, `assets`, `property`, `pricing`, `send`. The default tab is the first flagged tab, else `pricing` when status ≥ Priced, else `borrowers`.
- Sticky header: client name, status pill, and header numbers in this order: purchasing power · down payment (% and $) · PPP · note rate · strategy · program · location. PPP is hidden for primary loans. When the note rate is null it shows "—" in a muted style with the tooltip "Set after pricing".
- Tab rail: tab label + a green check (ok), a red count badge (flagged) or a grey dot (pending). Tabs 1–5 render a placeholder panel "Built in CQ-028"; tabs 6 and 7 render the placeholders for CQ-017 to CQ-019.
- Header actions menu: "Withdraw application" and "Close application" (confirm dialog + reason field). Both hidden when the status is already terminal.
- A "Pipeline running" banner with the current stage name while the Temporal workflow is active (poll the summary every 3 s while `last_pipeline_stage` is not terminal; stop when it is).
- Loading skeleton, 404 page and 403 page.

## Out of scope

- Tab content (CQ-017 to CQ-019, CQ-028).
- Dashboard and lists that link here (CQ-025 to CQ-027).
- Live push updates; polling is enough.

## References

- `docs/design/system-design.md` — Hero numbers (LO console header set), Application status machine, LO Console → Application workspace.
- `docs/design/data-field-catalog.md` — §5 loan structure (`down_payment_pct`, `prepayment_penalty_term`, `loan_program_name`, `occupancy_type`, `investment_strategy`).
- Status enum and transitions: CQ-007 model, CQ-011 pipeline.

## Acceptance criteria

- [ ] AC1 — For each of the 10 personas, every header number equals the value derived from the engine and the persona's current scenario (compared in an API test that computes the expected values with `quote_engine`).
- [ ] AC2 — Priya Nair (primary) shows no PPP field; Marcus Hale (STR) shows "5y PPP" or the persona's PPP.
- [ ] AC3 — The note rate shows "—" for an application with no recommended quote and the recommended quote's rate otherwise (e.g. 7.500% for Marcus Hale after CQ-018 marks par as recommended).
- [ ] AC4 — Aisha Coleman (missing occupancy) opens on her first flagged tab, which shows a red badge with count ≥ 1; Ben Ford's Housing tab shows a red badge; Priya Nair opens on Pricing.
- [ ] AC5 — An LO requesting another LO's application gets 403 from the API and the 403 page in the UI; a Manager can open it.
- [ ] AC6 — Withdrawing an application sets status Withdrawn, writes an activity event with the reason, and hides the actions menu; `PATCH …/status` with `Priced` returns 422.
- [ ] AC7 — While the pipeline runs (trigger by re-importing a persona), the banner shows the stage name and disappears when the workflow ends.
- [ ] AC8 — react-doctor passes; the header stays visible while scrolling a long tab at 1280 px and 1440 px widths.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | API test, parametrized over personas | `test_summary_matches_engine[persona]` |
| AC2, AC3 | Component test on the header | `ApplicationHeader.test.tsx` |
| AC4 | API test + component test | `test_tab_states_flags`, `TabRail.test.tsx` |
| AC5 | API test | `test_summary_access_by_role` |
| AC6 | API test | `test_status_patch_terminal_only` |
| AC7 | Integration test with the Temporal test server | `test_summary_reports_running_stage` |
| AC8 | react-doctor + manual screenshot at 2 widths | evidence in post-dev.md |

## Notes for the agent

- Wave 1 is the summary endpoint and the regenerated api-client; the UI follows.
- The default-tab rule is generic (first flagged tab, else Pricing when priced, else Borrowers); do not special-case personas.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
