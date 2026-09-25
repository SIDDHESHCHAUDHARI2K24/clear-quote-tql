# CQ-034 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Stage mapping (foundation checked; CQ-031 not merged into `phase-p5-p6` yet — `features/portal/home/` doesn't exist) | Decided: a small local `_stage_for` helper in `support/service.py` duplicates CQ-031's status→stage table (spec.md's table verbatim) for the email body only. For `STALE`, disambiguates "never sent" vs "after a send" by checking whether any `QuotePackage` row for the application has `sent_at` set (same signal CQ-031 will use). **Follow-up:** once CQ-031 merges, switch this call site to its canonical function and delete the local copy. |
| 2 | Decision | `lo_console_base_url` setting | Decided: added `settings.lo_console_base_url: str = "http://localhost:3010"` to `core/config.py` (mirrors the existing `support_inbox`/`stale_check_interval_seconds` P5/P6-foundation settings block; no such setting existed before this item). `.env.example` documents `LO_CONSOLE_BASE_URL`. The email body links to `{lo_console_base_url}/applications/{id}`. |
| 3 | Decision | Phone prefill source | Decided: **`/me`** (`GET /api/v1/auth/borrower/me`, `BorrowerMeOut`), not the party record. `useBorrowerSession()`'s `me` is already loaded once per portal session (no extra request), and `build_me` already fetches the `Client` row — this item adds `phone: str | None` to `BorrowerMeOut` (sourced from `client.phone`) as a small, additive, backward-compatible edit to `auth/borrower/{schemas,service}.py` (not an owned file — logged here per AGENTS.md "edit anything else only for a small necessity"). The party record (`application_parties.cell_phone`) is per-application, not per-borrower, and CQ-034 has no application scope to pick one from for a borrower with 0 or 2+ applications. |
| 4 | Decision | Support reference alphabet | Decided: `SUP-XXXXX`, 5 chars drawn from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (32 chars; excludes `0/O/1/I/L` — "unambiguous characters" per spec). Collision handled by inserting inside a `db.begin_nested()` SAVEPOINT and retrying on `IntegrityError`, up to 10 attempts (same pattern as `auth/users/service.py::_insert_user`). |
| 5 | Decision | Rate-limit key / message | Decided: `rl:support:borrower:{borrower_account_id}`, `hit(valkey, key, limit=5, window_seconds=3600)` (`otp/rate_limit.py`, per spec/brief). The 6th call's `RateLimitedError` is caught and re-raised with message `"Please try again later"` (AC4's exact wording) instead of `hit`'s own default `"Too many attempts. Try again later."` — no edit to the shared `rate_limit.py` needed. |
| 6 | Decision | Activity event type | Decided: `support.requested` (new type; not in the existing `pipeline.*`/`application.*`/`quote.*` list since no prior item wrote a support event). Payload: `{reference, topic}`. |
| 7 | Decision | Response shape | Decided: `POST /portal/support` returns `{reference, lo: {name, email, phone}}` — the confirmation UI needs both without a second round trip; `preferred_contact` isn't echoed back since the form already has it in local state. |
| 8 | Decision | Validation → field errors (AC3) | Decided: pydantic `Field`/`field_validator`/`model_validator(mode="after")` on `SupportRequestCreate` (mirrors `auth/borrower/schemas.py`'s `full_name` pattern) — a 9-char message or `preferred_contact=phone` with no phone both raise `ValueError`, which FastAPI turns into a 422 with per-field `detail[].loc`/`msg` (same shape every other item in this codebase relies on for "field errors"; `packages/ui`'s `extractErrorMessage` already parses it). |
| 9 | Decision | `(portal)/page.test.tsx` edit | Decided: the P5/P6 foundation's stub-page test (`apps/borrower-portal/src/app/(portal)/page.test.tsx`, not an owned file) asserted `/support` still showed the "Built in CQ-034" stub via an `it.each` shared with the Apply/Credit-check stubs. Small necessity: dropped the Support row (and its now-unused `SupportPage` import) since `/support` is no longer a stub — its own coverage moved to `src/features/support/SupportForm.test.tsx` (an owned file). |

No big gaps.

## Why

A borrower who is stuck needs a fast way to reach a human without an LO having to reconstruct their context from scratch. This item is a single form → one DB row → two emails (support inbox + borrower confirmation) → one activity event, gated by a per-borrower rate limit so the inbox can't be flooded.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend | create `backend/app/features/portal/support/{router,schemas,service,templates}.py` + `tests/{conftest,test_router,test_templates}.py`; modify `backend/app/core/config.py` (+`.env.example`), `backend/app/core/registry.py` (+1 line), `backend/app/features/auth/borrower/{schemas,service}.py` (+`phone` on `BorrowerMeOut`) |
| Frontend | fill `apps/borrower-portal/src/app/(portal)/support/page.tsx`; create `apps/borrower-portal/src/features/support/{SupportForm,api}.tsx|.ts` + tests; edit `apps/borrower-portal/src/app/login/page.tsx` (one line: "Need help signing in?") |
| e2e | create `e2e/borrower-portal/support.spec.ts` |
| Generated | `packages/api-client` via `make api-client` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Settings (`support_inbox` already exists; add `lo_console_base_url`) | — | `core/config.py`, `.env.example` | covered by T3's router tests reading the setting |
| T2 | `phone` on `BorrowerMeOut` | — | `auth/borrower/{schemas,service}.py` | existing `auth/borrower/tests/test_signup.py`/`test_login.py` stay green; new assertion in one existing `/me` test |
| T3 | Backend: schemas, service, templates, router | T1, T2 | `features/portal/support/*` | `test_support_request_emails` (AC1/AC2), `test_support_validation` (AC3), `test_support_rate_limit` (AC4), `test_support_without_application` (AC5), `test_templates.py` |
| T4 | Registry + api-client regen | T3 | `core/registry.py`, `packages/api-client` | `make api-client` diff reviewed |
| T5 | Frontend: `SupportForm` + `api.ts` + page | T4 | `src/features/support/**`, `(portal)/support/page.tsx` | `SupportForm.test.tsx` (AC6: keyboard operable, visible+linked errors, 429 message, confirmation state) |
| T6 | Login page help line | — | `app/login/page.tsx` | existing login page test stays green; one new assertion |
| T7 | e2e | T5, T6 | `e2e/borrower-portal/support.spec.ts` | AC1 via Mailpit |

## Wave schedule (stage 3)

Single worker, sequential (no sub-agents needed for a unit this size).

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Settings and the shared `/me` contract before anything reads them |
| 2 | T3 | Backend feature, TDD |
| 3 | T4 | Regenerate the client once the backend contract is stable |
| 4 | T5, T6 | Frontend, built against the regenerated client |
| 5 | T7 | e2e once both sides are up |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_support_request_emails`; `e2e/borrower-portal/support.spec.ts` |
| AC2 | `test_support_request_emails` (outbox row + `ActivityEvent` count) |
| AC3 | `test_support_validation` |
| AC4 | `test_support_rate_limit`; `SupportForm.test.tsx` (429 → "Please try again later") |
| AC5 | `test_support_without_application` |
| AC6 | `SupportForm.test.tsx` + `npx react-doctor -y --blocking error` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
