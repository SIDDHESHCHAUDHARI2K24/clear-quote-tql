# CQ-031 Borrower home & status

| Field | Value |
| --- | --- |
| Phase | P6 Borrower Tier B/C |
| Depends on | CQ-015 |
| Kaneo task | CQ-031 in Kaneo (task id `og87fx1m2qancd3vhtykefny`) |
| Branch | `cq-031-borrower-home` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

After logging in, a borrower sees where their loan stands in plain language and the one thing they should do next. Internal states such as "Needs Attention" never reach the borrower.

## Scope

**Backend (owned by this item)**

- `GET /api/portal/me` (borrower session) → borrower first name, email, and their applications, each with:
  - `stage` mapped from the internal status:

| Internal status | Borrower stage | Label shown |
| --- | --- | --- |
| Intake, Verifying, NeedsAttention, ReadyToPrice | `applied` | "Application received" |
| Priced, Stale (never sent) | `in_review` | "Your loan officer is reviewing your numbers" |
| Sent, Viewed, Inquiry, Stale (after a send) | `preapproved` | "Your pre-approval is ready" |
| OptionSelected | `option_selected` | "You chose an option — {LO first name} will be in touch" |
| Withdrawn, Closed | `closed` | "This application is closed" |

  - `next_action`: one of `view_report` (latest sent version token), `continue_application` (draft from CQ-032), `authorize_credit_check` (pending consent from CQ-033), `none`.
  - Assigned LO: name, phone, email.
- Drafts from the apply wizard (CQ-032) appear as `stage = draft` once that item exists.

**Frontend (`apps/borrower-portal`)**

- Route `/` for logged-in borrowers (logged-out → the CQ-015 login page).
- Portal shell: header with TQL logo, "Home", "Support" (CQ-034), and a sign-out menu; footer with core disclosures.
- Home: greeting, one card per application with a 4-step progress bar (Applied → In review → Pre-approved → Option selected), the stage label, the next-action button, and the LO contact card.
- No application → an empty state with "Start your application" (links to CQ-032's wizard; shows "Coming soon" until CQ-032 exists).
- Pending credit-check consent → a task banner at the top ("Your loan officer needs your permission for a credit check") linking to CQ-033's page.

## Out of scope

- The report page (CQ-022), the wizard (CQ-032), consent (CQ-033), support (CQ-034).

## References

- `docs/design/system-design.md` — Borrower Portal → Home; Application status machine.
- Built code to check in stage 1: CQ-015 borrower session and login pages, CQ-022 report route and token model.

## Acceptance criteria

- [ ] AC1 — Each of the 10 personas, logged in as the borrower, sees the stage and label from the table above for their seeded status (parametrized API test).
- [ ] AC2 — Aisha Coleman (NeedsAttention) sees "Application received"; the words "attention", "flag" or "error" appear nowhere in the portal response or page.
- [ ] AC3 — Marcus Hale's next action is "See your numbers" and opens his latest sent version; Luis Romero (OptionSelected) has `next_action = none`, sees the option-selected label, and reaches his report through a secondary "View your numbers" link.
- [ ] AC4 — A borrower with no applications sees the empty state with "Start your application".
- [ ] AC5 — A borrower can only see their own applications (API test with two borrowers).
- [ ] AC6 — At 375 px the progress bar and cards fit without horizontal scroll; react-doctor passes; Lighthouse accessibility ≥ 95.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Parametrized API test | `test_portal_stage_mapping[persona]` |
| AC2 | API + text scan | `test_portal_hides_internal_states` |
| AC3 | API + Playwright | `test_next_action_view_report`, `e2e/portal-home.spec.ts` |
| AC4 | Component test | `PortalHome.empty.test.tsx` |
| AC5 | API test | `test_portal_me_isolation` |
| AC6 | Playwright viewport + Lighthouse + react-doctor | evidence in post-dev.md |

## Notes for the agent

- Keep the status → stage mapping in one backend function; the frontend only renders `stage` and `label`.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
