# CQ-024 Borrower actions

| Field | Value |
| --- | --- |
| Phase | P4 Borrower Tier A |
| Depends on | CQ-022 |
| Kaneo task | CQ-024 in Kaneo (task id `ecrqlza5ruvr2uub5ct2xhck`) |
| Branch | `cq-024-borrower-actions` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The borrower can say "I'd like to move forward with this option" or ask about a different one, and the LO hears about it immediately. It closes the demo loop from the borrower's side without pretending to lock a rate.

## Scope

**Backend (owned by this item)**

- `POST /api/portal/reports/{token}/actions` (borrower session) with `{type, quote_id?, message?}`:

| Type | Allowed when | Effect |
| --- | --- | --- |
| `move_forward` | Version not expired, not superseded, status Sent or Viewed or Inquiry | Status → OptionSelected; stores `borrower_action` (type, quote_id, at); LO email "{Borrower} would like to move forward with {option label}" |
| `ask_other` | Same as above | Requires `message` (1–500 characters); status → Inquiry; LO email with the message and the option being viewed |
| `ask_updated` | Version expired | Optional message; status → Inquiry; LO email "{Borrower} asked for updated numbers" |

- After OptionSelected, `move_forward` and `ask_other` return 409; `ask_other` is the only type allowed after an Inquiry is answered by a new version.
- Every action writes an activity event, an `outbox_emails` row and a CRM event; emails go through SMTP (Mailpit locally).
- The report response (CQ-022) gains `borrower_action` so the page can render the confirmed state.

**Frontend (report page actions slot)**

- Primary button "I'd like to move forward with this option" (uses the currently selected option) and secondary "Ask about another option".
- Move forward → confirm dialog: "This tells {LO first name} you'd like to go ahead with {option label}. Your rate isn't locked yet — {LO first name} will contact you about next steps." Buttons: "Yes, let {LO first name} know" / "Cancel".
- Ask about another option → dialog with a textarea (placeholder "What would you like to change? For example, a lower cash to close.") and the current option shown for context.
- Confirmed state replaces the buttons: "You chose {option label} on {date}. {LO name} will be in touch." with LO contact details.
- Expired state (CQ-022 banner): "Ask for updated numbers" button → `ask_updated`.
- Errors: 409 shows the current state without an error-looking message; network errors show a retry message.

## Out of scope

- LO-side inbox or reply UI (the LO sees status, timeline and email; replying is by phone/email outside the app).
- Rate lock, e-signature, loan estimate.

## References

- `docs/design/system-design.md` — Application status machine, Borrower Portal → Quote report item 9, Decision 5 (non-binding).
- Seed persona 10 (Luis Romero) shows the resulting OptionSelected state.

## Acceptance criteria

- [ ] AC1 — On a freshly sent persona, "move forward" on the Buydown option sets status OptionSelected, stores the quote id, sends one email to the assigned LO in Mailpit naming the option, and writes one activity event and one CRM event.
- [ ] AC2 — After that, the page shows the confirmed state on reload, and a second `move_forward` returns 409 with no new email.
- [ ] AC3 — "Ask about another option" with an empty message is rejected (422); with a message it sets status Inquiry and the LO email contains the message.
- [ ] AC4 — Grace Kim's expired report shows only "Ask for updated numbers", which sets Inquiry and emails the LO; `move_forward` on her token returns 409.
- [ ] AC5 — No wording on the page or in the emails uses "accept", "lock" or "approved rate" (text scan test).
- [ ] AC6 — The LO console header status (CQ-016) shows the new status after its next poll; if CQ-025 is merged, its tile counts match too.
- [ ] AC7 — react-doctor passes; dialogs trap focus and close on Escape.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | Integration test with Mailpit | `test_move_forward_once` |
| AC3 | API tests | `test_ask_other_requires_message`, `test_ask_other_sets_inquiry` |
| AC4 | API + Playwright | `test_expired_allows_only_ask_updated`, `e2e/report-expired-actions.spec.ts` |
| AC5 | Text scan over templates and page | `test_no_binding_language` |
| AC6 | Playwright across both apps | `e2e/borrower-action-reflects-in-console.spec.ts` |
| AC7 | react-doctor + keyboard test | evidence in post-dev.md |

## Notes for the agent

- Like CQ-022, this can start before CQ-020 using the sent-version factory; re-verify AC1 end to end after CQ-020 merges.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
