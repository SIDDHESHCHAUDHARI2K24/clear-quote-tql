# CQ-014 — Implementation plan

Written by the orchestrator in stages 1–3. Tasks are executed by Sonnet subagents in the item worktree.

## Decisions & questions (stage 1)

Gap check against `system-design.md` ("LO Console → Auth", Decisions #7, #9). No big gaps open.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision (human, 2026-09-25) | Where P2 lands | Integration branch `phase-p2` off `phase-p0-p1`; item branches merge locally. P2 worktrees use `cq_dev_p2`, `cq_test_p2`, Valkey db 2 and API port 8012 so the parallel P1 session is untouched. |
| 2 | Decision (human) | Demo logins before CQ-010 | `create_user` service + `scripts/create_user.py` + idempotent `scripts/seed_dev_users.py` (lo@, manager@, admin@clearquote.test; password `DEMO_STAFF_PASSWORD`). |
| 3 | Decision (human) | UI scope | LO Console login/OTP/home/logout in this item. |
| 4 | Decision | Password hashing | `argon2-cffi` (`PasswordHasher` defaults). Unknown email still runs a dummy verify so timing does not reveal existence. |
| 5 | Decision | OTP storage | Valkey hash `otp:{challenge_id}` = {principal, subject_id, code_sha256, attempts}; TTL 300 s; compare with `hmac.compare_digest`; 5 wrong attempts deletes the key. `challenge_id` = `secrets.token_urlsafe(24)`. |
| 6 | Decision | Rate limits | Fixed window INCR+EXPIRE: `rl:login:email:{email}` 5 / 900 s, `rl:login:ip:{ip}` 20 / 900 s, `rl:otp:{challenge_id}` covered by attempts. Exceeded → 429 `RATE_LIMITED` (new `RateLimitedError`). |
| 7 | Decision | Sessions | Opaque `secrets.token_urlsafe(32)`, Valkey `sess:staff:{sha256(id)}` → user id, sliding TTL 12 h (`STAFF_SESSION_TTL_SECONDS=43200`). Cookie `cq_staff_session`: httpOnly, SameSite=Lax, Path=/, Secure unless `app_env in {local, test}`. No DB sessions table (none in the data model). |
| 8 | Decision | Principal-agnostic modules | `auth/otp` and `auth/sessions` take a `principal: Literal["staff", "borrower"]` argument now so CQ-015 adds borrower without copying. Only staff endpoints ship here. |
| 9 | Decision | Error codes | Add `ForbiddenError` (403 `FORBIDDEN`) and `RateLimitedError` (429 `RATE_LIMITED`) to `core/errors.py`; bad credentials / bad OTP use `AuthenticationError` with message "Invalid email or password" / "Invalid or expired code". |
| 10 | Decision | Email delivery | `notifications/email/service.py::send_email(db, *, to, subject, html, application_id=None)`: insert `outbox_emails` (queued) → send via `aiosmtplib` to `SMTP_HOST:SMTP_PORT` → mark `sent` / `failed` (failure logged, not raised, so OTP issue still returns; the outbox shows it). A module-level `smtp_send` function is the seam tests monkeypatch. |
| 11 | Decision | Manager filter | `scope_applications(stmt, user, lo_id: UUID | None = None)`: LO → `lo_id == user.id` (ignores `lo_id` arg); Manager/Admin → all, or filtered when `lo_id` given. |
| 12 | Decision | Frontend → API cookies | Browser calls the API with `credentials: "include"`; locally console (3010) and API share host `localhost`, so the cookie is visible to Next middleware. Cross-domain on Railway is a CQ-035 follow-up (proxy/rewrites). |
| 13 | Decision | Valkey in tests | Real Valkey (db 2 locally; CI service). A `valkey` fixture in `backend/conftest.py` yields a client and `FLUSHDB`s after each test; the app's Valkey dependency is overridden to it in the `client` fixture. |

## Why

Every console feature needs a signed-in staff user and the LO/Manager scoping rule. OTP email also forces the first real email sender, which CQ-020's send workflow reuses.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Deps / config | `pyproject.toml`, `uv.lock` (argon2-cffi, aiosmtplib), `backend/app/core/config.py`, `.env.example` |
| Core | `backend/app/core/security.py`, `backend/app/core/valkey.py`, `backend/app/core/auth.py`, `backend/app/core/errors.py`, `backend/app/core/registry.py`, `backend/conftest.py` |
| Email | `backend/app/features/notifications/email/{__init__,service}.py`, `tests/` |
| Auth | `backend/app/features/auth/otp/`, `auth/sessions/`, `auth/staff/` (router, schemas, service, tests), `auth/users/` (service, tests) |
| Scripts | `backend/scripts/create_user.py`, `backend/scripts/seed_dev_users.py` |
| API client | `packages/api-client/openapi.json`, generated `src/` |
| LO Console | `apps/lo-console/src/features/auth/*`, `src/app/login/page.tsx`, `src/app/page.tsx`, `src/middleware.ts`, `src/lib/api-client.ts` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Email service (outbox row + SMTP) | — | `features/notifications/email/**` | `email/tests/test_service.py` (AC1) |
| T2 | Security primitives + config + Valkey client/dep + conftest `valkey` fixture + error classes | — | `core/security.py`, `core/valkey.py`, `core/errors.py`, `core/config.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `backend/conftest.py`, `core/tests/test_security.py` | `test_security.py` |
| T3 | OTP + rate-limit + sessions services; staff endpoints; `core/auth.py` deps; registry | T1, T2 | `features/auth/otp/**`, `features/auth/sessions/**`, `features/auth/staff/**`, `core/auth.py`, `core/registry.py`, `core/tests/test_auth_deps.py` | AC2–AC7 |
| T4 | `create_user` service + scripts + dev seed | T2 | `features/auth/users/**`, `backend/scripts/create_user.py`, `backend/scripts/seed_dev_users.py` | AC8 |
| T5 | Export OpenAPI + regenerate api-client | T3 | `packages/api-client/**` | `pnpm --filter @cq/api-client test`, tsc |
| T6 | LO Console login UI | T5 | `apps/lo-console/**` | AC9 |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Primitives, config and error classes every later task imports; disjoint files |
| 2 | T3, T4 | Both need T2; T3 needs T1; disjoint files |
| 3 | T5 | Contract before the frontend |
| 4 | T6 | Consumes the generated client |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `email/tests/test_service.py`; `auth/staff/tests/test_login_flow.py::test_login_sends_otp_email`; e2e curl + Mailpit |
| AC2 | `test_login_flow.py::test_bad_credentials_same_401` |
| AC3 | `auth/otp/tests/test_otp.py::test_expired`, `::test_attempts_exhausted` |
| AC4 | `auth/otp/tests/test_rate_limit.py`; `test_login_flow.py::test_login_rate_limited` |
| AC5 | `test_login_flow.py::test_cookie_flags_me_logout` |
| AC6 | `core/tests/test_auth_deps.py::test_require_roles` |
| AC7 | `core/tests/test_auth_deps.py::test_scope_applications` |
| AC8 | `auth/users/tests/test_seed_dev_users.py` |
| AC9 | lo-console vitest login tests; react-doctor; browser screenshot |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [ ] T5
- [ ] T6
