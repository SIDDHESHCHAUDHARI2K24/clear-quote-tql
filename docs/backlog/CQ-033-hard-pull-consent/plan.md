# CQ-033 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

Gap check against spec.md, system-design.md (Borrower Portal → Hard-pull consent, `consents`, `CreditClient`) and phase-p5-p6-plan.md E11/E12/E14. No big gaps.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Consent text | `features/portal/consents/consent_text.py`: `HARD_PULL_TEXT_VERSION = "hard_pull_v1"`, one text naming Clear Quote / the LO, the three bureaus (Experian, Equifax, TransUnion), the purpose (final pre-approval and pricing) and the score effect (a hard inquiry may lower the score by a few points). SHA-256 of the exact text is stored in `consents.text_hash` with `text_version`. Changing the text means a new version. |
| 2 | Decision | `CreditClient.hard_pull` | The spec names `CreditClient.hard_pull`; the built Protocol has `pull_credit(loan_number, pull_type)` (CQ-009). The service calls `pull_credit(key, CreditPullType.HARD_PULL)`; no mock edit needed. The key is `application.los_loan_guid`, or `portal_credit_key(application.id)` for a portal application (E14). |
| 3 | Decision | FICO write (CQ-028a #12 contract) | Upsert `field_values.representative_fico = middle_score` with `source = credit_bureau`, `source_ref = "hard_pull"`, and `credit_pull_type = "Hard_Pull"` (same source/ref). |
| 4 | Decision | Tradeline refresh | The mock's tradelines carry `creditor`/`type`/`status` and optionally `monthly_payment`/`balance`. Refresh = upsert: a tradeline matching an imported liability (same creditor + type, case-insensitive) updates payment/balance when the tradeline has them; an unmatched tradeline is inserted only when it carries a monthly payment (never a phantom $0 debt; review finding 1). LO-added rows (`row:liabilities:*` marker) and rows the LO edited (`orig:liabilities:{id}:*`) are never touched, same spirit as CQ-028a's import. Imported rows absent from the report are **kept**: the mock report has no "closed" signal, and a portal report has no tradelines at all, so deleting would wipe the wizard's liabilities. |
| 5 | Decision | Pricing bucket (AC4) | The bucket is the existing `sections.service.fico_bracket` (20-point bands `<620`…`780+`). The rate-sheet `min_fico` tiers (660/680/700) all fall on those band edges, so any tier crossing is also a bracket crossing. A bracket change calls CQ-030's `mark_application_quotes_stale(db, app_id, reason="fico_bucket_change …")` and is logged. Brandt (692 soft → 690 hard) stays in 680–699, so AC1 leaves quotes fresh. |
| 6 | Decision | Typed-name match | Case-insensitive, whitespace-collapsed match against the primary borrower party's `first last`, falling back to `clients.full_name`. The GET returns `borrower_name` so the page can say "Type your full name: Tom Brandt". Mismatch → 422. |
| 7 | Decision | Expiry on read | GET, accept and decline all run `_expire_if_due`: a pending row with `expires_at <= clock.now()` is persisted as `expired` (CQ-028a #13 left persisting to us). Accept/decline of an expired request → 409 `CONSENT_EXPIRED`. |
| 8 | Decision | Idempotency (AC6) | Accept takes `lock_application` first, then re-reads the consent (`populate_existing`). Already `accepted` → 200 with the current state, no second pull. `declined`/`expired` → 409. |
| 9 | Decision | Guard (AC2) | `perform_hard_pull(db, application_id)` raises `HardPullConsentRequiredError` (a `ConflictError`, 409, code `HARD_PULL_CONSENT_REQUIRED`) and logs a warning unless an `accepted` `hard_pull` consent exists; the check runs before any provider call, so nothing (not even an integration-call log) is written. |
| 10 | Decision | Failure of the pull | If the provider fails, the whole accept transaction rolls back (the consent stays pending, the borrower sees an error and can retry). Recording "accepted" without the pull would leave the LO with an authorized-but-not-pulled state the Credit tab cannot show. |
| 11 | Decision | Events and emails | Events `credit.consent_accepted`, `credit.consent_declined` (actor `borrower`), `credit.hard_pull_completed` (actor `system`, payload fico, previous fico, brackets, stale count). No borrower email/name in payloads. LO emails: "Credit check authorized — FICO {score}" and "Credit check declined", both to the application's LO with `application_id`. |
| 12 | Decision | Isolation (AC5) | Consent → application → `ensure_borrower_owns_client`; a non-`hard_pull` consent id or a missing one is the same 404. |
| 13 | Decision | Re-run rules | `verification.service.run_and_persist(app_id, db, commit=False)` inside the same transaction (it re-takes the same row lock, a no-op). Not `reverify_and_maybe_resume` (owned by the hardening unit; no pipeline resume is needed for a FICO refresh). |

## Why

A hard pull must only happen after an explicit, recorded borrower authorization, and its result must flow back into the Credit tab and pricing.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Consent text | create `backend/app/features/portal/consents/consent_text.py` |
| Borrower API | create `backend/app/features/portal/consents/{router,schemas,service,templates}.py`, `tests/` |
| Pull service | create `backend/app/features/applications/credit/hard_pull.py`, `credit/tests/test_hard_pull.py` |
| Registry | one line in `backend/app/core/registry.py` |
| api-client | regenerate `packages/api-client` |
| Portal | `apps/borrower-portal/src/app/(portal)/tasks/credit-check/[id]/page.tsx`, `src/features/credit-consent/**` |
| E2E | `e2e/borrower-portal/credit-consent.spec.ts` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Consent text + hash | — | `consent_text.py` | covered by T3 tests |
| T2 | `perform_hard_pull` service | — | `credit/hard_pull.py` | `test_hard_pull_requires_consent`, `test_fico_bucket_change_marks_stale` |
| T3 | Portal consent endpoints + registry | T1, T2 | `portal/consents/**`, registry | `test_hard_pull_consent_flow`, `test_hard_pull_decline`, `test_consent_isolation`, `test_consent_expiry`, `test_consent_accept_idempotent` |
| T4 | api-client | T3 | `packages/api-client` | tsc |
| T5 | Portal page + feature | T4 | `(portal)/tasks/credit-check/**`, `features/credit-consent/**` | `CreditConsent.test.tsx`, react-doctor |
| T6 | E2E | T5 | `e2e/borrower-portal/credit-consent.spec.ts` | Playwright |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Service contract first |
| 2 | T3 → T4 | API, then the generated client |
| 3 | T5 → T6 | UI on the generated client, then E2E |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 Brandt accept → consent row (hash, IP, time), FICO = middle, one LO email | `portal/consents/tests/test_consents_api.py::test_hard_pull_consent_flow`; E2E Mailpit check |
| AC2 no accepted consent → raises, writes nothing | `applications/credit/tests/test_hard_pull.py::test_hard_pull_requires_consent` |
| AC3 decline stores reason, emails LO, Credit shows Declined, no pull | `test_consents_api.py::test_hard_pull_decline` |
| AC4 bucket crossing marks stale; same bucket leaves fresh | `test_hard_pull.py::test_fico_bucket_change_marks_stale` |
| AC5 other borrower 404; 15-day-old request cannot be accepted | `test_consents_api.py::test_consent_isolation`, `test_consent_expiry` |
| AC6 accept twice → one pull | `test_consents_api.py::test_consent_accept_idempotent` |
| AC7 react-doctor; checkbox + typed name required and accessible | `features/credit-consent/CreditConsent.test.tsx`, `npx react-doctor` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
