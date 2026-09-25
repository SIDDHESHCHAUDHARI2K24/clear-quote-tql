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
- ~~`admin/settings/service.py` imports two underscore-prefixed ("private") names from `pricing/scenarios/service.py` across a feature-package boundary (review finding 6).~~ Resolved in Review round 1: `pricing/scenarios/service.py` now exports public `DEFAULT_DOWN_PAYMENT_PRIMARY`/`DEFAULT_DOWN_PAYMENT_INVESTMENT` aliases; `admin/settings/service.py` imports those instead.

## Review round 1 (orchestrator review)

A fresh fix worker merged `origin/phase-p5-p6` into this branch and addressed every stage-6 finding below (M2 plus minors 1-8 and the two nits). Commit `78a1ae8` ("CQ-029: fix: merge phase-p5-p6 and address stage-6 review findings").

| # | Finding | Resolution |
| --- | --- | --- |
| M2 | Timeline showed generic text and the wrong actor for event types written outside `timeline/service.py` (CQ-028a's `applications/sections/events.py`, CQ-030's stale events) | `describe_event` now returns `payload["message"]` (a non-empty `str`) before the humanized fallback, plus explicit cases for `application.submitted`/`application.assigned`/`support.requested`; `_resolve_actor` treats `actor == "borrower"` as a borrower actor; `application.submitted`/`support.requested` added to `_BORROWER_EVENT_TYPES`; `activity/icons.tsx` maps `field.*`, `flag.*`, `credit.*`, `support.*`, `row.*`, `ssn.*`, `document.*`, `property.*`, `application.stale`, `application.repriced_from_stale` to real icons. New tests: a 31-case parametrised backend test (`test_every_written_event_type_has_a_readable_message_and_correct_actor`) over every `ActivityEvent(` write site in the base, plus a frontend `icons.test.tsx` |
| Minor 1 | Per-row `db.get(User, ...)` for each staff actor | `list_activity` batches one `select(User.id, User.full_name).where(User.id.in_(...))` for the page's staff actors |
| Minor 2 | AC6 test hand-assembled a `Scenario` row instead of exercising the real service | `test_settings_match_snapshot_primary`/`_investment` now build the scenario through the real `create_default_scenarios` call (mirroring `pricing/scenarios/tests/test_default_scenarios_{primary,investment}.py`'s own fixtures) and diff the settings page against the persisted `config_snapshot`/`inputs.down_payment_pct`, for both occupancies |
| Minor 3 | Two independently-hardcoded down-payment literals across a package boundary | `pricing/scenarios/service.py` exports public `DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT`; `admin/settings/service.py` imports the public names |
| Minor 4 | No test for a key that's a real object in storage but not on *this* email's `attachment_keys` | `test_outbox_attachment_key_not_on_this_email_404s`; `test_outbox_attachment_content_disposition` added too |
| Minor 5 | Outbox `type` query param was untyped `str` | `schemas.EmailType` (`Literal["otp", "borrower_action", "quote_sent", "other"]`); router/service param typed as `EmailType \| None`; unknown value is a 422 (`test_outbox_unknown_type_is_422`); api-client regenerated (`packages/api-client/src/schema.d.ts`'s `type` query param is now the literal union); the lo-console `api.ts` narrows to it at the one call site |
| Minor 6 | `IntegrationsPanel.tsx`: silent revert on toggle failure, single-adapter pending slot, uncaught `load()` rejection | Visible `toggleError` alert; `pendingAdapters: Set<string>`; `.catch` on `load()` into the error state with a Retry button; 3 new Vitest cases (visible alert, independent pending tracking, Retry re-fetch) |
| Minor 7 | `test_admin_forced_pricing_failure.py`'s direct `db_session` reads didn't hold `db_lock`, risking asyncpg's "another operation is in progress" against the shared per-test worker connection | Both reads (`blocked_event` query, `db_session.refresh`) wrapped in `async with db_lock:` |
| Minor 8 | The Outbox page never read `?application_id=` | `page.tsx` reads it from `useSearchParams()` and passes it to `OutboxList`, which passes it to `fetchOutboxList`; `open()`/`close()` now preserve it across the `email_id` drawer navigation too; new Vitest test (`OutboxList.test.tsx`) and backend test (`test_outbox_application_id_filter`) |
| Nit | `API_BASE_URL` defined in two places | Exported from `lib/api-client.ts` alone; `features/outbox/api.ts` re-exports it |
| Nit | Plain `filename=` only | `Content-Disposition` now carries both `filename="..."` (ASCII-folded) and an RFC 5987 `filename*=UTF-8''...` |

**Verification on the merged tree:**

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | 788 passed |
| Seed tests | `uv run pytest seed` | 32 passed |
| Lint/types (backend) | `ruff check backend`, `ruff format --check backend`, `mypy backend/app backend/conftest.py backend/tests backend/scripts` | clean |
| Frontend tests | `pnpm -r run test` | api-client 2, ui 163, lo-console 126 (+22 vs. pre-fix: icons.test.tsx ×19, IntegrationsPanel ×3, OutboxList ×1, minus double-counting overlaps), borrower-portal 113 — all passed |
| Lint/types (frontend) | `pnpm -r run lint`, `pnpm -r run typecheck` | clean |
| Prettier | `pnpm exec prettier --check .` | clean (2 pre-existing-from-merge files reformatted: `apps/lo-console/src/app/(staff)/page.test.tsx`, `IntegrationsPanel.tsx`) |
| react-doctor | `npx react-doctor -y --blocking error` (lo-console) | 81/100, 0 errors, 4 warnings (2 pre-existing unrelated + 2 already-logged `no-locale-format-in-render` false positives — `ActivityTimeline.tsx`, `IntegrationsPanel.tsx`); exit 0 |
| e2e (slot 15, full `e2e/lo-console`, `--workers=1`, after `make demo-reset`, API+worker+lo-console+borrower-portal running) | `pnpm exec playwright test e2e/lo-console --workers=1` | CQ-029's own specs are fully green across every run: `shell.spec.ts` 4/4, `integration-panel.spec.ts` 4/4. Two **pre-existing, out-of-scope** failures surfaced on the merged tree, confirmed unrelated to this fix round (see below) |

**Out-of-scope findings surfaced by the merged-tree e2e run** (not fixed here — neither file is CQ-029's, and both reproduce independent of every change in this commit):

1. `e2e/lo-console/dashboard-tiles.spec.ts`'s test *"resolving a flag directly in the DB removes the application from the attention list (AC5 — pending, re-check once CQ-028 exists)"* (CQ-025's own file) directly `UPDATE`s Aisha Coleman's `flags`/`applications` rows in Postgres as a stand-in for CQ-028's real re-verify endpoint. CQ-028 has since merged into `phase-p5-p6`, so that workaround is now stale — and because `test.describe.configure({ mode: "serial" })` only serializes within one spec *file*, Playwright still runs every file in one shared DB/worker in filename order, so this direct DB mutation leaks into `e2e/lo-console/workspace.spec.ts`'s *"AC4: Aisha Coleman (missing occupancy) opens on her first flagged tab with a red badge"* (CQ-016/028's file), which runs later in the same suite against the now-already-resolved persona and times out waiting for a redirect to `/pricing` that no longer happens. Confirmed by running `workspace.spec.ts` alone after a fresh `make demo-reset` (no `dashboard-tiles.spec.ts` beforehand): that same Aisha Coleman test passes cleanly. Needs a CQ-025 fix: point that test at the real re-verify flow (or otherwise stop mutating a shared persona's DB row) now that CQ-028 exists, matching the test's own title.
2. `e2e/lo-console/applications-list.spec.ts`'s *"a status filter updates the URL and survives reload and back navigation"* (CQ-027's own file) hit a Playwright strict-mode violation: `getByRole('button', { name: /^Status/ })` now matches two buttons (a filter-bar `Select` trigger and a sortable-column header button), both labeled "Status". Pre-existing ambiguity in CQ-027's own markup/locator, not touched by this branch.
3. `e2e/lo-console/workspace.spec.ts`'s *"AC7: the pipeline banner shows the running stage while the workflow is active"* is timing-sensitive against `POST .../pipeline/start` for an already-`priced` persona (Marcus Hale) and intermittently times out waiting for `last_pipeline_stage` to flip non-null within its own 8s poll before the page assertion's 10s timeout; observed once in isolation with the worker confirmed running. Not caused by this branch (no CQ-029 file touches the pipeline/start contract or Marcus Hale's persona); flagged for whoever owns `workspace.spec.ts` (CQ-016/028) to look at re-run stability.

Backend/frontend unit and integration tests, ruff, mypy, eslint, tsc, prettier and react-doctor are all green on the merged tree. `make demo-reset` completes in ~2-8s across every run in this session.

## Review round 2 (fresh-subagent code review, `/code-review --effort low`)

A fresh code-review subagent (no context from writing the fix) reviewed `bb75632..HEAD` (the 20 files named in Review round 1's table). It found 0 new correctness bugs and 10 cleanup/altitude findings; the reviewer's own top-3 picks (items 1, 2 and 5 below) were acted on plus three more (3, 4, 9); the rest are logged as follow-ups. Commit `<pending — see the push below>`.

| # | Finding | Resolution |
| --- | --- | --- |
| 1 | `outbox/router.py`'s ASCII `Content-Disposition` fallback didn't escape an embedded `"`/`\` in the filename, so `filename="a"b.pdf"` ends its quoted-string early | Fixed: escapes `\` then `"`; regression test `test_outbox_attachment_content_disposition_escapes_embedded_quotes` |
| 2 | Minor 3 ("single source of truth" for the down-payment defaults) was incomplete: `pricing/scenarios/ob_request.py` kept its own private `_DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT` copy and used it for real Optimal Blue pricing requests | Fixed: `ob_request.py` (the lower-level module `scenarios/service.py` already imports from, so this is the non-circular direction) now defines the public `DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT`; `scenarios/service.py` imports (re-exports) them instead of redefining; `admin/settings/service.py`'s import is unchanged (still from `scenarios.service`) |
| 3 | `activity/icons.tsx`'s `categoryForEventType` picked the first array entry whose prefix matched -- a future specific entry appended after a broader prefix (e.g. `application.`) already in the array would be silently shadowed by it | Fixed: longest-matching-prefix wins, not array position; regression test `prefers the longest matching prefix over array order` |
| 4 | `ActivityEvent.actor`'s docstring said "a user id or `system`", omitting the literal `"borrower"` this fix round taught `_resolve_actor` to treat specially | Fixed: docstring updated |
| 5 | *(reviewer's own judgement item, not in their top-3)* — logged as a follow-up, not fixed: `timeline/service.py`'s per-writer knowledge (the `describe_event` if-chain, `_BORROWER_EVENT_TYPES`) plus the frontend `TYPE_PREFIX_CATEGORY` plus the test's `_WRITTEN_EVENTS` list are three hand-synced lists; a future event-type writer that skips `payload["message"]` or a frontend entry degrades silently (generic text, bullet icon) rather than failing a test. A real fix (one event-type registry writers must use, plus a test that scans every `ActivityEvent(type=...)` literal in the codebase against it) is a bigger, cross-cutting change better scoped as its own item |
| 6 | `pricing/scenarios/ob_request.py`'s `_ACTOR_BORROWER`-style duplication concern doesn't apply here (that's `portal/apply/service.py`'s own constant) — logged as a follow-up: `timeline/service.py`'s `_ACTOR_BORROWER = "borrower"` and `portal/apply/service.py`'s own `_ACTOR_BORROWER = "borrower"` are two independently-maintained copies of the same magic string. A shared constant would need a small shared module both packages can import without creating a cycle; deferred rather than touching `portal/apply/service.py` (another item's owned file) in this fix round |
| 7 | `outbox/page.tsx`'s `open()`/`close()` each rebuilt `URLSearchParams` from scratch, keeping only `application_id` -- any other future query param (e.g. a URL-driven `?type=`) would be dropped on every drawer open/close | Fixed: both now seed from `searchParams.toString()` (matching `DashboardPage.tsx`'s `handleLoChange`) and only set/delete the one key they own |
| 8 | `IntegrationsPanel.tsx`'s `toggle()` has the same revert-and-`setToggleError` logic duplicated between the `{error}`-body branch and the `catch` block | Logged as a follow-up (cleanup only, not a bug): consolidating to "the error branch throws, one `catch` handles both" is a reasonable follow-up but reorders the function's control flow for a working code path with full test coverage already; deferred to keep this round's diff focused on the failures and gaps flagged |
| 9 | `timeline/service.py`'s `_resolve_actor` had two differently-worded branches (`event.actor == _ACTOR_SYSTEM` explicitly, then `_staff_actor_id(event) is None`) saying the same thing, since `_staff_actor_id` already returns `None` for the system actor | Fixed: dropped the redundant explicit branch (verified equivalent: `_staff_actor_id` returns `None` for `_ACTOR_SYSTEM`/`_ACTOR_BORROWER`/a non-UUID string, and `None` already means "system") |
| 10 | `admin/settings/tests/test_router.py`'s `_seed_conventional_curve`/`_seed_dscr_curve` copy the same 5-offset loop and price formula | Logged as a follow-up (test-only cleanup): a parameterised `_seed_rate_curve(...)` would remove the duplication; deferred, no behavior risk |

**Re-verification after round 2:** `uv run pytest backend` 789 passed (+1: the new Content-Disposition escaping test); `ruff check backend` / `ruff format --check backend` / `mypy` clean; `pnpm -r run test` — lo-console 146 passed (+20: `icons.test.tsx` gained the longest-prefix regression test); `pnpm -r run lint` / `pnpm -r run typecheck` / `pnpm exec prettier --check .` clean; `react-doctor` unchanged (81/100, 0 errors, same 4 pre-existing/already-logged warnings, exit 0).
