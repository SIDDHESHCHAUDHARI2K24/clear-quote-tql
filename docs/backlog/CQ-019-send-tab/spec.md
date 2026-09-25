# CQ-019 Send tab & preview

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-018, CQ-021 |
| Kaneo task | CQ-019 in Kaneo (task id `cl3sboh5ibwsb0jdgapvc4um`) |
| Branch | `cq-019-send-tab` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The LO picks which quotes go to the borrower, confirms the recommendation, and sees exactly what the borrower will see, both the portal report and the pre-approval letter, before sending. If the automation did its job, this is the only tab the LO needs to open.

## Scope

**Backend (owned by this item)**

- Quote package draft: `PUT /api/applications/{id}/package` with `{quote_ids[], recommended_quote_id, lo_note}` creates or updates the single draft package; `GET` returns it. Default draft (created on first `GET`): the recommended quote (else the par quote of the first group) plus up to 2 alternatives, in group order.
- Recommendation text: the draft includes `recommendation_text`, pre-drafted from the scenario, e.g. "20% down · Par pricing at 7.500%, no prepay. It balances your monthly payment and cash needed at closing." The LO's note is stored separately and shown under it.
- `GET /api/packages/{id}/report` returns the `ReportViewModel` (schema and builder from CQ-021) for the draft. This is the same payload the borrower portal will get (CQ-022).
- Letter template: a Jinja2 HTML template `backend/app/features/quotes/pdf/templates/preapproval_letter.html` with the variables in catalog §10 (par quote only, TBD or address variant, LLC entity when vesting in an LLC, assigned LO signature, document checklist generated from the documents table, portal link placeholder). `GET /api/packages/{id}/letter.html` renders it. CQ-020 turns the same template into a PDF.
- Send readiness: `GET /api/packages/{id}/readiness` → `{ready: bool, blockers: [{code, message, tab}]}`. Blockers: any selected quote stale; any open flag with severity `error`; no recommended quote; borrower email missing.

**Frontend (Send tab)**

- Left column: quote checklist (selected quotes, drag to reorder, recommended radio), recommendation text (read-only) and the LO note (textarea, 500 characters), readiness list with links to the blocking tabs.
- Right column: preview with two tabs, **Borrower report** (renders `ReportViewModel` with the CQ-021 components) and **Pre-approval letter** (renders `letter.html` in a sandboxed iframe at page width).
- Send button: disabled with the first blocker as a tooltip when not ready; when ready, opens a confirm dialog showing recipient email and attachments, then calls the send endpoint from CQ-020. Until CQ-020 lands, the confirm dialog's action is a stub that says "Sending arrives in CQ-020".

## Out of scope

- PDF generation, storage, email and the report link (CQ-020).
- Borrower-side page (CQ-022).

## References

- `docs/design/system-design.md` — LO Console → Send (tab 7), Borrower Portal → Quote report, Decisions 3–5.
- `docs/design/data-field-catalog.md` — §10 pre-approval letter template variables, §3 `credit_score_bracket`, `verified_assets_display`.
- Reference screens: `02-preapproval-letter-current.png`, `03-preapproval-letter-target.png`, `04-report-summary.png`.

## Acceptance criteria

- [ ] AC1 — Opening Send for Marcus Hale shows a default draft with the recommended quote first and at most 2 alternatives; the recommendation text names the down payment, pricing type and rate of the recommended quote.
- [ ] AC2 — The Borrower report preview renders from `GET /api/packages/{id}/report`, and its JSON is byte-identical to what CQ-022's portal endpoint returns for the same package once CQ-022 exists (a contract test compares the two builders now).
- [ ] AC3 — The letter preview for Kathleen McReynolds (TBD property) shows "- TBD -" as the property, the par quote's terms only, "780+"-style FICO bracket, "Verified Assets $135K+"-style asset line, and the assigned LO's name, title, NMLS and contact.
- [ ] AC4 — The letter for Asheville Holdings LLC shows the LLC as the buyer; the letter for a specific-address persona shows the full address.
- [ ] AC5 — Grace Kim's package is not ready: blocker "Quotes are out of date" links to Pricing; Aisha Coleman's blocker names her open flag. The Send button is disabled for both.
- [ ] AC6 — Removing a quote, changing the recommended radio or editing the note persists after reload.
- [ ] AC7 — react-doctor passes; the preview iframe cannot run scripts (sandbox attribute set).

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | API test | `test_default_package_draft` |
| AC2 | Contract test | `test_report_view_model_same_for_lo_and_portal` |
| AC3, AC4 | Template render tests with persona data | `test_letter_tbd_variant`, `test_letter_llc_and_address_variants` |
| AC5 | API test | `test_readiness_blockers[grace_kim, aisha_coleman]` |
| AC6 | Playwright | `e2e/send-tab-draft.spec.ts` |
| AC7 | react-doctor + DOM assertion | evidence in post-dev.md |

## Notes for the agent

- Wave 1: package endpoints, readiness and api-client; wave 2: letter template; wave 3: UI.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
