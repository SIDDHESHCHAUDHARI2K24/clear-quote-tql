# CQ-015 Borrower auth

| Field | Value |
| --- | --- |
| Phase | P2 Auth |
| Depends on | CQ-014 |
| Kaneo task | CQ-015 in Kaneo (task id `wpmdf28umbsvrhtrtl634tab`) |
| Branch | `cq-015-borrower-auth` |
| Status | Ready — filled from design docs and human answers on 2026-09-25 (magic link dropped by human decision) |

## Goal

Borrowers create a portal account themselves, then sign in with email + password and a 6-digit email OTP. Every later portal page (report, home, apply, support) knows which client is signed in and shows only that client's data.

## Scope

- Migration: `borrower_accounts.password_hash` and `email_verified_at` (both nullable).
- Self sign-up: full name, email, password → email OTP → account created. If the email matches an existing client (case-insensitive), the account links to it; otherwise a new client is created and assigned to the LO with the fewest clients.
- Login: email + password → email OTP → session. Same OTP limits and rate limits as staff (reuse CQ-014's `auth/otp` and `auth/sessions` with principal `borrower`).
- Sessions: httpOnly cookie `cq_borrower_session`, 7-day sliding TTL in Valkey.
- Endpoints `/api/v1/auth/borrower/{signup, login, otp/verify, logout, me}`; `/me` returns the account, the client and the latest application's id + status (or none).
- `core/auth.py`: `get_current_borrower` / `CurrentBorrower`, and `ensure_borrower_owns_client(...)`, which returns 404 for another client's data.
- `seed_dev_users.py` also creates a demo borrower (`borrower@clearquote.test`, linked to a client of `lo@`) and borrower accounts for any existing client without one, using `DEMO_BORROWER_PASSWORD`.
- Borrower Portal: `/signup`, `/login` (each with the OTP step), signed-in placeholder home ("Hi {first name}", application status or "No application yet"), logout, and middleware redirecting signed-out visitors.

## Out of scope

- Magic links (dropped by human decision, 2026-09-25). `quote_packages.report_token` stays an opaque report URL id with no auth meaning; CQ-022 decides how the report route uses it.
- The real home/status page (CQ-031), the report page (CQ-022) and the apply wizard (CQ-032).
- Password reset.

## References

- `docs/design/system-design.md`: "Borrower Portal" intro (updated 2026-09-25), "Data model" (`borrower_accounts`, `clients`), Decision #9.
- `docs/backlog/CQ-014-staff-auth/plan.md`: Decisions #4–#13 (hashing, OTP, rate limits, sessions, cookies, test Valkey).

## Acceptance criteria

- [ ] AC1 — A borrower signs up with a seeded client's email, gets the OTP in Mailpit, verifies it, and `/me` returns that existing client (no new client row).
- [ ] AC2 — Signing up with an unknown email creates a client assigned to the LO with the fewest clients, plus a linked borrower account.
- [ ] AC3 — Signing up with an email that already has an account looks the same to the caller (200 with a challenge id); the email sent says an account exists, and no second account is created.
- [ ] AC4 — Borrower login: a wrong password and an unknown email return the same 401; OTP expiry, the 5-attempt limit and the rate limit apply as for staff.
- [ ] AC5 — A borrower cookie gets 401 on staff `/me`, and a staff cookie gets 401 on borrower `/me`.
- [ ] AC6 — `ensure_borrower_owns_client` returns 404 for another client's id and passes for the borrower's own.
- [ ] AC7 — The migration upgrades and downgrades cleanly on a fresh DB.
- [ ] AC8 — `seed_dev_users.py` creates the demo borrower and stays idempotent.
- [ ] AC9 — Portal sign-up → OTP → home → logout and login → OTP → home work against the local API; vitest and react-doctor pass.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | API + e2e | `features/auth/borrower/tests/test_signup.py::test_signup_links_existing_client`; curl + Mailpit recipe |
| AC2 | API | `test_signup.py::test_signup_unknown_email_creates_client_for_least_loaded_lo` |
| AC3 | API | `test_signup.py::test_signup_existing_account_is_indistinguishable` |
| AC4 | API | `features/auth/borrower/tests/test_login.py` |
| AC5 | API | `test_login.py::test_cookies_do_not_cross_principals` |
| AC6 | unit | `backend/app/core/tests/test_borrower_deps.py` |
| AC7 | migration | `uv run alembic downgrade base && uv run alembic upgrade head` on `cq_test_p2`; conftest runs upgrade each session |
| AC8 | DB | `features/auth/users/tests/test_seed_dev_users.py` (extended) |
| AC9 | component + e2e | borrower-portal vitest; react-doctor; curl flow; screenshot |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- The worktree `.env` points at `cq_dev_p2` / `cq_test_p2` / Valkey db 2 (tests db 3); the API runs on port 8012 for e2e. Never use `cq_dev`, `cq_test` or port 8000.
