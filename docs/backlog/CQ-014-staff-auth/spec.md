# CQ-014 Staff auth

| Field | Value |
| --- | --- |
| Phase | P2 Auth |
| Depends on | CQ-004, CQ-007 |
| Kaneo task | CQ-014 in Kaneo (task id `pf867pgf6t8kvnq4v8ngn051`) |
| Branch | `cq-014-staff-auth` |
| Status | Ready — filled from design docs and human answers on 2026-09-25 |

## Goal

Loan officers, managers and admins log in to the LO Console with email + password and a 6-digit email OTP, and every later console feature can ask "who is this and what may they see". Without it no console screen (P3, P5) can be demoed.

## Scope

- Password hashing (argon2) and a `create_user` service; `backend/scripts/create_user.py` and an idempotent `backend/scripts/seed_dev_users.py` (lo@, manager@, admin@clearquote.test, password from `DEMO_STAFF_PASSWORD`).
- Email OTP: 6 digits, 5-minute expiry, 5 attempts, stored hashed in Valkey. Rate limits in Valkey on login/OTP issue.
- Server-side sessions in Valkey, opaque id in the httpOnly cookie `cq_staff_session` (12 h sliding TTL).
- Endpoints `/api/v1/auth/staff/{login, otp/verify, logout, me}`.
- `core/auth.py` dependencies: `get_current_staff`, `require_roles(...)`, and `scope_applications(stmt, user)` (LO sees own files; Manager/Admin see all; Manager may filter by LO).
- `notifications/email`: `send_email(...)` writes an `outbox_emails` row and delivers over SMTP (Mailpit locally). Reused by CQ-015, CQ-020, CQ-024, CQ-034.
- LO Console: `/login` (email + password → OTP step), signed-in placeholder home showing name + role, logout, redirect to `/login` when signed out.
- Regenerated `packages/api-client`.

## Out of scope

- Borrower auth (CQ-015). The OTP/session modules are written so CQ-015 can add a borrower principal, but only staff is wired here.
- User administration UI, password reset, MFA beyond email OTP.
- Real dashboard or applications list (P5); the home page is a placeholder.
- Persona seed (CQ-010) — it will call `create_user`.

## References

- `docs/design/system-design.md` — "LO Console" (roles, Auth paragraph), "Architecture" (Valkey for OTP limits), "Data model" (`users`, `outbox_emails`), Decisions #7, #9, #12.
- `docs/design/data-field-catalog.md` — none (no catalog fields).
- Code: `backend/app/features/auth/models.py` (`User`), `backend/app/core/enums.py` (`UserRole`), `backend/app/core/errors.py`, `backend/app/core/registry.py`, `backend/app/features/notifications/outbox/models.py`, `backend/app/features/applications/models.py` (`Application.lo_id`).

## Acceptance criteria

- [x] AC1 — Auth tests pass; the OTP email arrives in Mailpit (visible via the Mailpit API) and an `outbox_emails` row is written with status `sent`.
- [x] AC2 — A wrong password and an unknown email return the same 401 body; the OTP step is never reached.
- [x] AC3 — An OTP older than 5 minutes is rejected; after 5 wrong attempts the challenge is dead even for the right code.
- [x] AC4 — Login is rate-limited: the 6th attempt for one email inside 15 minutes returns 429 `RATE_LIMITED`.
- [x] AC5 — A successful verify sets an httpOnly, SameSite=Lax `cq_staff_session` cookie; `/me` returns the user; after logout `/me` returns 401.
- [x] AC6 — `require_roles(ADMIN)` returns 403 `FORBIDDEN` for an LO and 200 for an Admin.
- [x] AC7 — `scope_applications`: an LO sees only applications where `lo_id` is theirs; a Manager sees all and can filter by LO.
- [x] AC8 — `seed_dev_users.py` creates the three dev users; running it twice leaves three users.
- [x] AC9 — LO Console login → OTP → home → logout works in the browser against the local API; vitest and react-doctor pass.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | integration + e2e | `features/notifications/email/tests/test_service.py`, `features/auth/staff/tests/test_login_flow.py::test_login_sends_otp_email`; curl + Mailpit API recipe |
| AC2 | API | `test_login_flow.py::test_bad_credentials_same_401` |
| AC3 | unit (Valkey) | `features/auth/otp/tests/test_otp.py::test_expired`, `::test_attempts_exhausted` |
| AC4 | unit + API | `features/auth/otp/tests/test_rate_limit.py`, `test_login_flow.py::test_login_rate_limited` |
| AC5 | API | `test_login_flow.py::test_cookie_flags_me_logout` |
| AC6 | API | `backend/app/core/tests/test_auth_deps.py::test_require_roles` |
| AC7 | DB | `backend/app/core/tests/test_auth_deps.py::test_scope_applications` |
| AC8 | script | `features/auth/users/tests/test_seed_dev_users.py` |
| AC9 | component + manual | `apps/lo-console` vitest (`login` tests), react-doctor, browser screenshot in post-dev.md |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Worktree `.env` points at `cq_dev_p2` / `cq_test_p2` / Valkey db 2 to stay isolated from the P1 session; API runs on port 8012 for e2e.
