# CQ-033 — Post-development notes

## Summary

A hard credit pull now runs only after the borrower authorizes it in the portal. `perform_hard_pull` (`backend/app/features/applications/credit/hard_pull.py`) refuses unless an accepted `hard_pull` consent exists. When it runs, it writes the middle of three scores as `representative_fico` (`source_ref="hard_pull"`, CQ-028a contract), sets `credit_pull_type = Hard_Pull`, upserts tradelines into liabilities, re-runs the rules, and marks quotes stale when the FICO bracket changes. The borrower endpoints (`/api/v1/portal/consents/{id}`, `/accept`, `/decline`) record the decision with text version `hard_pull_v1`, its SHA-256, the typed name, IP, user agent and time, and email the LO. The portal page `/tasks/credit-check/[id]` shows the text, a required checkbox, a required typed name, and Authorize / Decline, plus confirmation, expired and not-found states.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `CreditClient.hard_pull` | `CreditClient.pull_credit(key, HARD_PULL)` | The built Protocol (CQ-009) already takes the pull type; no mock edit was needed (plan.md #2). |
| "tradelines are refreshed into liabilities" | Upsert only: matched rows get the bureau amounts, new tradelines are added, rows missing from the report are kept | The mock report has no closed-account signal, and portal reports have no tradelines at all (plan.md #4). |
| — | `(portal)/stub-pages.test.tsx`: removed the credit-check row | That page is no longer a stub. This is a one-line edit outside the owned paths, made because it was necessary. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 Brandt: consent row with hash, IP and time; FICO = middle (690); one LO email | Met | `portal/consents/tests/test_consents_api.py::test_hard_pull_consent_flow` (row fields, FICO 690, exactly 1 LO email + outbox row, Credit section `accepted`/690); E2E `e2e/borrower-portal/credit-consent.spec.ts` passed on slot 23 (email link from Mailpit, UI authorize, Credit section API 690, Mailpit shows exactly 1 "Credit check authorized — FICO 690"); screenshots `evidence/consent-form-{1280,375}.png`, `evidence/consent-authorized-{1280,375}.png` |
| AC2 no accepted consent: raises and writes nothing | Met | `applications/credit/tests/test_hard_pull.py::test_hard_pull_requires_consent` (pending and declined rows present; 409 error; FICO, liabilities, events and integration calls unchanged) |
| AC3 decline stores reason, emails LO, Credit shows Declined, no pull | Met | `test_consents_api.py::test_hard_pull_decline` (reason stored, 1 LO email, 0 hard-pull integration calls, Credit section `declined` + reason, pull type still soft; a later accept → 409) |
| AC4 bucket crossing marks stale; same bucket leaves fresh | Met | `test_hard_pull.py::test_fico_bucket_change_marks_stale` (692→690 same 680–699: 0 stale; 692→675: every quote stale) |
| AC5 other borrower 404; 15-day-old request cannot be accepted | Met | `test_consents_api.py::test_consent_isolation` (GET/accept/decline 404, unknown id 404, signed out 401), `test_consent_expiry` (CLOCK_NOW +15 d → 409 `CONSENT_EXPIRED`, row persisted `expired`, no pull), `test_consent_expiry_persisted_on_read` |
| AC6 accepting twice pulls once | Met | `test_consents_api.py::test_consent_accept_idempotent` (2×200, 1 hard-pull integration call, 1 completed event, 1 LO email) |
| AC7 react-doctor; checkbox and typed name required and accessible | Met | `features/credit-consent/CreditConsent.test.tsx` (8 tests: labelled required inputs, `aria-invalid` + `aria-describedby` errors, focus on first invalid, server error `role=alert`, decline, expired and 404 states); `npx react-doctor -y --blocking error` 100/100 |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `make test` (pytest backend + seed) | 739 passed, 32 passed |
| Frontend tests | `make test` (vitest) | portal 120, lo-console 108, ui 163, api-client 2 passed |
| Lint / types | `make lint` (ruff, mypy, eslint, tsc, prettier) | clean |
| react-doctor | `npx react-doctor -y --blocking error` (borrower-portal) | 100/100, no issues |
| E2E | `pnpm exec playwright test e2e/borrower-portal/credit-consent.spec.ts --project=borrower-portal` (slot 23, API with `PORTAL_BASE_URL=http://localhost:3223`) | 1 passed |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | `_refresh_liabilities` inserted unmatched tradelines with $0 amounts. A renamed LO row, or a seed creditor mismatch (Marcus: LOS "Chase", bureau "Wells Fargo"), gained a phantom debt | Fixed: an unmatched tradeline is inserted only when it carries a monthly payment. `test_tradelines_keep_manual_rows_and_add_new` now also asserts that a no-amount line is not added. |
| Low | On a 401 the consent page redirected to `/login` without `next`, so the emailed link was lost after sign-in | Fixed: it uses `loginUrlFor('/tasks/credit-check/{id}')`. New test "sends an expired session to login and back to this request (401)". |

## How to test manually

1. `scripts/worktree-env.sh 23`, `make demo-reset`, then start the API with `PORTAL_BASE_URL=http://localhost:3223` and the portal on 3223.
2. As casey.nguyen (manager), `POST /api/v1/applications/{brandt id}/credit/hard-pull-request`.
3. Open the link in Tom Brandt's Mailpit email, sign in, tick the box, type "Tom Brandt" and click Authorize.
4. `GET /api/v1/applications/{id}/sections/credit` shows consent `accepted` and FICO 690. The LO has one "Credit check authorized — FICO 690" email.

## Follow-ups

- The E2E needs the API's `PORTAL_BASE_URL` to point at the slot's portal, or the emailed link goes to :3020.
- The LO console Credit tab (CQ-028b) renders the states from the Credit section, so no LO-console change is needed here (E11).

## Hardening round (branch `cq-033-consent-hardening`)

Fixes for the minors the CQ-033 review left open (after PR #24). Every fix has a test written first.

| Item | Fix | Evidence |
| --- | --- | --- |
| Lock upgrade | `sections/credit.py` `request_hard_pull` no longer takes a second `FOR UPDATE` on the application. The router's `lock_application` (`FOR NO KEY UPDATE`) already serialises it, and the 409-while-pending check runs under that lock. | `test_consent_hardening.py::test_request_hard_pull_takes_no_second_for_update` records every application lock taken by the request (all `FOR NO KEY UPDATE`); a second request gets 409 |
| m1 lock order | Accept locks the application's quotes first (`lock_application_quotes`: `select(Quote.id)` via the scenarios join, `with_for_update(of=Quote)`), then takes `lock_application`. This matches CQ-030's `mark_stale` order (quotes → versions → applications). The order is documented in the `hard_pull.py` and `service.py` docstrings. | `test_accept_locks_quotes_before_the_application` uses a statement spy on a bucket-crossing pull and checks the order: quotes lock, then application lock, then `UPDATE quotes` |
| m2 text proof | The checkbox sentence is now the last paragraph of `hard_pull_v1`, so the hash covers it. It was changed in place because this is pre-release and no v1 decision exists outside the rebuildable demo DBs. The GET returns `text.body`, `text.authorization` and `text.sha256`, where `sha256` hashes the whole text. Accept requires `text_version` and `text_sha256`; if either mismatches it returns 409 `CONSENT_TEXT_CHANGED` and records nothing. The portal labels the checkbox with `authorization` and sends back the sha it displayed. | `test_accept_rejects_a_changed_text` (wrong hash or version → 409, missing fields → 422, row still pending, no pull; the good hash is stored); `test_hard_pull_consent_flow` (body + authorization = v1 text, sha); Vitest "labels the checkbox with the versioned authorization sentence" and the accept-body assertion |
| m3 expiry race | `_expire_if_due` is now a conditional `UPDATE … WHERE id AND status = pending AND expires_at <= now`, followed by a re-read. It never overwrites an accepted or declined row. | `test_expiry_never_overwrites_a_decision[accepted/declined]` |
| m6 one consent per pull | `perform_hard_pull(db, application_id, *, consent_id)` requires that consent to be an accepted `hard_pull` consent of the same application (`HARD_PULL_CONSENT_REQUIRED`). If a `credit.hard_pull_completed` event already names the consent, it raises `HARD_PULL_CONSENT_USED`. The completed event's payload records `consent_id`. | `test_hard_pull.py::test_hard_pull_requires_consent` (AC2 direct: pending, declined and unknown ids are refused, nothing written), `test_hard_pull_uses_each_consent_once`, `test_hard_pull_writes_middle_score` (payload `consent_id`) |
| m5 duplicate tradelines | Candidates are now a list per (creditor, type) key, and each matched row is popped, so two Chase cards remain two accounts. | `test_tradelines_with_same_creditor_and_type_stay_separate` (two imported Chase cards take 111/222, and a third line is added as 333) |
| m4 provider failure (partial) | On an `IntegrationError`, the decision is rolled back, so the request stays pending and can be retried. A `credit.hard_pull_failed` event (consent id, error code) and the LO email "Credit check could not be completed" are then committed in a separate transaction, and the bureau error (502) is re-raised. The LO is emailed once per consent, and a failure while recording is logged without masking the 502 (code-review lows 1 and 2). | `test_provider_failure_keeps_the_request_pending` (forced failure through `set_forced_failure("credit")`: 502, row pending, 1 failed event, 1 LO email; a second failure adds an event but no email; after recovery a retry returns 200 with 1 completed event) |
| m7 portal | A 409 from accept or decline re-fetches the request and shows the outcome. If the request is still pending (text changed), the form remounts with a notice. A 401 on accept or decline goes to `/login?next=…`. `NAME_MISMATCH` sets the name field's error (`aria-invalid`, `aria-describedby`) and focuses it once the submit settles. | `CreditConsent.test.tsx`: 14 tests, including 409 accept → declined outcome, 409 decline → expired outcome, text-changed notice with the checkbox cleared, 401 accept → login, NAME_MISMATCH on the field |
| Nit: concurrent double accept | Two accepts are sent at once, each through its own session, against committed rows. | `test_consent_concurrency.py::test_concurrent_double_accept_pulls_once` (both 200/accepted, 1 hard-pull integration call, 1 completed event, 1 LO email) |

**Code review (medium):** no critical or major findings. The two lows in `_record_pull_failure` (the recording could mask the 502; one email per retry) are fixed as described above.

**Test log**

| Check | Result |
| --- | --- |
| `make lint` (ruff, mypy, eslint, tsc, prettier) | clean |
| `make test` | backend 756 passed, seed 32 passed; portal 126, lo-console 108, ui 163, api-client 2 passed |
| consents + credit tests ×3 (`portal/consents`, `applications/credit`, `sections/tests/test_credit.py`) | 24 passed, 24 passed, 24 passed |
| react-doctor (borrower-portal) | 100/100 |
| Slot-26 E2E: `make demo-reset`, API with `PORTAL_BASE_URL=http://localhost:3226`, worker, portal on 3226, `e2e/borrower-portal/credit-consent.spec.ts` | 1 passed |

**Follow-up (logged, not fixed):** `notifications/email/service.send_email` sends over SMTP before the caller commits. This is a shared issue with every caller: if the commit fails after the send, the email has gone out without its outbox row or decision. In the failure path the email is sent after the decision has been rolled back, so it matches what was committed. The fix belongs in the shared email service, for example sending after commit from the outbox.
