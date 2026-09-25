# CQ-015 — Post-development notes

## Summary

Borrowers create a portal account themselves and sign in with email + password and a 6-digit email OTP. The magic link was dropped by human decision on 2026-09-25, and the design doc was updated.

Sign-up behaviour:
- If the email matches an existing client, the new account links to that client.
- Otherwise a new client is created and assigned to the least-loaded LO.
- Signing up with an email that already has an account looks identical to a fresh sign-up.

Sessions use the `cq_borrower_session` httpOnly cookie with a 7-day sliding TTL in Valkey. They reuse CQ-014's OTP, rate-limit and session modules with principal `borrower`, and `get_current_borrower` plus `ensure_borrower_owns_client` give later portal features a signed-in client.

The Borrower Portal has `/signup`, `/login`, a signed-in placeholder home and logout.

The same item hardened the shared auth code:
- atomic OTP verify;
- separate sign-up rate limits;
- argon2 moved off the event loop;
- auth UI and error parsing that both apps share, moved into `@cq/ui`;
- request helpers and limits shared in `auth/common.py`.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Plan Decision #8: sign-up and login share `check_login` | Sign-up has its own `rl:borrower:signup:*` keys | Review: a sign-up flood could lock a borrower out of login (plan Decisions #8 and #14) |
| Short passwords rejected by the service (`ValidationAppError`) | Rejected by the schema (`min_length`) with FastAPI's 422; the service check stays | The rule is now in OpenAPI and `api-client` (Decision #17) |
| Scope: portal auth UI | Also refactored CQ-014's LO Console auth UI onto shared `@cq/ui/auth` pieces | Review: the portal copy was a near-duplicate of the console's (Decision #18) |
| CQ-014 OTP verify: HGETALL, then HINCRBY/DEL | Lua script for wrong-code attempts; success requires `DEL == 1` | Review: concurrent verify could revive a TTL-less key or let two correct verifies both succeed |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `auth/borrower/tests/test_signup.py::test_signup_links_existing_client`. E2E: sign-up of a seeded client's email, Mailpit code, verify; `/me.client_id` equals the existing client (T1 run). Final run with a new address `e2e-final-25592@clearquote.test`: 200, `set-cookie: cq_borrower_session=…; HttpOnly; Max-Age=604800; Path=/; SameSite=lax`, `/me` first_name "Pat" |
| AC2 | Pass | `test_signup.py::test_signup_unknown_email_creates_client_for_least_loaded_lo`. E2E: new client "Pat Rivera" assigned to `lo@clearquote.test` |
| AC3 | Pass | `test_signup.py::test_signup_existing_account_is_indistinguishable`, `::test_signup_existing_account_still_hashes_password`. E2E: sign-up for `borrower@clearquote.test` returned 200 with a challenge_id, and the Mailpit subject was "You already have a Clear Quote account" |
| AC4 | Pass | `auth/borrower/tests/test_login.py` (same 401, attempts exhausted, 429). E2E: login as `borrower@clearquote.test` then OTP then `/me` first_name "Casey" |
| AC5 | Pass | `test_login.py::test_cookies_do_not_cross_principals`. E2E: borrower cookie on staff `/me` returns 401 |
| AC6 | Pass | `core/tests/test_borrower_deps.py` (404 for another client, pass for own) |
| AC7 | Pass | On fresh DB `cq_mig_p2`: `alembic upgrade head`, then `downgrade base`, then `upgrade head`; ends at `642b3bc55d31 (head)` with `password_hash` and `email_verified_at` present |
| AC8 | Pass | `auth/users/tests/test_seed_dev_users.py` (idempotent; hashes once; no-op rerun hashes nothing). E2E: repeated `seed_dev_users.py` runs are stable |
| AC9 | Pass | borrower-portal vitest 36/36, `packages/ui` 66/66; react-doctor exit 0 (portal 83, ui 90). E2E: `/` without cookie gives 307 to `/login`; with cookie 200; logout 204, then `/me` 401. Screenshots `evidence/login.png`, `evidence/signup.png` (headless Chrome) |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | 177 passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | Clean |
| Frontend | `make test` (ui 66, lo-console 20, borrower-portal 36, api-client 2) | All passed |
| react-doctor | `npx react-doctor -y --blocking error` in lo-console, borrower-portal, packages/ui | Exit 0; 83 / 83 / 90. Warnings: `nextjs-no-client-side-redirect` on home pages (accepted, same as CQ-014) and `prefer-html-dialog` on Overlay (pre-existing) |
| Migration | `alembic upgrade head` / `downgrade base` / `upgrade head` on a fresh DB | Clean |

## Review findings (stage 6)

Implementer and helper reviews during the waves found the following; all are fixed:
- timing parity on existing-account sign-up;
- seed collisions on normalized email;
- shared rate-limit lockout;
- OTP verify races;
- sync argon2 on the event loop;
- duplicated `_client_ip` and length caps;
- password minimum missing from the contract;
- raw `full_name` size cap;
- seed hashing once per row;
- duplicated auth UI across the apps;
- FastAPI `detail` 422 shown as a generic error.

Fresh reviewer (Sonnet, did not write the code):

| Severity | Finding | Resolution |
| --- | --- | --- |
| minor | No test for two concurrent sign-up verifies of the same new email; correctness relies on the losing request's transaction rolling back its flushed `Client` | Follow-up (a concurrency test needs two DB sessions outside the per-test rollback fixture) |
| minor | `lower(clients.email)` lookup has no functional index | Follow-up for CQ-010/CQ-026 when client volume grows |
| nit | LO Console 429/pending display is now covered by `packages/ui` tests, not app tests | Accepted: shared coverage model (Decision #18) |

No critical or major findings are open.

## After merge to main

Phase 2 was merged with Phase 1 on 2026-09-25 (see `docs/backlog/phase-p2-merge-plan.md`). What changed for this item:

- Demo users now come only from `make demo-reset`. Staff are the persona users in `seed/users.yaml` at `@clearquote-demo.test`: LOs `jordan.lee` and `morgan.reyes`, Manager `casey.nguyen` and Admin `riley.admin`. Every persona client also gets a borrower account (for example `marcus.hale@clearquote-demo.test`) when `SEED_BORROWER_PASSWORD` is set.
- The `DEMO_STAFF_PASSWORD` / `DEMO_BORROWER_PASSWORD` env vars are gone, and no password value is committed anywhere. Seeded passwords come from `SEED_STAFF_PASSWORD` (required by `make demo-reset`) and `SEED_BORROWER_PASSWORD` (optional; blank means no borrower accounts), both blank in `.env.example`. The seed hashes them with argon2 (`app.core.security.hash_password`), the same scheme login verifies against.
- `backend/scripts/seed_dev_users.py`, `DEV_USERS`, `seed_dev_users` and `seed_dev_borrowers` were retired. `backend/scripts/create_user.py` remains for creating individual staff users.
- Phase 1's pricing and pipeline routes now require a staff session (`CurrentStaff`) and scope applications with `scope_applications`: an LO sees only their own, a Manager or Admin sees all, and out-of-scope ids return 404. `DEV_LO_ID` and `get_current_lo_stub` were removed.

## How to test manually

1. `make up`. Set `SEED_STAFF_PASSWORD` and `SEED_BORROWER_PASSWORD` in your local `.env` (any values of at least 8 characters), then run `make demo-reset`.
2. Start the API (`make api`), then `pnpm --filter @cq/borrower-portal dev` (http://localhost:3020).
3. Visit `/` and you are redirected to `/login`. Choose "Create an account", enter a name, a new email and a password, get the code from Mailpit (http://localhost:8025) and enter it. The home page shows "Hi {first name}" and "No application yet".
4. Log out, then sign in as a persona client, for example `marcus.hale@clearquote-demo.test`, with your `SEED_BORROWER_PASSWORD`. The home page shows "Hi Marcus" and the status of Marcus's application.

## Follow-ups

- CQ-035: uvicorn `--proxy-headers --forwarded-allow-ips` so per-IP limits see real client IPs; same-site cookie setup across Railway domains.
- Concurrency test for a double sign-up verify, and a `lower(email)` index on `clients`.
- CQ-020 and CQ-022: the quote email links to the portal report, which requires sign-in; `quote_packages.report_token` stays an opaque URL id.
- ~~CQ-010: call `seed_dev_users` / `seed_dev_borrowers` from `make demo-reset` so personas get portal accounts.~~ Done at the merge to main: `make demo-reset` creates persona borrower accounts when `SEED_BORROWER_PASSWORD` is set.
