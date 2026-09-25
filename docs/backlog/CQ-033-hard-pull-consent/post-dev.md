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
