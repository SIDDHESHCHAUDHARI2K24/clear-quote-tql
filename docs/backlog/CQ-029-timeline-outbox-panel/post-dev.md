# CQ-029 — Post-development notes

## Summary

Four supporting LO Console screens: a per-application activity timeline
(`GET /api/v1/applications/{id}/activity`, an "Activity" drawer button next
to the workspace header's actions menu, exported `ActivityTimeline` for
CQ-026 to reuse), a searchable outbox of every email sent (`GET /api/v1/
outbox`, `GET /api/v1/outbox/{id}`, `GET /api/v1/outbox/{id}/attachments/
{key}`, `/outbox` page with search + type filter and a sandboxed-iframe
detail view), an Admin-only Integration panel over the 9 mock adapters
(`GET`/`PUT /api/v1/admin/integrations`, reusing CQ-009's `failure_toggle`
and `IntegrationCall` log, `/admin/integrations` page with a per-adapter
force-failure toggle and a warning banner), and a read-only Admin Settings
page (`GET /api/v1/admin/settings`, `/admin/settings`). The outbox derives
an email `type` from its subject (no `outbox_emails.type` column, no
migration — plan.md decision 1); the integration panel's "Run stale check
now" button stays hidden behind a logged constant until CQ-030 lands.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `outbox_emails.type` implied by the "type" filter | Derived from `subject` via a substring classifier (`otp`/`borrower_action`/`quote_sent`/`other`), no migration | Simpler, no schema change, single source of truth also drives the SQL filter; logged (plan.md decision 1). CQ-020/24/34's real sends may classify as `other` until the classifier is extended. |
| AC3 "a 403" for cross-scope outbox access | 404 (`NOT_FOUND`) | plan.md E16 (binding, Decision #11): every `application_id`-scoped resource in this codebase 404s for out-of-scope staff, not 403, so an LO can't distinguish "not yours" from "doesn't exist". Logged per the prompt's own instruction to log this difference. |
| AC4 Playwright e2e drives the full "force fail -> reprice -> NeedsAttention -> unforce -> reprice succeeds" round trip | Playwright covers the toggle/banner/admin-only UI mechanics; the full pipeline round trip is a new backend test, `backend/app/workflows/tests/test_admin_forced_pricing_failure.py`, against the real Temporal workflow | Every seeded persona's `application_parties`/housing/etc. rows were written directly by `seed/loader.py::seed_persona` (not through the real `ApplicationPipelineWorkflow`), so `POST .../pipeline/start` against a seeded persona runs `import_application` for the first time from Temporal's point of view and hits an unrelated unique-constraint violation on the already-existing rows — not the forced-failure path this AC is about. CQ-018 (not yet built) is what adds a real "reprice" UI action that skips import. The backend test starts a fresh (never-run) workflow via `client.start_workflow` + the `resume` signal instead, exactly mirroring `applications/router.py`'s own `pipeline/start`/`pipeline/resume` contract. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — Marcus Hale's timeline: import, verification, enrichment, pricing, send, view, borrower action, readable messages, system events visually distinct | ✅ | `backend/app/features/applications/timeline/tests/test_router.py::test_activity_order_marcus_hale` (real seeded pipeline order + messages) and `::test_activity_renders_send_view_borrower_action_and_staff_types` (send/view/borrower-action/staff-actor fixtures — Marcus's own real state is only import/verify/price, plan.md decision 6); `ActivityTimeline.test.tsx` (4 tests, incl. quieter system styling); manual curl against slot 15 confirms Marcus's real 3-event timeline (see "How to test manually") |
| AC2 — outbox lists every email after demo-reset + one send; opens Marcus Hale's quote email (HTML + PDF) | ✅ HTML / ⏳ PDF pending | `test_outbox_list_and_detail`, `OutboxDetail.test.tsx`; manual curl confirms `type=quote_sent` rows (Grace Kim, Luis Romero) after `make demo-reset`. Marcus Hale is seeded `priced`, not `sent` (no persona has both a real quote email *and* a real PDF attachment yet), so the PDF-download half is `pending — re-check after CQ-020` per the E2E_NOTE; covered now by `test_outbox_attachment_stream` (a fixture PDF uploaded via `core/storage`, live MinIO round trip) |
| AC3 — an LO cannot open another LO's outbox email/attachment | ✅ (404, not 403 — logged deviation) | `test_outbox_access` |
| AC4 — force `PricingClient` to fail, re-price → NeedsAttention with the named error; unforce, re-price succeeds | ✅ | `backend/app/workflows/tests/test_admin_forced_pricing_failure.py` (real `ApplicationPipelineWorkflow`, real Temporal test env: forced failure → `needs_attention` + `pipeline.pricing_blocked` payload `"Cannot price: pricing unavailable"` → unforce + `resume` signal → `"priced"`); `e2e/lo-console/integration-panel.spec.ts` (UI toggle + banner half — see deviation above) |
| AC5 — panel shows last latency/result per adapter after a pipeline run; non-admin 403 + no menu entry | ✅ | `test_integrations_summary_shape`, `test_integrations_admin_only`; `e2e/lo-console/shell.spec.ts` (admin sees the link, LO doesn't); `e2e/lo-console/integration-panel.spec.ts` |
| AC6 — settings page values equal the config snapshot on a newly created scenario | ✅ | `test_settings_match_snapshot` (builds a scenario the same way `create_scenario`/`auto_price` do — `ConfigSnapshot()` + the primary down-payment default — and diffs against the settings response) |
| AC7 — react-doctor passes; email iframe runs no scripts | ✅ | react-doctor: 0 errors (4 pre-existing/low-risk warnings, see Test log); `OutboxDetail.test.tsx` asserts `sandbox=""` on the iframe |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` (from repo root) | 515 passed (494 pre-existing + 21 new: 5 timeline, 6 outbox, 5 admin/integrations, 4 admin/settings, 1 Temporal AC4 workflow test) |
| Seed tests | `uv run pytest seed` | 32 passed (unchanged) |
| Lint / types (backend) | `ruff check backend`, `ruff format --check backend`, `mypy backend/app backend/conftest.py backend/tests backend/scripts` | clean |
| Frontend (whole repo) | `pnpm -r run test` | ui 163, lo-console 69 (+9: 4 activity, 4 outbox, 3 admin, +1 WorkspaceHeader Activity-button test, −3 retired stub-page assertions), borrower-portal 95 (untouched), api-client 2 — all passed |
| Lint / types (frontend) | `pnpm -r run lint`, `pnpm -r run typecheck`, `pnpm exec tsc --noEmit` (e2e), `pnpm exec eslint e2e/lo-console/{integration-panel,shell}.spec.ts` | clean |
| Prettier | `pnpm exec prettier --check .` | clean |
| react-doctor | `npx react-doctor -y --blocking error` (lo-console) | 79/100, 0 errors, 4 warnings (see below); exit code 0 |
| e2e (slot 15) | `pnpm exec playwright test e2e/lo-console --workers=1` (API 8115, worker on `cq-s15`, LO console 3115) | 18 passed, incl. the 3 new `integration-panel.spec.ts` tests and the edited `shell.spec.ts` |
| Manual API check | curl against slot 15 after `make demo-reset` | Marcus Hale's `/activity` returns the exact imported→verified→priced sequence with readable messages; `/outbox?type=quote_sent` returns Grace Kim + Luis Romero; `/admin/settings` returns every documented key with sources |

react-doctor warnings (all non-blocking, exit code 0):
- 2 pre-existing (`nextjs-no-client-side-redirect` on the session providers, `no-reset-all-state-on-prop-change` on `WorkspaceProvider`) — unrelated to this item, already noted in the foundation's own post-dev.md.
- 2 new (`no-locale-format-in-render` on `ActivityTimeline.tsx`/`IntegrationsPanel.tsx`/`OutboxList.tsx`): fixed the locale half (pinned `"en-US"`, matching `packages/ui/report/format.ts`'s own convention) but the rule still flags any `toLocale*` call reached from render at all. Assessed as a false positive with high confidence: both components start in a `loading` state and only compute a formatted date *after* a `useEffect`-driven fetch resolves — no `toLocale*` output is ever part of the SSR-rendered/hydrated initial paint, so there is no server/client mismatch to have. Logged rather than suppressed per the tool's own guidance ("confidence requires code context").

## Review findings (stage 6)

Pending — a fresh subagent review runs next (stage 6 of the agent loop, before this PR opens).

## How to test manually

1. `bash scripts/worktree-env.sh 15 && uv run python -m seed.reset` (from repo root; `.env` must already have `SEED_STAFF_PASSWORD`/`SEED_BORROWER_PASSWORD`).
2. Start, in the background: `uv run uvicorn app.main:app --port 8115` (repo root), `uv run python -m app.workflows.worker` (repo root), `pnpm --filter @cq/lo-console exec next dev -p 3115`.
3. Sign in to the LO console (`http://localhost:3115`) as `riley.admin@clearquote-demo.test` → user menu → Integrations: 9 adapter rows, toggle "pricing" → banner appears → untoggle → banner clears. → Settings: every `settings` row + the two down-payment code defaults, sourced.
4. Open an application (e.g. Marcus Hale) → "Activity" button next to the actions menu → drawer shows Imported/Verified/Priced, grouped under "Today", quieter styling.
5. `/outbox` → search "pre-approval", filter type "Quote sent" → Grace Kim / Luis Romero rows → click a row → sandboxed iframe with the HTML.
6. Sign in as `jordan.lee@clearquote-demo.test` (LO) → user menu has no Integrations/Settings link; `/admin/integrations` shows "Not authorized"; that LO's own outbox list never shows another LO's emails.

## Follow-ups

- `outbox/service.py`'s subject-based `type` classifier only knows today's OTP/borrower-action/quote-sent subjects. When CQ-020 (real quote-send emails), CQ-024 (letter emails) and CQ-034 (support emails) land, extend `_TYPE_SUBJECT_RULES` with their real subjects, or those emails will keep showing as `other`.
- AC2's PDF-download half stays `pending — re-check after CQ-020`: re-verify against a real sent persona with a real PDF attachment once CQ-020 merges (H2, phase-p5-p6-plan.md).
- `IntegrationsPanel`'s "Run stale check now" button is gated behind `STALE_CHECK_JOB_AVAILABLE = false` (`features/admin/integrations/api.ts`) — flip it to `true` once CQ-030 merges `POST /admin/jobs/stale-check`.
- react-doctor's `no-locale-format-in-render` on the three new date-formatting call sites: see the Test log note above; no code change needed unless react-doctor's own analysis improves to account for post-mount-only formatting.
