# CQ-015 — Implementation plan

Written by the orchestrator in stages 1–3. Tasks are executed by Sonnet subagents in the item worktree.

## Decisions & questions (stage 1)

Gap check against the updated `system-design.md` (Borrower Portal intro, Decision #9) and CQ-014's plan. There are no big gaps open.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision (human, 2026-09-25) | Borrower auth method | Email + password + email OTP. There is no magic link. Design doc and CQ-020 spec updated on `phase-p2` (commit 9018ff6). |
| 2 | Decision (human) | First password | Self sign-up by email. A matching client is linked, otherwise a new client is created. |
| 3 | Decision | Reuse | `auth/otp`, `auth/otp/rate_limit`, `auth/sessions` with `principal="borrower"`, and `core/security`, `notifications/email`, `auth/users.normalize_email` from CQ-014. Nothing is copied. |
| 4 | Decision | Pending sign-up | `POST /signup` hashes the password immediately and puts {full_name, email, password_hash, mode="signup"} in the OTP challenge `extra`. The account and client are created only when `/otp/verify` succeeds, so an unverified email never creates rows. Login challenges carry `mode="login"` and `subject_id` = account id. |
| 5 | Decision | Existing account on sign-up | The caller gets the same response as a fresh sign-up: 200 with a random `challenge_id` that is never stored, so verify fails with "Invalid or expired code". The email says "You already have a Clear Quote account — sign in instead". No second account is created. |
| 6 | Decision | Matching a client | `lower(clients.email) == normalized email`. `clients.email` is not unique, so the oldest client (`created_at`, then `id`) is used. A client that already has an account is handled by Decision #5. |
| 7 | Decision | New client's LO | `clients.assigned_lo_id` is NOT NULL, so the new client goes to the active `lo`-role user with the fewest assigned clients (ties by `users.created_at`). If there is no LO, 409 `NO_LOAN_OFFICER` is returned via `ConflictError`. |
| 8 | Decision | Rate limits | Sign-up and login both call `check_login(valkey, principal="borrower", …)`, which uses the per-email and per-IP limits from settings. |
| 9 | Decision | Session | Cookie `cq_borrower_session`, TTL `borrower_session_ttl_seconds` (7 days), sliding. `borrower_accounts.last_login_at` is set on every verified login and sign-up. |
| 10 | Decision | `/me` shape | `{account_id, email, client_id, full_name, first_name, latest_application: {id, status} \| null}`. The latest application is by `created_at` for that client. `first_name` is the first word of `clients.full_name`. |
| 11 | Decision | Ownership rule | `ensure_borrower_owns_client(account, client_id)` raises `NotFoundError`, which returns 404, never 403, so a borrower cannot confirm that another client id exists. Later portal features call it (or filter by `account.client_id`). |
| 12 | Decision | Demo borrower | `seed_dev_users.py` also creates client "Casey Morgan" (`borrower@clearquote.test`, assigned to lo@), an account with `DEMO_BORROWER_PASSWORD` and `email_verified_at=now`, and an account for every existing client without one. It is idempotent. |
| 13 | Decision | Portal cookie visibility | Same as CQ-014 Decision #12: `credentials: "include"` (already in `@cq/api-client`). Portal on 3020 and API on localhost share a host. Railway is a CQ-035 follow-up. |

## Why

The quote email (CQ-020), report (CQ-022), borrower actions (CQ-024) and the whole P6 portal need a signed-in borrower tied to exactly one client.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Model + migration | `backend/app/features/auth/models.py`, `alembic/versions/<rev>_borrower_accounts_password.py` |
| Borrower auth | `backend/app/features/auth/borrower/{__init__,router,schemas,service}.py`, `tests/` |
| Core | `backend/app/core/auth.py` (borrower deps), `backend/app/core/registry.py`, `backend/app/core/tests/test_borrower_deps.py` |
| Seed | `backend/app/features/auth/users/service.py` (`seed_dev_borrowers`), `backend/scripts/seed_dev_users.py`, users tests |
| API client | `packages/api-client/openapi.json`, `src/schema.d.ts` (generated) |
| Portal | `apps/borrower-portal/src/**` (features/auth, app/login, app/signup, app/page.tsx, middleware.ts) |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration and model, borrower service and endpoints, borrower deps, registry, dev seed extension | — | model, migration, `auth/borrower/**`, `core/auth.py`, `core/registry.py`, `core/tests/test_borrower_deps.py`, `auth/users/**`, `backend/scripts/seed_dev_users.py` | AC1–AC8 |
| T2 | Regenerate api-client (orchestrator) | T1 | `packages/api-client/{openapi.json,src/schema.d.ts}` | tsc |
| T3 | Borrower Portal auth UI | T2 | `apps/borrower-portal/src/**` | AC9 |

## Wave schedule (stage 3)

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1 | One cohesive backend slice. The migration, service and endpoints share the model, and splitting them would make agents edit the same files. |
| 2 | T2 | The contract lands before the frontend. |
| 3 | T3 | Uses the generated client. |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `auth/borrower/tests/test_signup.py::test_signup_links_existing_client`, plus the e2e curl run |
| AC2 | `test_signup.py::test_signup_unknown_email_creates_client_for_least_loaded_lo` |
| AC3 | `test_signup.py::test_signup_existing_account_is_indistinguishable` |
| AC4 | `auth/borrower/tests/test_login.py` |
| AC5 | `test_login.py::test_cookies_do_not_cross_principals` |
| AC6 | `core/tests/test_borrower_deps.py` |
| AC7 | `alembic downgrade base && upgrade head` on `cq_test_p2` |
| AC8 | `auth/users/tests/test_seed_dev_users.py` |
| AC9 | borrower-portal vitest, react-doctor, e2e and screenshot |

## Progress

- [ ] T1
- [ ] T2
- [ ] T3
