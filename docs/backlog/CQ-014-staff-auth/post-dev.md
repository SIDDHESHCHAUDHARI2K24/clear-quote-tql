# CQ-014 — Post-development notes

## Summary

Staff sign in to the LO Console with email + password, then a 6-digit email OTP. OTP challenges, login rate limits and sessions live in Valkey (hashed keys, 5-minute OTP, 5 attempts, 12 h sliding session in an httpOnly `cq_staff_session` cookie). `core/auth.py` gives every later feature `get_current_staff`, `require_roles(...)` and `scope_applications(...)` (LO sees own files; Manager/Admin see all, Manager can filter by LO). The first real email sender (`notifications/email`) writes `outbox_emails` and delivers over SMTP to Mailpit; CQ-015/020/024/034 reuse it. `seed_dev_users.py` creates lo@, manager@ and admin@clearquote.test until CQ-010 seeds personas. Built in parallel with P1 on `phase-p2`, isolated to `cq_dev_p2`/`cq_test_p2` and its own Valkey dbs.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Tests use Valkey from `VALKEY_URL` (plan Decision #13 first draft) | Tests use `TEST_VALKEY_URL`, default `VALKEY_URL` with db 15 | The fixture `FLUSHDB`s; a local `make test` must not wipe the dev server's sessions in db 0 |
| — | `features/auth/principal.py`, `features/auth/valkey_decode.py` added | Shared `Principal` type and a decode helper used by both OTP and session modules (review finding) |
| LO Console home kept the API health indicator (CQ-005 placeholder) | Home is now the signed-in placeholder (name, role, logout) | Spec scope: signed-in home; health remains at `/health` |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `email/tests/test_service.py` (4), `auth/staff/tests/test_login_flow.py::test_login_sends_otp_email`; e2e: login for `LO@clearquote.test` → Mailpit message "Your Clear Quote sign-in code" with code `824243`; `outbox_emails` row `lo@clearquote.test|sent` |
| AC2 | Pass | `test_login_flow.py::test_bad_credentials_same_401` (identical body); unknown email runs a dummy argon2 verify |
| AC3 | Pass | `auth/otp/tests/test_otp.py::test_expired`, `::test_attempts_exhausted` |
| AC4 | Pass | `auth/otp/tests/test_rate_limit.py`; `test_login_flow.py::test_login_rate_limited`, `::test_login_rate_limit_is_case_and_whitespace_insensitive` |
| AC5 | Pass | `test_login_flow.py::test_cookie_flags_me_logout`; e2e `set-cookie: cq_staff_session=…; HttpOnly; Max-Age=43200; Path=/; SameSite=lax`, `/me` 200 → logout 204 → `/me` 401 `Not signed in` |
| AC6 | Pass | `core/tests/test_auth_deps.py::test_require_roles` (LO 403 `FORBIDDEN`, Admin 200) |
| AC7 | Pass | `core/tests/test_auth_deps.py::test_scope_applications` (LO cannot widen via `lo_id`; Manager all + filter) |
| AC8 | Pass | `auth/users/tests/test_seed_dev_users.py`; e2e: script run 3× → same 3 users in `cq_dev_p2` |
| AC9 | Pass | lo-console vitest 17/17 (LoginForm, OtpForm, AuthFlow, home); react-doctor exit 0, score 83; e2e: console `/` without cookie → 307 `/login`, with cookie → 200; screenshot `evidence/login.png` (headless Chrome — the Chrome-extension browser tools were not available in this session) |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | 139 passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | Clean |
| Frontend | `make test` (vitest: ui 27, borrower-portal 4, lo-console 17, api-client 2) | All passed |
| react-doctor | `cd apps/lo-console && npx react-doctor -y --blocking error` | Exit 0; 83/100; 2 warnings `nextjs-no-client-side-redirect` on `page.tsx` (accepted: redirect depends on the runtime `/me` result) |

## Review findings (stage 6)

Implementer-side `code-review` passes (T1–T6) fixed: argon2 `VerificationError` on corrupted hashes, unsalted OTP hash (now HMAC with `SECRET_KEY`), rate-limit key not email-normalized, principal leak / forgeable reserved fields in OTP challenges, non-atomic HSET+EXPIRE and INCR+EXPIRE, oversized login input, `create_user` duplicate race, stale-cookie redirect loop, unhandled logout failure.

Fresh reviewer (Sonnet, did not write the code):

| Severity | Finding | Resolution |
| --- | --- | --- |
| major | post-dev.md unfilled | This file |
| minor | `OtpVerifyRequest` fields uncapped | Fixed: `challenge_id` ≤ 64, `code` ≤ 6; `test_verify_rejects_oversized_fields` |
| minor | No request-rate limit on `/otp/verify` | Accepted, plan Decision #14 |
| nit | Demo passwords committed in `.env.example` | Kept, plan Decision #15 |

No critical/major open.

## How to test manually

1. `make up`; in the worktree `uv run alembic upgrade head && uv run python backend/scripts/seed_dev_users.py`.
2. `make api` (or port 8012 in the P2 worktree) and `pnpm --filter @cq/lo-console dev`.
3. Open http://localhost:3010 → redirected to `/login`. Sign in as `lo@clearquote.test` / `DEMO_STAFF_PASSWORD`.
4. Open Mailpit http://localhost:8025, copy the 6-digit code, enter it → "Signed in as Jordan Avery (Loan Officer)". Log out → back at `/login`.

## Follow-ups

- CQ-035: the console and API on different Railway domains need a same-site setup (Next rewrites/proxy) for the session cookie (plan Decision #12).
- CQ-010: call `create_user` / `seed_dev_users` from `make demo-reset`.
- P1 merge: if P1 adds its own email sender, fold it into `notifications/email`.
