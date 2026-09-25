# Phase P5/P6 verification

Status: **superseded by the main→phase-p5-p6 merge** (see
`docs/backlog/phase-p5-p6-main-merge-plan.md` on `origin/phase-p5-p6`). P3/P4
landed on `main` (PR #33) after this branch was cut from `phase-p5-p6`, so
this doc's (c) section — written when this branch could only see
`phase-p5-p6` in isolation — is out of date: it is kept below as a record of
what was actually found and how, with a note pointing at the merge plan's
U1–U3 reconciliation units, which re-verify each item against the merged
code. Everything else below ((a), (b), (d), (e)) is this session's real,
final result and does not need to be redone; U4 (post-merge phase
verification) picks up from here.

## (a) Suite results

Setup used: slot 28 (API 8128, LO 3128, portal 3228), branch
`p56-phase-verification` (local `p56-verify-2`) off `origin/phase-p5-p6`
merged with `origin/p56-phase-verification` @ `dd974bc`.

### Fixes landed across this branch's two sessions

From the prior session (handed off at `dd974bc`, carried forward unchanged):

1. **`e2e/borrower-portal/shell.spec.ts`** — the stale stub-era assertions
   were replaced: `/support` now asserts the real `h1` "Get in touch"
   (matches `support.spec.ts`); `/apply` still asserts `h1` "Apply"
   (unchanged, still correct); `/tasks/credit-check/{unknown-uuid}` now
   asserts `h1` "Request not found" (`ConsentStates.tsx`'s `ConsentNotFound`,
   since an all-zero UUID 404s) instead of the old "Credit check"/"Built in
   CQ-033" stub text.
2. **`e2e/borrower-portal/portal-home.spec.ts:166`** — same stale-stub class
   of bug: asserted `h1` "Credit check" for a *real, pending* consent; the
   real page (`ConsentForm.tsx`) renders "Authorize a credit check". Fixed.
3. **`e2e/helpers/db.ts`** — added `queryRows()`, a typed read-query export
   over the existing `pg` pool, for the P5 milestone spec's independent SQL
   recomputation of the dashboard tile counts.
4. **`playwright.config.ts`** — the `cross-app` project's `testMatch` was a
   single hardcoded filename; widened to also match `cross-app/*.spec.ts`
   so the two new milestone specs run.
5. **`e2e/cross-app/p5-milestone.spec.ts`** (new) — Manager dashboard tiles
   vs. SQL-computed counts, then an LO resolves Aisha Coleman's
   missing-occupancy flag and she reaches Priced and leaves "Needs your
   attention" (restored in `afterAll`).
6. **`e2e/cross-app/p6-milestone.spec.ts`** (new) — a new borrower signs up
   (Mailpit OTP), completes the apply wizard, submits, reaches Intake, and
   auto-prices with no LO action; the LO console (a second browser context,
   signed in as the Manager) shows the same application Priced.
7. **`backend/scripts/restart_pipeline.py`** (new, test-only) — see "Task 1
   decision" below; used only by `p5-milestone.spec.ts`.

From this session:

8. **`e2e/cross-app/p5-milestone.spec.ts`** — prettier formatting fix only
   (`make lint` flagged it; whitespace/wrapping, no logic change).
9. `graphify-out/{GRAPH_REPORT.md,graph.html,graph.json,manifest.json}` —
   AST-only incremental `graphify update .` (see (e) below).

### Task 1 decision: keep `backend/scripts/restart_pipeline.py`

Reviewed the prior session's fix for the "two real-Temporal-resume specs
can't share one demo-reset" problem (`e2e/lo-console/aisha-occupancy-resume.spec.ts`,
CQ-028 AC1, and the new `p5-milestone.spec.ts` both resolve Aisha Coleman's
real missing-occupancy flag through the real UI and a real Temporal run, but
`backend/app/features/applications/sections/reverify.py::_plan_resume`
deliberately never restarts a *completed* run, so only the first of the two
specs in a pass gets a real resume). **Decision: keep the script**, not
replace it with test-order tricks. Reasoning:

- Only referenced from `e2e/cross-app/p5-milestone.spec.ts` and its own
  docstring (confirmed via a repo-wide grep) — genuinely test-only; no
  production code path touches it.
- It's a thin CLI (persona/email lookup → `client.start_workflow(...,
  id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE)`), consistent with
  other one-off scripts already in `backend/scripts/` (`freeze_version.py`,
  `build_report_fixtures.py`, `create_user.py`, `export_openapi.py`) — not a
  new pattern for that directory.
- It does not touch pricing/verification logic, only which Temporal run id
  is live.
- **It already makes the milestone spec order-independent**, not just
  "safe under the order Playwright happened to use": `cleanupAishasPipelineArtifacts`
  + `restartAishasPipeline()` unconditionally reset Aisha's DB rows and start
  a brand-new Temporal run, regardless of whether `aisha-occupancy-resume.spec.ts`
  (lo-console) ran before or after this spec (cross-app) in the same pass.
  Confirmed empirically: both official full-suite runs this session
  (68/68 each) exercise this path with `lo-console` running first per
  Playwright's project order, and the prior session's isolated re-run
  (`p5-milestone.spec.ts` alone, ~17s) also passed — the fix doesn't depend
  on ordering at all, it just needs *a* Temporal run, real or restarted.
- The alternative considered and rejected: Playwright `project.dependencies:
  ["lo-console"]` on the `cross-app` project, then have the milestone spec
  only assert post-conditions instead of re-performing the resume itself.
  Rejected because (a) only Aisha's seed persona
  (`seed/personas/p07_aisha_coleman.yaml`) has the missing-occupancy
  condition either spec needs, so there's no seed-data-only fix; (b)
  `dependencies` would also serialize the *other* cross-app tests
  (`p6-milestone`, `borrower-action-reflects-in-console`) behind all of
  `lo-console` for no reason; and (c) a `dependencies`-failed project causes
  Playwright to **skip** (not fail) its dependents, which would hide a real
  cross-app regression as "skipped" instead of surfacing it as "failed" —
  strictly worse CI signal than the current self-contained fix.

### Runs

Both runs this session: fresh `make demo-reset`, API + worker restarted
each time (asyncpg pooled connections cache type OIDs from the dropped DB —
restarting avoids `cache lookup failed for type`), both Next.js apps left
running throughout, `pnpm exec playwright test --workers=1 --reporter=line`
with `LO_BASE_URL=http://localhost:3128 PORTAL_BASE_URL=http://localhost:3228
SEED_STAFF_PASSWORD=... SEED_BORROWER_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_dev_s28` (the
`+asyncpg` scheme matters — see the note below).

| Run | Scope | Result | Duration |
| --- | --- | --- | --- |
| 1 | Full suite (`--workers=1`, all 3 projects: lo-console, borrower-portal, cross-app), fresh `make demo-reset` | **68 passed, 0 failed** | 2.3 min |
| 2 | Same, second fresh `make demo-reset` + API/worker restart | **68 passed, 0 failed** | 1.9 min |

Both runs are fully green — the two-Temporal-resume fix (task 1) held clean
across both, with no flakiness and no test-only issues found in `e2e/**`
this round.

**One environment note, not a bug**: the first attempt at run 1 failed at
`e2e/global-setup.ts`'s `freeze_version.py` call with `ModuleNotFoundError:
No module named 'psycopg'`. Root cause: `e2e/helpers/db.ts`'s
`nodePgConnectionString()` already strips `+asyncpg` from `DATABASE_URL`
itself before opening its own `pg` pool, so the env var handed to the
`pnpm exec playwright test` invocation must be passed **exactly as it
appears in `.env`** (`postgresql+asyncpg://...`). Passing a pre-stripped
plain `postgresql://` URL instead works for Node but leaks into the `uv run`
subprocesses `global-setup.ts` spawns (e.g. `freeze_version.py`), which
inherit the overridden env var and break pydantic-settings' asyncpg driver
resolution. Not an app or test bug — purely a corrected invocation, now
reflected in the command line above.

Evidence screenshots: `docs/backlog/evidence/p56-phase/` — all 6 files
refreshed from this session's run 2: `p5-milestone-dashboard.png`,
`p5-milestone-aisha-priced.png`, `p5-milestone-dashboard-after.png`,
`p6-milestone-borrower-intake.png`, `p6-milestone-borrower-priced.png`,
`p6-milestone-lo-console-priced.png`.

## (b) `make demo-reset` timing

Prior session, slot 28: **1.9s**, **1.3s**, **1.2s**. This session, slot 28:
**1.5s** (before run 1), **1.2s** (before run 2). All well under the 60s
budget (`=== done in ===` line; wall time including `uv run` startup was
~2–9s).

## (c) H2 "pending P3 re-check" list — SUPERSEDED, see `phase-p5-p6-main-merge-plan.md`

**This section's finding is out of date.** It was produced by checking this
branch's `phase-p5-p6` code (P3 was not yet on `main`), and reads as "P3 was
never built." That conclusion does not hold once `main`'s P3/P4 (CQ-017
pricing panel, CQ-018 quote builder + reprice, CQ-019 send tab, CQ-020
letter PDF + `SendQuotePackageWorkflow`) is merged in — the main-merge
plan's own research (`origin/phase-p5-p6:docs/backlog/phase-p5-p6-main-merge-plan.md`,
"Cross-lane mismatches" section) confirms all of these now exist on `main`
and are handled by dedicated reconciliation units **U1–U3**, not re-litigated
here. Keeping the original investigation below for the audit trail — it is
still useful evidence of what `phase-p5-p6`-only looked like, and every one
of its concrete code pointers (line numbers, service names) matches what the
merge plan's own research found on the `main` side.

Investigation method: grepped `docs/backlog/CQ-02*/post-dev.md`,
`docs/backlog/CQ-03*/post-dev.md` and `phase-p5-p6-*.md` for "pending"/"P3",
then cross-checked every H2 item against the actual code on `phase-p5-p6`
(not just prose) via `packages/api-client/openapi.json` (the ground truth
for what routes existed on this branch) and direct greps for
`clear_stale`/`mark_stale` callers, `datetime.now(UTC)` vs `core/clock.now()`
call sites, and the LO console route tree.

| Item / AC | Depends on | Status found on `phase-p5-p6` alone | Now (per the merge plan's own research on `main`) |
| --- | --- | --- | --- |
| CQ-030 AC5: reprice must call `clear_stale(fresh_quote_ids=…)` | CQ-018 `/reprice` | No `/reprice` route existed in `packages/api-client/openapi.json` on this branch; `clear_stale` (`quotes/stale/service.py:356`) had zero non-test callers. | Exists on `main`: `builder/service.py:762 reprice_application` (and `:733 autoquote_replacing`). Merge plan flags it *still* doesn't call `clear_stale` — a Stale application stays Stale after reprice, so CQ-030 AC5 (Grace Kim) still fails post-merge. **U3 fixes this** (M4). |
| CQ-029 AC2: PDF-download half, "re-check after CQ-020" | CQ-020 | No `/send` route existed; `QuotePackage(` was only ever instantiated in `seed/loader.py`, never in application code on this branch. | CQ-020's send flow exists on `main` (`delivery/steps.py`, `send/service.py`) and already sets `attachment_keys=[version.letter_key]` in the shared bucket, compatible with the outbox's `astream_object` stream. Merge plan: "ready to verify end to end." **U4 adds the cross-app spec** (send Marcus's quote, open the outbox email, download the PDF) to actually prove it. |
| Stale marking shared with CQ-017 | CQ-017 | Neither override endpoint on this branch marked quotes stale (`applications/sections/fields.py`, no stale logic; `pricing/enrichment/service.py:283,316`, also none — and that second, spec-named `/field-values/{key}` route was confirmed unused by any frontend code, a real orphaned-endpoint finding). | `main`'s CQ-017 (`enrichment/service.py::_mark_application_quotes_stale`) and CQ-018 (`builder/service.py:508`) *do* mark quotes stale now, but each with its own code instead of sharing CQ-030's `mark_application_quotes_stale` — two parallel implementations of the same rule. **U3 unifies them** (M4). The `/field-values` vs `/fields` duplication this session found is not mentioned in the merge plan's research; worth flagging to the U1 worker as a possible third loose end, not yet confirmed resolved by the merge. |
| E2 clock: `priced_at`/`sent_at` must use `core/clock.now()` | — | Confirmed bypassed with `datetime.now(UTC)` at `pricing/scenarios/service.py:264` and `portal/reports/versions.py:178`. | Merge plan's own research finds the *same* pattern independently, and a longer list of it, on `main`: `priced_at` at `scenarios/service.py:291`, `builder/service.py:648,781`; `sent_at` at `delivery/steps.py:134`; `expires_at` at `portal/reports/versions.py:64-65`; plus `send/service.py:407`, `readiness.py:96`. **U3 fixes all of these** (M5). |
| CQ-017: stale-marker reconciliation + `/field-values` re-verify and resume | CQ-017/CQ-028 | Same root cause as the row above. | Covered by U3 (M4) for the stale-marking half; the `/field-values` orphan needs a specific check in U1 or U4 (see note above). |
| Move P3 files under `apps/lo-console/src/app/applications/[id]` into `(staff)/` | — | **Resolved** on this branch already — confirmed already under `apps/lo-console/src/app/(staff)/applications/[id]/`. | Still true; the merge plan separately flags that main's own edits to `(staff)/applications/[id]/{pricing,send}/page.tsx` will need their relative imports switched to `@/features/…` once merged in (a *different*, import-path issue, not a re-regression of the route-group move). |
| `lock_application_quotes` should use `FOR NO KEY UPDATE` once CQ-020 inserts QuotePackages | CQ-020 | Confirmed still `FOR UPDATE` (`applications/credit/hard_pull.py:91`), and moot since CQ-020 didn't insert `QuotePackage` rows in application code on this branch (only seed fixtures did). | Merge plan's own lock research (M3) independently reaches the same "must switch to FOR NO KEY UPDATE" conclusion, now for a real reason: main added a *second* lock module (`applications/locks.py`, plain FOR UPDATE) that can deadlock against CQ-030's/CQ-033's quotes-first lock order. **U2 unifies the lock modules and fixes this** (M3). |
| CQ-029: un-hide admin "Run stale check now" button | CQ-030 | **Resolved** on this branch — `IntegrationsPanel.tsx:208` renders it unconditionally; its own test comment confirms "CQ-030 has merged." | Not revisited by the merge plan (not a cross-lane conflict); should still hold post-merge, worth a quick re-check in U4. |
| CQ-025: stale list should query `quote_package_versions.expired_at`/`applications.status = 'stale'` | CQ-030 | Confirmed still using its own time-window heuristic (`dashboard/service.py::_build_stale`, ~lines 266-300) instead of the canonical fields CQ-030 writes. | Not mentioned in the merge plan's research; likely still open post-merge since nothing in U1-U3's scope touches `dashboard/service.py`. Flag for U4. |
| CQ-027 AC2/AC3 | CQ-030, CQ-025 | **Resolved** per CQ-027's own post-dev.md "Orchestrator note (after CQ-025 merged)." | Unaffected by the merge; still resolved. |

## (d) Consolidated follow-up backlog

Collected via `grep -A` over the "Follow-ups" sections of all 10 CQ-025..034
`post-dev.md` files, plus `phase-p5-p6-e2e-cleanup.md` and
`phase-p5-p6-foundation.md`. Grouped by area, one line each (severity per
the source doc's own framing):

**Pricing/quotes/stale** (mostly superseded by the main-merge plan's U1–U3 — see (c)):
- Resend path can silently revert the attention-list reason to the generic
  fallback text once a resend can happen after OPTION_SELECTED/INQUIRY
  (`_latest_sent_versions` orders by `sent_at DESC`, correct today, but a
  fresh unacted-on resend version would become "most recent") — CQ-025
  follow-up, minor, not yet triggered by anything the app can do today.
- Duplicated metros endpoints, metro names not state-qualified — accepted
  minors, `phase-p5-p6-e2e-cleanup.md`.
- `lock_application_quotes` FOR NO KEY UPDATE — superseded by U2/M3 (was
  blocked on CQ-020, which is now resolved by the merge; see (c)).
- CQ-025's stale list vs CQ-030's canonical fields (`_build_stale`'s own
  heuristic vs `applications.status='stale'`/`expired_at`) — see (c), not
  covered by U1-U3, flagged for U4.

**Locking (cross-cutting, main-merge)**: two lock modules
(`applications/locking.py` vs main's new `applications/locks.py`) with
different orders (quotes-then-application vs application-then-quotes) can
deadlock against each other and against KEY SHARE locks from activity
inserts. Major — this is exactly what U2 exists to fix (M3); flagged here
because it's the single largest cross-lane risk the merge plan's own
research surfaced.

**Email/outbox**:
- `notifications/email/service.py::send_email` sends over SMTP before the
  caller's `db.commit()` — every caller (OTP issue, CQ-020 send, CQ-024
  actions, CQ-034's inbox/confirmation emails) shares the same "email sent,
  no record" gap if the process dies in between. Accepted, cross-cutting;
  CQ-034's own follow-up: "worth a dedicated hardening item on
  `notifications/email/`, not a per-caller fix."
- `outbox/service.py`'s subject-based `type` classifier only recognizes
  today's OTP/borrower-action/quote-sent subjects — needs `_TYPE_SUBJECT_RULES`
  extended once CQ-020 (real quote-send emails), CQ-024 (letter emails) and
  CQ-034 (support emails) land, or those emails keep showing as `other` —
  CQ-029 follow-up. (CQ-020/024 are now on `main` per the merge; worth
  re-checking whether their actual subjects were ever added.)

**Dashboard/attention list**:
- `_build_application_out`-style N+1: up to 4 sequential DB round-trips per
  application, unbatched across N applications — fine at today's seed scale
  (every seeded persona/demo borrower has exactly 1 application), logged as
  a scaling follow-up, not a functional bug — CQ-031 follow-up.
- CQ-025's stale list vs CQ-030's canonical fields — see above/(c).

**Consent/reporting**:
- No LO-authenticated report-preview route exists yet for "Quotes sent"
  report links; a future item could add one instead of linking to the
  borrower-only `/report/{token}` route — CQ-026 follow-up.
- Optional Temporal `Replayer` test for
  `workflow.patched("p56-load-application-source")` against a pre-patch
  history — skipped for budget reasons; `phase-p5-p6-foundation.md` already
  has the concrete approach logged (`test_application_pipeline_replay.py`,
  capture a pre-patch history or build one via
  `WorkflowEnvironment.start_time_skipping()`, replay with
  `temporalio.worker.Replayer`).

**Dead code / orphaned endpoints**:
- `apps/borrower-portal/src/features/auth/applicationStatus.ts`'s
  `applicationStatusLabel` export is dead code after CQ-031 (and its
  re-export in `features/auth/index.ts`) — flagged for removal by whoever
  next touches `features/auth/` — CQ-031 follow-up.
- **New finding, this session**: `pricing/enrichment/router.py`'s
  `PATCH .../field-values/{field_key}` (+ `/revert`) — the endpoint CQ-017's
  own spec.md names — is not called by any frontend code in either app
  (confirmed by grep across both apps' `src/`); the LO console's
  Verification tabs actually call the older, parallel
  `applications/sections/router.py`'s `PUT/DELETE .../fields/{field_key}`
  instead. Two endpoints doing the same job, one dead. Not previously
  logged anywhere; flagged to the U1 worker in (c) above since it may or
  may not survive the merge as-is.

**Proxy/IP** (same root cause, logged twice):
- `auth.common.client_ip` uses the socket peer, not
  `X-Forwarded-For`/Railway's real client IP — CQ-032 and CQ-033 follow-ups
  both point at the same fix landing once CQ-035 exists.

## (e) `make lint` / `make test` / `graphify update .`

**`make lint`**: found and fixed one real issue —
`e2e/cross-app/p5-milestone.spec.ts` (written by the prior session) had a
prettier formatting violation. Fixed with `pnpm exec prettier --write`
(whitespace/wrapping only, no logic change). Re-ran: **fully green** — ruff
check, ruff format --check, mypy (481 files), eslint ×4 workspaces
(api-client, ui, lo-console, borrower-portal), tsc ×4, prettier --check.

**`make test`**: **fully green** — 846 backend pytest tests, 32 seed tests,
156 borrower-portal + 220 lo-console + 163 packages/ui + 2 packages/api-client
frontend tests (Vitest), all passed, 1 intentionally-skipped stub test.

**`graphify update .`**: ran, with one scoped deviation, logged here rather
than silently deviating from AGENTS.md's framing of the command as
"AST-only, no API cost":

`detect_incremental` found 737 changed files since whoever last committed
`graphify-out/`: 471 code (free, AST-only) + 199 docs + 66 images + 1 paper
(the latter three categories all require LLM semantic extraction — no
`GEMINI_API_KEY`/`GOOGLE_API_KEY` is set in this environment, so semantic
extraction means dispatching subagents as the host LLM: roughly 15-20
batches for the 199 docs + 1 paper, plus 66 *individual* per-image subagent
calls since each image needs its own chunk — on the order of 80+ subagent
dispatches total). That volume reflects the whole repo's drift across many
phases of work since `graphify-out/` was last committed, not anything from
this session, and would have blown well past the context budget on a
rebuild unrelated to phase verification.

**Decision: ran AST-only.** Extracted the 471 code files via `graphify.extract`,
merged into the existing graph via `build_merge`, health-checked clean (0
dangling/missing/collapsed edges via `graphify.diagnostics`), regenerated
`GRAPH_REPORT.md` + `graph.html` (8003 nodes, 19291 edges, 540 communities),
**0 tokens spent**. Did not hand-label the 540 communities (kept the
default `Community N` placeholders — no budget to write ~540 2-5-word
names by hand). **Known gap left for a dedicated follow-up**: the 199
changed docs (including the 18 spec.md files this phase touched) + 66
images + 1 paper are not yet reflected in the graph's semantic layer; their
nodes/edges still reflect content from before those edits. A dedicated
`graphify update .` pass — ideally with a Gemini key configured, or
explicitly budgeted for ~80 subagent dispatches — should be run as its own
maintenance task, not bundled into a verification pass again.

One incidental fix during this: the skill's standard Step 9 cleanup
(`rm -f graphify-out/.graphify_analysis.json`) registered as a git deletion,
because this repo (unusually) has that file committed rather than treated
as pure scratch. Restored it with `git checkout --
graphify-out/.graphify_analysis.json` before it could be committed as a
deletion.

---

## Handoff

### Handoff 1 — 2026-09-25 (time not tracked) — Claude (Opus 5.5, P56-verify)

- **Branch / last commit:** `p56-phase-verification` @ `dd974bc`
- **Stage:** 5 Test (mid full-suite verification, tasks 1–2 done, task 3
  partially done, tasks 4–6 not started)
- **Done:** stale-stub e2e fixes (task 1), the two milestone specs plus
  `queryRows()`/`playwright.config.ts` wiring (task 2), one full-suite run
  (67/68, the 1 failure root-caused and fixed after the run —
  `backend/scripts/restart_pipeline.py`, verified in isolation), `make
  demo-reset` timed 3× (1.9s/1.3s/1.2s).
- **Next steps (superseded by Handoff 2 below — see there for what actually
  happened instead):** re-run the full suite twice, do the 5c/5d grep
  passes, run lint/test, open the PR.

### Handoff 2 — 2026-09-25 — Claude (Opus/Sonnet 5, P56-verify session 2)

- **Branch / last commit:** `p56-verify-2` (local name for
  `p56-phase-verification`) @ this doc's own commit, prefixed
  `P56-verify: wip:`.
- **Stage:** 5 Test, complete for this branch's scope — then **superseded
  mid-session** by a scope change from the coordinator: P3/P4 landed on
  `main` while this session was running, so a dedicated
  `phase-p5-p6-main-merge-plan.md` now governs what happens next (units
  U0–U5). This session's remaining work *is* U0: close out this branch's
  WIP cleanly (commit, push, kill slot 28) rather than open a PR.
- **Done:**
  - Task 1 (review the handoff's fix): decided to **keep**
    `backend/scripts/restart_pipeline.py` — see "(a) Task 1 decision" above
    for the full reasoning (test-only, consistent with existing
    `backend/scripts/` conventions, already order-independent, the
    `project.dependencies` alternative was considered and rejected).
  - Task 2 (full suite twice): **both green**. Run 1: 68/68 (2.3 min). Run
    2: 68/68 (1.9 min). One env-invocation mistake found and fixed along
    the way (not an app/test bug — see "(a) Runs" above for the
    `DATABASE_URL` scheme note).
  - `make lint`: found and fixed one real prettier violation in
    `e2e/cross-app/p5-milestone.spec.ts` (whitespace only). Now green.
  - `make test`: green (846 backend + 32 seed + 541 frontend tests).
  - `graphify update .`: ran AST-only (471 code files, 0 token cost);
    logged the docs/images/paper backlog as a deferred follow-up — see (e).
  - 5c investigation: fully researched with file:line evidence against
    `phase-p5-p6` alone (this branch never had `main`'s P3/P4). Once the
    coordinator surfaced the main-merge plan mid-session, **rewrote this
    section's framing as superseded**, cross-referencing every finding
    against the merge plan's own independent research on `main` (which
    corroborates every line-number/file this session found, just from the
    other side of the merge) and pointing at U1–U3 as where each item is
    actually resolved. Flagged one thing the merge plan's research doesn't
    mention: the orphaned `/field-values` endpoint (CQ-017's own
    spec-named route, never called by any frontend code) — worth a check
    in U1 or U4.
  - 5d: compiled the consolidated follow-up backlog, grouped by area, with
    the new orphaned-endpoint finding folded in.
- **In progress:** nothing mid-edit. This doc is finished for what this
  branch can responsibly claim; the (c) section explicitly defers to the
  merge plan rather than re-asserting a conclusion ("P3 was never built")
  that the merge makes moot.
- **Next 3 steps (now the merge plan's, not this branch's):**
  1. U1 (`p56-merge-main`, Opus, slot 29): merge `main` into `phase-p5-p6`,
     resolve the 8 conflicts, get `make lint`/`make test`/`make demo-reset`/
     full Playwright green.
  2. U2 (`p56-lock-unify`, Opus, slot 30) then U3 (`p56-stale-clock`, Opus,
     slot 31): lock unification, then stale-marking/clock/reprice
     reconciliation.
  3. U4 (`p56-phase-verification`, Sonnet, slot 28): re-run this doc's (a)
     suite runs post-merge, rewrite (c) with each item resolved with real
     evidence (not "pending"), add the CQ-029 AC2 send+PDF cross-app spec,
     open the PR.
- **Open questions / blockers:** none for this branch — its work is done
  and closed out per U0. The orphaned `/field-values` endpoint finding
  should be handed to whoever runs U1 or U4, since it isn't in the merge
  plan's own research and might get silently resolved (or silently
  preserved as dead code) by the merge without anyone noticing either way.
- **Verify state (for U4, once U1–U3 land):**
  ```bash
  cd <repo> && git fetch origin && git switch phase-p5-p6
  lsof -iTCP:8128,3128,3228 -sTCP:LISTEN -n -P   # confirm slot 28 is free
  bash scripts/worktree-env.sh 28
  make demo-reset                                 # expect well under 60s
  PORTAL_BASE_URL=http://localhost:3228 uv run uvicorn app.main:app --app-dir backend --port 8128
  make worker
  pnpm --filter @cq/lo-console exec next dev -p 3128
  pnpm --filter @cq/borrower-portal exec next dev -p 3228
  # from repo root, DATABASE_URL exactly as in .env (+asyncpg, not stripped):
  LO_BASE_URL=http://localhost:3128 PORTAL_BASE_URL=http://localhost:3228 \
    SEED_STAFF_PASSWORD=<from .env> SEED_BORROWER_PASSWORD=<from .env> \
    DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_dev_s28 \
    pnpm exec playwright test --workers=1 --reporter=line
  ```
