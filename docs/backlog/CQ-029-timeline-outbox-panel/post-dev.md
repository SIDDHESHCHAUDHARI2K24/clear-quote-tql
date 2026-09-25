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
force-failure toggle, a warning banner, and a "Run stale check now" button
that calls CQ-030's `POST /api/v1/admin/jobs/stale-check` and shows the
returned counts), and a read-only Admin Settings page (`GET /api/v1/admin/
settings`, `/admin/settings`). The outbox derives an email `type` from its
subject (no `outbox_emails.type` column, no migration — plan.md decision 1).

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
| Backend tests | `uv run pytest backend` (from repo root, after merging `origin/phase-p5-p6`) | 622 passed (515 CQ-029 + CQ-027/CQ-030/CQ-031/CQ-034 merged in) — first full run under heavy concurrent-agent load on shared Postgres flaked 3 (`applications/listing` tests, spurious 401s from a leaked, hour-old `idle in transaction` savepoint on the shared slot-15 DB from a since-exited concurrent session); killed the stuck backend and reran clean twice, confirming pure contention, not a regression |
| Seed tests | `uv run pytest seed` | 32 passed (unchanged) |
| Lint / types (backend) | `ruff check backend`, `ruff format --check backend`, `mypy backend/app backend/conftest.py backend/tests backend/scripts` | clean |
| Frontend (whole repo) | `pnpm -r run test` | ui 163, lo-console 104 (+9 CQ-029: 4 activity, 4 outbox, 3 admin incl. 2 new stale-check tests, +1 WorkspaceHeader Activity-button test, −3 retired stub-page assertions, plus CQ-027/030/031/034's own new tests), borrower-portal 113 (+18, CQ-031/034), api-client 2 — 382 total, all passed |
| Lint / types (frontend) | `pnpm -r run lint`, `pnpm -r run typecheck`, `pnpm exec tsc --noEmit` (e2e), `pnpm exec eslint e2e/lo-console/{integration-panel,shell}.spec.ts` | clean |
| Prettier | `pnpm exec prettier --check .` | clean |
| react-doctor | `npx react-doctor -y --blocking error` (lo-console) | 79/100, 0 errors, 4 warnings (see below); exit code 0 |
| e2e (slot 15, full lo-console suite, re-run after the `phase-p5-p6` merge) | `make demo-reset`; API on 8115, worker on `cq-s15`, LO console 3115, borrower portal 3215 (global-setup signs in shared borrower personas regardless of project scope); `pnpm exec playwright test e2e/lo-console --workers=1` | 24 passed (`applications-list.spec.ts` ×5, `integration-panel.spec.ts` ×4 incl. the new stale-check test, `report-gallery.spec.ts` ×2, `shell.spec.ts` ×4, `smoke.spec.ts` ×1, `staff-login.spec.ts` ×1, `workspace.spec.ts` ×7) in 1.2m; screenshots saved to `evidence/` (`admin-integrations-forced.png`, `admin-integrations-stale-check.png`, `admin-settings.png`) |
| Manual API check | curl against slot 15 after `make demo-reset` | Marcus Hale's `/activity` returns the exact imported→verified→priced sequence with readable messages; `/outbox?type=quote_sent` returns Grace Kim + Luis Romero; `/admin/settings` returns every documented key with sources |

react-doctor warnings (all non-blocking, exit code 0):
- 2 pre-existing (`nextjs-no-client-side-redirect` on the session providers, `no-reset-all-state-on-prop-change` on `WorkspaceProvider`) — unrelated to this item, already noted in the foundation's own post-dev.md.
- 2 new (`no-locale-format-in-render` on `ActivityTimeline.tsx`/`IntegrationsPanel.tsx`/`OutboxList.tsx`): fixed the locale half (pinned `"en-US"`, matching `packages/ui/report/format.ts`'s own convention) but the rule still flags any `toLocale*` call reached from render at all. Assessed as a false positive with high confidence: both components start in a `loading` state and only compute a formatted date *after* a `useEffect`-driven fetch resolves — no `toLocale*` output is ever part of the SSR-rendered/hydrated initial paint, so there is no server/client mismatch to have. Logged rather than suppressed per the tool's own guidance ("confidence requires code context").

## Review findings (stage 6)

A fresh subagent (no context from writing the code) reviewed `git diff HEAD` vs `origin/phase-p5-p6`. 10 findings; 9 fixed, 1 accepted as a deliberate, already-logged tradeoff. No critical/major finding is open.

| # | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | Major | `ActivityTimeline.tsx` bucketed days by UTC (`toISOString().slice(0,10)`) instead of the viewer's local calendar date — a late-evening US event could land under tomorrow's heading | Fixed: `localDateKey()`; regression test `ActivityTimeline.test.tsx` pinned `TZ=America/New_York` + `vi.setSystemTime`, verified failing on the old code and passing on the new |
| 2 | Major | `IntegrationsPanel.tsx`'s `toggle()` had no try/catch/finally — a rejected promise (network drop, not just an `{error}` body) left the checkbox stuck disabled with the optimistic update never reverted | Fixed: try/catch/finally; regression test asserts the checkbox un-disables and reverts on a rejected PUT |
| 3 | Major | Outbox attachment route called sync `stream_object()` directly in the handler, blocking the event loop for the whole GET | Fixed: `astream_object()`, pulling the first chunk eagerly so a missing key still 404s cleanly instead of aborting mid-stream after headers are sent; new test `test_outbox_attachment_stream_404s_cleanly_for_a_missing_object` |
| 4 | Major | Outbox free-text search (`q`) built an unescaped `ILIKE` pattern — a literal `%`/`_` in the search text acted as a SQL wildcard | Fixed: `_escape_like()` + `escape=` kwarg; regression test `test_outbox_search_escapes_like_wildcards` |
| 5 | Minor | `list_outbox` selected the whole `OutboxEmail` entity (including `html`) per row just to discard it | Fixed: `_LIST_COLUMNS` + `_row_to_out()` selects only what `OutboxEmailRow` needs |
| 6 | Major | `admin/settings/service.py` hand-copied the down-payment default literals instead of importing `pricing/scenarios/service.py`'s real constants — two independently-maintained copies of the same literal | Fixed: imports `_DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT` directly (cross-package private-name import — flagged in "Follow-ups" below for a human call on whether a public alias is preferred) |
| 7 | Minor | `timeline/service.py`'s `_payload_summary` sliced "first 5" keys from a JSONB payload, which doesn't preserve insertion order | Fixed: `sorted(payload.items())[:5]` for determinism |
| 8 | Major | `admin/integrations/service.py`'s `list_integration_status` made ~27 sequential DB/Valkey round trips (2 queries × 9 adapters + 9 sequential Valkey GETs) | Fixed: one `DISTINCT ON` query for the latest call per adapter, one `GROUP BY` query for hourly counts, `asyncio.gather` over the 9 Valkey `is_forced_to_fail` calls; also fixed a `SADeprecationWarning` this surfaced (SQLAlchemy 2.1's `distinct_on` API) |
| 9 | Minor | `OutboxList.tsx` fired a full `GET /outbox` on every keystroke in the search box | Fixed: 300ms debounce (`qInput` shown immediately, debounced `q` drives the fetch); regression test asserts exactly one fetch for a whole typed string |
| 10 | Minor | Outbox `type` is derived from subject-text pattern matching rather than a real `outbox_emails.type` column | **Accepted** — already a logged, deliberate tradeoff (plan.md decision 1: no migration, single classifier also drives the SQL filter; follow-ups note extending `_TYPE_SUBJECT_RULES` as CQ-020/24/34 land) |

Two items the reviewer listed separately as "not in the top 10, for your judgement" (not scored/counted above):
- Outbox scoping re-implements the shape of `core/auth.py`'s `scope_applications` rather than calling it directly — accepted, minor (outbox rows scope through `applications.lo_id`, not a direct FK `scope_applications` expects; revisit if a third caller needs the same scoping).
- `IntegrationsPanel`'s "Run stale check now" button needing a manual flip once CQ-030 merged — resolved in this session (see "Remaining work" below): CQ-030 has merged, the button is un-hidden and wired to `POST /api/v1/admin/jobs/stale-check`, with a new Vitest suite and Playwright coverage.

## How to test manually

1. `bash scripts/worktree-env.sh 15 && uv run python -m seed.reset` (from repo root; `.env` must already have `SEED_STAFF_PASSWORD`/`SEED_BORROWER_PASSWORD`).
2. Start, in the background: `uv run uvicorn app.main:app --port 8115` (repo root), `uv run python -m app.workflows.worker` (repo root), `pnpm --filter @cq/lo-console exec next dev -p 3115`.
3. Sign in to the LO console (`http://localhost:3115`) as `riley.admin@clearquote-demo.test` → user menu → Integrations: 9 adapter rows, toggle "pricing" → banner appears → untoggle → banner clears; "Run stale check now" → shows "Nothing was stale…" or the marked/expired/flagged counts. → Settings: every `settings` row + the two down-payment code defaults, sourced.
4. Open an application (e.g. Marcus Hale) → "Activity" button next to the actions menu → drawer shows Imported/Verified/Priced, grouped under "Today", quieter styling.
5. `/outbox` → search "pre-approval", filter type "Quote sent" → Grace Kim / Luis Romero rows → click a row → sandboxed iframe with the HTML.
6. Sign in as `jordan.lee@clearquote-demo.test` (LO) → user menu has no Integrations/Settings link; `/admin/integrations` shows "Not authorized"; that LO's own outbox list never shows another LO's emails.

## Follow-ups

- `outbox/service.py`'s subject-based `type` classifier only knows today's OTP/borrower-action/quote-sent subjects. When CQ-020 (real quote-send emails), CQ-024 (letter emails) and CQ-034 (support emails) land, extend `_TYPE_SUBJECT_RULES` with their real subjects, or those emails will keep showing as `other`.
- AC2's PDF-download half stays `pending — re-check after CQ-020`: re-verify against a real sent persona with a real PDF attachment once CQ-020 merges (H2, phase-p5-p6-plan.md).
- react-doctor's `no-locale-format-in-render` on the three new date-formatting call sites: see the Test log note above; no code change needed unless react-doctor's own analysis improves to account for post-mount-only formatting.
- `admin/settings/service.py` imports two underscore-prefixed ("private") names from `pricing/scenarios/service.py` across a feature-package boundary (review finding 6). Deliberate (single source of truth), and ruff's enabled rule set (`E,F,I,UP,B`) doesn't flag it, but worth a second pair of eyes in case a public alias is preferred.
