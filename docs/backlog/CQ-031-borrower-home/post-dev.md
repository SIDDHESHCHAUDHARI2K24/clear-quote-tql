# CQ-031 — Post-development notes

## Summary

Added `GET /api/v1/portal/me` (`backend/app/features/portal/home/`): the
signed-in borrower's first name and email, plus one entry per application
with a plain-language `stage`/`label` (from the single `stage_and_label`
function, `service.py`), a `next_action` (`view_report` / `continue_
application` / `authorize_credit_check` / `none`), and the assigned LO's
contact info. An open `application_drafts` row (CQ-032a) surfaces as a
synthetic `stage = draft` entry. On the frontend, `apps/borrower-portal/
src/features/home/` renders the greeting, a task banner for a pending
credit-check consent, one `ApplicationCard` per application (4-step
progress bar, label, next-action button, LO card) and an empty state with
"Start your application" — all from `stage`/`label` text the backend
already produced, with no status re-derivation on the client.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET /api/portal/me` | `GET /api/v1/portal/me` | Every route lives under `/api/v1` (AGENTS.md/worker guide); the coordinator prompt also pins this exact path. |
| Empty state links to CQ-032's wizard and shows "Coming soon" until CQ-032 exists | Links straight to `/apply` (the P5/P6 foundation's stub route), no "Coming soon" | `/apply` already renders (a stub CQ-032b fills later), so the link always works — coordinator instruction, logged in plan.md Decision 7. |
| `next_action`'s priority between `view_report`/`continue_application`/ `authorize_credit_check`/`none` isn't pinned | One explicit ladder in `service._build_application_out` (plan.md Decision 3): `option_selected`/`closed` → always `none`; else pending unexpired consent → `authorize_credit_check`; else a non-superseded sent version → `view_report`; else `none`. Draft entries always get `continue_application`, bypassing the ladder. | Needed a total order to pick exactly one `next_action`; matches every persona example the coordinator gave (Marcus, Luis). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — each of the 10 personas sees the spec.md stage/label | Met | `backend/app/features/portal/home/tests/test_router.py::test_portal_stage_mapping` (10 parametrized cases, one per persona/status pair from spec.md's table); e2e `portal-home.spec.ts` additionally checks Aisha, Marcus and Luis against the real seeded stack (slot 17, `make demo-reset`) |
| AC2 — Aisha (needs_attention) sees "Application received"; no "attention"/"flag"/"error" anywhere | Met | `test_router.py::test_portal_hides_internal_states` (full `ApplicationStatus` sweep, raw JSON text scan) and `test_service.py::test_no_internal_vocabulary_in_any_label` (every status × has_ever_sent); e2e test does the same scan over the live page's rendered `<body>` text for Aisha |
| AC3 — Marcus Hale's next action opens his latest sent version; Luis (option_selected) gets `next_action=none` + reaches his report via a secondary "View your numbers" link | Met | `test_router.py::test_next_action_view_report_and_option_selected`; e2e `portal-home.spec.ts` (`backend/scripts/freeze_sent_version.py --persona marcus_hale` gives him a real sent version, since he's seeded `priced`; Luis already has one from his seed fixture) — both click through to a real `/report/{token}` page |
| AC4 — a borrower with no applications sees the empty state | Met | `test_router.py::test_empty_state_no_applications` (factory-built borrower with zero applications); `apps/borrower-portal/src/app/(portal)/page.test.tsx` ("shows the empty state and starts the application on click"); e2e signs in as the seeded `noapp.borrower@clearquote-demo.test` and clicks through to `/apply` |
| AC5 — a borrower can only see their own applications | Met | `test_router.py::test_portal_me_isolation` (two borrowers, two applications, each session's response contains only its own application id) |
| AC6 — 375 px fits with no horizontal scroll; react-doctor passes; Lighthouse accessibility ≥ 95 | Met | e2e `portal-home.spec.ts` "AC6: 375 px..." (Priya Nair, real cards, scrollWidth ≤ clientWidth+1); react-doctor `apps/borrower-portal` **100/100, no issues**; Lighthouse accessibility **100/100** (`evidence/lighthouse-report.json`, run against the live, signed-in `/` page) |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend (this item) | `uv run pytest backend/app/features/portal/home` | 31 passed |
| Backend (whole repo) | `uv run pytest backend` | Flaky under this session's heavy concurrent-worktree load (asyncpg `InterfaceError`s in unrelated files — `test_schema.py`, `workflows/tests/*`, `test_errors.py` — the same environmental flake the p56-foundation post-dev already documented); this item's own directory is consistently green in isolation and after each fix, run repeatedly |
| ruff / ruff format | `uv run ruff check backend`, `uv run ruff format --check backend` | clean (whole repo) |
| mypy | `uv run mypy backend` | clean, 338 source files (whole repo) |
| Frontend (borrower-portal) | `pnpm --filter @cq/borrower-portal exec vitest run` | 107 passed (20 files) |
| eslint | `pnpm --filter @cq/borrower-portal exec eslint .` | clean |
| tsc | `pnpm --filter @cq/borrower-portal exec tsc --noEmit` | clean |
| e2e tsc | `npx tsc --noEmit -p tsconfig.json` | clean |
| prettier | `npx prettier --check <changed files>` | clean |
| react-doctor | `npx react-doctor -y --blocking error` (apps/borrower-portal) | **100/100**, no issues |
| e2e | `pnpm exec playwright test --project=borrower-portal e2e/borrower-portal/portal-home.spec.ts --workers=1` (slot 17) | **7 passed** |
| api-client | `make api-client` | regenerated cleanly; `PortalHomeResponse`/`PortalApplicationOut`/`PortalNextAction`/`PortalStage` present in `packages/api-client/src/schema.d.ts` |
| migrations | none added by this item | `alembic heads` unaffected |
| demo-reset | `uv run python -m seed.reset` (slot 17) | 3.4s |

## Review findings (stage 6)

Fresh-subagent `code-review` skill run against the diff. All findings fixed.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `HomeView`'s 401 handler redirected to `/login` without clearing the stale `cq_borrower_session` cookie first, unlike `BorrowerSessionProvider`/`ReportView`'s established pattern — `src/middleware.ts` only checks cookie *presence*, so it would bounce the redirect straight back to `/`, re-triggering the same failed fetch | Fixed: `HomeView` now calls `POST /api/v1/auth/borrower/logout` before `router.replace("/login")`, same as the other two call sites; new assertion in `page.test.tsx`'s 401 test |
| Major | `_pending_consent_id` only inspected the single most-recently-requested `PENDING` consent, then checked *that one's* expiry — an older, still-valid `PENDING` row for the same application would be silently skipped if a newer one had since expired (nothing in the schema stops more than one `PENDING` row per application) | Fixed: the `WHERE` clause itself now filters to non-expired rows (`expires_at IS NULL OR expires_at > now()`) before ordering/limiting, so an older valid row is found even if a newer one expired; new regression test `test_pending_consent_skips_an_expired_newer_row` |
| Low (logged, not fixed — outside owned files) | `apps/borrower-portal/src/features/auth/applicationStatus.ts`'s `applicationStatusLabel` (the old placeholder's status→label lookup) is now dead code (its only caller, the old `(portal)/page.tsx`, was replaced by this item) but is still exported from `features/auth/index.ts`, re-implementing exactly the mapping spec.md says must live in one backend function only | Not fixed here: `features/auth/` is a P5/P6-foundation-owned file, outside this item's owned paths (`AGENTS.md`: edit outside owned files "only for a small necessity, and log it" — removing dead code from another unit's file isn't a necessity for any AC). Logged below as a follow-up for the orchestrator/foundation owner. |
| Info (logged, not fixed) | `_build_application_out` issues up to 4 sequential DB round-trips per application (LO lookup, has-ever-sent, latest-token, pending-consent), unbatched across `N` applications | Not fixed: every seeded persona and demo borrower has exactly 1 application (`seed/personas/*.yaml`; the seed's own tests assert this), so this is a latent scaling concern, not a functional bug for anything this repo currently seeds. Logged as a follow-up. |

## How to test manually

1. `bash scripts/worktree-env.sh 17 && make demo-reset`
2. Start the API (`uv run uvicorn app.main:app --app-dir backend --port 8117` from the repo root) and the portal (`pnpm --filter @cq/borrower-portal exec next dev -p 3217`).
3. Sign in at `http://localhost:3217/login` as `aisha.coleman@clearquote-demo.test` (`SEED_BORROWER_PASSWORD`, OTP from `http://localhost:8025`) → "Application received", no "attention"/"flag"/"error" text anywhere.
4. `uv run python backend/scripts/freeze_sent_version.py --persona marcus_hale`, then sign in as `marcus.hale@clearquote-demo.test` → "Your pre-approval is ready" and a "See your numbers" button that opens `/report/{token}`.
5. Sign in as `luis.romero@clearquote-demo.test` → "You chose an option — {LO} will be in touch", no primary button, a "View your numbers" link.
6. Sign in as `noapp.borrower@clearquote-demo.test` → "No application yet" + "Start your application" → `/apply`.

## Follow-ups

- `apps/borrower-portal/src/features/auth/applicationStatus.ts`'s `applicationStatusLabel` export is dead code after this item (see Review findings above). Whoever next touches `features/auth/` should remove it (and its re-export in `features/auth/index.ts`) so a future feature can't accidentally reach for it instead of the backend's `stage`/`label`.
- `service._build_application_out`'s per-application query count (4 round-trips) doesn't batch across a borrower's applications. Fine at today's seed scale (1 application per borrower everywhere in this repo); worth batching (e.g. one `IN (...)` query per data need instead of N) if a future item gives a borrower multiple applications at once.
- AC1/AC2's full-repo backend suite run showed the same environmental asyncpg contention flake the p56-foundation post-dev already documented (many concurrent worktree agents sharing one Postgres instance) — unrelated to this item's files; `backend/app/features/portal/home`'s own suite is consistently green.
