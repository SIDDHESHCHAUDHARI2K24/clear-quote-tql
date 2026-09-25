# Phase P5 + P6 plan (CQ-025–CQ-034)

## Context

P0–P2 are on `main`. P3/P4 run on `phase-p3-p4`. P4 (CQ-021–024) and CQ-016 are merged there and In Review in Kaneo. CQ-017 is In Progress (open branch). CQ-018–020 are To Do. The next phases are P5 LO Tier B (CQ-025–030) and P6 Borrower Tier B/C (CQ-031–034). Their only hard dependencies are CQ-016, CQ-011, CQ-012 and CQ-015, and all of these are merged.

The specs for CQ-025–034 are filled in but uncommitted in the main folder (branch `phase-p0-p1`). They are still marked "Draft", with no `spec-ready` label in Kaneo; the human says to mark them ready now. This session plans and orchestrates. Subagents write the code: **Opus 5.5 for complex units, Sonnet 5 for medium and easy ones**. Each unit gets its own worktree and PR. The same AGENTS.md loop and `_templates/` (plan, handoff, post-dev) are used as in `docs/backlog/phase-p3-p4-plan.md`.

### Human decisions (2026-09-25, this session)
- **H1 Base:** new integration branch `phase-p5-p6`, cut from the current `origin/phase-p3-p4`. Item PRs target `phase-p5-p6`. The orchestrator merges `phase-p3-p4` into it as each P3 item lands: regenerate the api-client and check `alembic heads` = 1. The final PR `phase-p5-p6` → `main` is opened after P3/P4 reach main, and the human merges it.
- **H2 P3-dependent ACs:** stub now and re-check later. Workers verify with factories or fixtures and expose a hook that the P3 item will call. Those ACs are marked "pending P3" in post-dev.md, and the orchestrator re-verifies them after the P3 merge. Affected: CQ-030 AC5 (reprice from CQ-018), CQ-029 AC2 (PDF from CQ-020), and stale marking shared with CQ-017.
- **H3 Foundation:** one foundation unit `p56-foundation` holds the shared migration, helpers and both app shells.
- **H4 Specs:** approved. The orchestrator commits them with Status "Approved" and adds the `spec-ready` label in Kaneo for CQ-025–034.
- **H5 Context cap:** no subagent goes above 400K. Workers commit WIP, append a `handoff.md` entry (template `docs/backlog/_templates/handoff.md`) and stop at **~350K**. If they are mid-way through a critical atomic step (a migration, a half-applied refactor, a failing test being fixed), they may run to **~450K** to leave a consistent state. A fresh worker continues from the handoff. Review-fix rounds go to a fresh worker, and findings are sent in one batch.

## Research findings

**Backend (phase-p3-p4).**
- Routes mount at `/api/v1` via `core/registry.py:17` `FEATURE_ROUTERS`. The specs' `/api/...` paths therefore become `/api/v1/...`.
- Auth:
  - `core/auth.py` has `CurrentStaff`, `require_roles`, `scope_applications(stmt, user, lo_id)`, `get_scoped_application` (404) and `CurrentBorrower` + `ensure_borrower_owns_client`.
  - `BorrowerAccount.client_id` is 1:1 with the client.
- `ApplicationStatus` already includes `stale`, but nothing writes it. `quotes.stale` and `applications.recommended_quote_id` exist, but nothing writes them yet. CQ-017 adds the stale marking in `enrichment/service.py`.
- `QuotePackageVersion` (`quotes/send/models.py:60`) has report_token, sent_at, expires_at (sent + 21 d), superseded and borrower_action.
- Activity: `applications/timeline/models.py` `ActivityEvent(actor,type,payload,at)`. Event types:
  - `pipeline.*`
  - `application.withdrawn` / `application.closed`
  - `quote.viewed` / `quote.move_forward` / `quote.ask_*`
  - seed `quote.sent`
  There is **no GET endpoint**, and override/revert writes no event.
- Flags: `verification/models.py:41` `Flag(tab, field_key, rule, severity, resolved_at)`, **with no message**. `verification/service.py:255` `run_and_persist(app_id, db)` re-runs the rules. The resume signal is `application_pipeline.py:48`; the loop restarts at verify.
- Pipeline `run()` always calls `import_application` (LOS `los_loan_guid` is required), so it has **no portal/skip-import path**. Other gaps:
  - No `create_application` service.
  - `_least_loaded_lo_id` and `_find_or_create_client` are private in `auth/borrower/service.py:187,202`.
- Consent (`borrower/consent/models.py`) has only type, text_hash, ip and at. It has **no status, requested_by, requested_at, typed_name, user_agent, text_version or decline_reason**.
- Models exist for `Document`, `Liability`, `HousingHistory`, `Employment`, `Asset`, and `Property` (buy_box_states/metros, recommend_matches). The metros list exists only in `ProviderListing.metro`.
- Integrations: 9 adapters. Failure switch: `common/failure_toggle.py` (`is_forced_to_fail`, `set_forced_failure`). Call log: `IntegrationCall` via `common/logging.py:49`. `CreditClient.pull_credit(loan_number, pull_type)`; the seed has hard_pull rows with 3 scores and `middle_score`.
- Email: `send_email(db,*,to,subject,html,application_id)` writes to the outbox and does not commit. It takes no attachments. Templates are Python string helpers (`portal/actions/templates.py`).
- Storage: **no `core/storage.py`**. boto3 appears only in `seed/generators/documents.py`.
- Settings table defaults include `stale_quote_days`=21, read via `verification/service.py:76 _setting_int`. `ConfigSnapshot()` uses hardcoded defaults. **No clock injection.**
- Temporal: one worker (`workflows/worker.py`), task queue from settings, **no schedules**. There is no reprice endpoint (that is CQ-018).
- Rate limit: `auth/otp/rate_limit.py` `hit(valkey,key,limit,window_seconds)`, reusable.
- Tests: `backend/conftest.py` provides `db_session`, `client`, `make_staff_session(role)`, `make_borrower_session` and fake Valkey. Seed users: 2 LOs, a Manager and an Admin. Seed persona statuses:
  - Aisha (p07) and Ben (p08) are needs_attention.
  - Grace (p09) was sent 25 days ago.
  - Luis (p10) is option_selected.
  - The rest are priced.
  - No borrower without an application.

**Frontend.**
- `lo-console`:
  - The root `app/layout.tsx` is bare: no nav, shell or user menu. `/` is a placeholder that calls `/auth/staff/me`.
  - Role is known only via `/me`, with no session context.
  - Workspace tabs 1–5 are placeholders ("Built in CQ-028").
  - `WorkspaceHeader.tsx:58-64` has the natural spot for the Activity button.
  - Data fetching is openapi-fetch in `useEffect`, with thin per-feature `api.ts` wrappers.
- `borrower-portal`: the layout is bare, `/` is a placeholder, and `middleware.ts` guards on the cookie.
- `packages/ui` has Button, Card, Money/PercentInput, Overlay (modal with focus trap), SourceBadge, StatusPill, Table, Tabs and auth bits. It is **missing** Pagination, Select/MultiSelect, Drawer and nav/menu.
- Playwright projects: lo-console, borrower-portal, cross-app. Helpers: `staffLogin`, `borrowerLogin`, `mailpit`, `db`. `scripts/worktree-env.sh <slot>` gives each worktree its own DBs, Valkey db, ports and task queue; slots 1–10 are taken.

**Conflict hotspots:**
- `registry.py` (one line per item; trivial merge).
- `packages/api-client` generated files (never hand-merged; rerun `make api-client`).
- Root layouts and nav (foundation owns them).
- `WorkspaceHeader.tsx` (CQ-029 only).
- `packages/ui/src/index.ts` (foundation adds the shared primitives).

## Decisions (each worker logs the relevant ones in its plan.md)

| # | Decision |
|---|---|
| E1 | One foundation migration (chained off the head on `phase-p5-p6`):<br>• `flags.message` (text).<br>• `consents`: `status` (pending/accepted/declined/expired; the existing rows count as accepted), `requested_by`, `requested_at`, `decided_at`, `typed_name`, `user_agent`, `text_version`, `decline_reason`, `expires_at`.<br>• `support_requests` (reference, borrower_account_id, application_id, topic, message, preferred_contact, phone, created_at).<br>• `application_drafts` (borrower_account_id, data JSONB per tab, current_tab, submitted_application_id, timestamps; one open draft per borrower via a partial unique index).<br>• `applications.source` (`los`/`portal`, default `los`).<br>Any later migration chains off the head, and the orchestrator checks `alembic heads` = 1 at every merge. |
| E2 | `core/clock.py` `now()` honours the `CLOCK_NOW` setting. New P5/P6 code uses it; old code is not refactored. |
| E3 | `core/storage.py` is a MinIO/S3 helper (put/get/presign/stream, bucket ensure). CQ-020 in the P3 lane is told to reuse it (Kaneo comment on CQ-020). |
| E4 | `core/pagination.py` holds `Page[T]` and `paginate(stmt, page, page_size≤100)`. |
| E5 | The LO console gets a `(staff)` route group layout with a top nav (Dashboard, Clients, Applications, Outbox) and a user menu (Settings and Integrations for Admin only, Sign out). A `StaffSessionProvider`/`useStaffSession` gives the role. Login and gallery stay outside the group. Pages are stub routes that the items fill: `/`, `/clients`, `/applications`, `/outbox`, `/admin/integrations`, `/admin/settings`. |
| E6 | The borrower portal gets a `(portal)` shell: a header with the logo, Home, Support and a sign-out menu, plus a footer with disclosures. It includes a `useBorrowerSession`. Stub routes: `/`, `/support`, `/apply`, `/tasks/credit-check/[id]`. |
| E7 | New `packages/ui` primitives: `Pagination`, `Select`, `MultiSelect`, `Drawer` (right side, focus-trapped), `EmptyState`, `Toast`. |
| E8 | Flag messages: the foundation backfills `flags.message` from rule text in `verification/rules.py`, and `write_flag` sets it. |
| E9 | CQ-027 owns `ApplicationRow` and the list row schema. CQ-026 runs a wave later and reuses them, along with CQ-029's `ActivityTimeline`. |
| E10 | CQ-025 tile links use exactly the CQ-027 parameter names in the CQ-025 spec table (the `sent_or_later` alias and comma lists). |
| E11 | CQ-028's Credit section response includes the latest consent request (status, dates, FICO after the pull, and the decline reason). CQ-028-ui renders all three states, so CQ-033 needs **no** LO-console edit. |
| E12 | CQ-030 exposes `stale.service.clear_stale(application_id)` and `mark_stale(now)`, and a shared `mark_application_quotes_stale(app_id, reason)`. If CQ-017's marker has merged, CQ-030 and CQ-033 reuse it; otherwise CQ-030 owns it and CQ-017's merge reconciles. CQ-018's reprice must call `clear_stale` (Kaneo comment on CQ-018). |
| E13 | The CQ-029 outbox attachment stream uses `core/storage.py`. AC2's PDF is checked with a fixture attachment until CQ-020 lands (H2). |
| E14 | A portal application sets `source = portal`, and the pipeline skips `import_application` for it. A wizard applicant who reaches a hard pull without a seeded credit report gets a deterministic mock score. |
| E15 | LO auto-assignment: the foundation promotes `_least_loaded_lo_id` to the public `applications.assignment.least_loaded_lo_id` (fewest active applications, ties broken alphabetically). |
| E16 | Cross-scope access stays **404** (Decision #11 / D6). Specs that say 403 for LOs log the difference. Admin-only endpoints still return 403 to non-admins through `require_roles`. |
| E17 | The foundation seeds one borrower with no application (`noapp.borrower@clearquote-demo.test`) for CQ-031 AC4 and CQ-034 AC5. |

## Work units and waves

A wave starts only after the previous wave's PRs are merged into `phase-p5-p6`. Model tier: **O** = Opus 5.5, **S** = Sonnet 5.

| Wave | # | Unit | Model | Branch | Slot | Owns (main paths) | Change |
|---|---|---|---|---|---|---|---|
| 0 | — | Orchestrator setup | me | `phase-p5-p6` | 0 | `docs/backlog/CQ-025..034/spec.md`, `docs/backlog/README.md`, `docs/backlog/phase-p5-p6-plan.md` | Branch from `origin/phase-p3-p4`. Commit the 10 specs with Status "Approved". Add the `spec-ready` label in Kaneo. Post the E3/E12 comments on CQ-020/CQ-018. Push. |
| 1 | 1 | P5/P6 foundation | O | `p56-foundation` | 11 | E1 migration and models, `core/clock.py`, `core/storage.py`, `core/pagination.py`, `applications/assignment.py`, `flags.message` + `write_flag`, pipeline `source=portal` skip (E14), E17 seed, lo-console `(staff)` shell + session provider + stub routes, portal `(portal)` shell + stubs, `packages/ui` primitives (E7), `worktree-env.sh` slots 11–23 | Shared contracts and shells only, with no item features. Tests for each helper, the shell role gating and the pipeline skip. |
| 2 | 2 | CQ-025 Dashboard | S | `cq-025-dashboard` | 12 | `features/dashboard/`, `app/(staff)/page.tsx`, `src/features/dashboard/` | Aggregate endpoint, tiles, lists, feed, 30 s refresh. |
| 2 | 3 | CQ-027 Applications list | S | `cq-027-applications-list` | 13 | `features/applications/listing/`, `(staff)/applications/page.tsx`, `src/features/applications/` (ApplicationRow, filters) | Filtered, paginated list plus indexes; URL filters. |
| 2 | 4 | CQ-028a Verification API | O | `cq-028-verification-api` | 14 | `features/applications/sections/`, collection row edits, credit actions (import liabilities, hard-pull request + email), property/buy-box, documents, `reference/metros`, re-verify → resume hook, edit activity events | Every CQ-028 backend AC, including the AC1 Temporal integration test. Regenerated api-client. |
| 2 | 5 | CQ-029 Timeline, Outbox, Integrations, Settings | S | `cq-029-timeline-outbox-panel` | 15 | `features/applications/timeline/router`, `features/notifications/outbox/router`, `features/admin/`, `src/features/activity/`, `(staff)/outbox/**`, `(staff)/admin/**`, `WorkspaceHeader.tsx` (Activity button) | Four screens and their endpoints. The stale-check button stays hidden until CQ-030 merges. |
| 2 | 6 | CQ-030 Stale quote job | O | `cq-030-stale-quote-job` | 16 | `features/quotes/stale/`, `workflows/stale_*.py`, `worker.py` (schedule registration), `POST /admin/jobs/stale-check` (a `features/admin/jobs` sub-router, separate from CQ-029's files) | Temporal Schedule, idempotent `mark_stale(now)`, `clear_stale` hook (E12). |
| 2 | 7 | CQ-031 Borrower home | S | `cq-031-borrower-home` | 17 | `features/portal/home/`, `(portal)/page.tsx`, `src/features/home/` | `/portal/me` with stage mapping and next_action, cards, progress, banner, empty state. |
| 2 | 8 | CQ-032a Apply API | O | `cq-032-apply-api` | 18 | `features/portal/apply/` (draft, autosave, per-tab validation, submit, document upload), consent at submit, LO email | Submit creates the application with `source=portal`, starts the pipeline, and the application reaches Priced (AC1 backend via the Temporal test env). |
| 2 | 9 | CQ-034 Support form | S | `cq-034-support-form` | 19 | `features/portal/support/`, `(portal)/support/**`, `src/features/support/`, `SUPPORT_INBOX` setting | Reference, two emails, outbox, activity, 429 rate limit, login help line. |
| 3 | 10 | CQ-026 Clients | S | `cq-026-clients` | 20 | `features/clients/` router/service, `(staff)/clients/**`, `src/features/clients/` | List and detail; reuses ApplicationRow (E9) and ActivityTimeline. |
| 3 | 11 | CQ-028b Verification tabs UI | S | `cq-028-verification-tabs` | 21 | `app/(staff)/applications/[id]/{borrowers,housing,credit,assets,property}/**`, `src/features/verification/` | The five tabs (the worker may run one sub-agent per tab), inline flags, SSN reveal, toast, consent states (E11). |
| 3 | 12 | CQ-032b Apply wizard UI | S | `cq-032-apply-wizard` | 22 | `(portal)/apply/**`, `src/features/apply/` | Four tabs, stepper, 1 s autosave, resume, uploads, confirmation, aria-describedby. |
| 3 | 13 | CQ-033 Hard-pull consent | O | `cq-033-hard-pull-consent` | 23 | `features/portal/consents/`, `features/applications/credit/hard_pull.py` (service guard), `CreditClient.hard_pull`, `(portal)/tasks/credit-check/**` | Consent text v1 + hash, accept/decline, consent-gated pull, middle score, re-run rules, stale on bucket change (E12), expiry, idempotency. |
| 4 | — | Phase verification | me | `phase-p5-p6` | 0 | — | Cross-item ACs (CQ-025 AC4/AC5, CQ-026 AC4 timeline, CQ-031 banner → CQ-033), milestone Playwright specs, and the H2 re-checks after P3 merges. |

Wave 2 has 8 parallel units: 3 Opus and 5 Sonnet. Wave 3 has 4 units: 1 Opus and 3 Sonnet. Split items (CQ-028, CQ-032) produce two PRs under one Kaneo task; the task moves to In Review after the second PR merges.

## E2E recipe (each worker, in its worktree)

1. Setup: `source scripts/worktree-env.sh <slot>`. Slot N gives DBs `cq_dev_s<N>`/`cq_test_s<N>`, Valkey db N+2, API 8100+N, LO 3100+N, portal 3200+N and Temporal queue `cq-s<N>`. Shared infra comes from `make up`. Never touch the `cq_dev`/`cq_test`/`*_p2` DBs, ports 8000/3010/3020, or another slot.
2. `make demo-reset`. Then start in the background: API `uv run uvicorn app.main:app --port $API_PORT`, `make worker` when a workflow or schedule is involved, and the affected app with `pnpm --filter @cq/<app> exec next dev -p <port>`.
3. API: sign in with curl. Staff: `lo@…`/manager/admin from `seed/users.yaml`, password `SEED_STAFF_PASSWORD`. Borrower: persona email with `SEED_BORROWER_PASSWORD`. Read the OTP from Mailpit `http://localhost:8025/api/v1/messages`. Hit the item's endpoints for the AC personas and check counts, statuses and emails (Mailpit).
4. UI: `pnpm exec playwright test <item specs>` with `LO_BASE_URL`/`PORTAL_BASE_URL` set to the slot ports. Save screenshots (1280 px, and 375 px for portal items) to `docs/backlog/CQ-0XX-*/evidence/`.
5. Kill the background processes. Backend-only units (CQ-028a, CQ-030, CQ-032a) skip step 4 and use curl plus Temporal/Mailpit checks.

## Orchestration steps

1. After approval, leave plan mode and do wave 0:
   - Copy this plan to `docs/backlog/phase-p5-p6-plan.md`.
   - Commit the specs with Status "Approved".
   - Kaneo: add `spec-ready` to CQ-025–034, and post the E3/E12 comments on CQ-020 and CQ-018.
   - Save a memory entry for P5/P6 setup and the 350K/450K rule.
2. For each wave: move the wave's Kaneo tasks to In Progress. Launch one worker per unit (`isolation: "worktree"`, background, `model: "opus"` or `"sonnet"` per the table), all in one message.
3. When a worker reports a PR: dispatch a **fresh** Sonnet reviewer (Opus for O units) on the PR against the spec (stage 6, same context cap). Send critical/major findings in one batch to a **fresh** fix worker.
4. Merge:
   - `gh pr merge --merge` into `phase-p5-p6`.
   - Fix generated-file conflicts with `make api-client`.
   - Check `alembic heads` = 1.
   - Run `make lint && make test` and `make demo-reset` on `phase-p5-p6` (slot 0 env), then push.
   - Kaneo: post a comment and move the task to In Review.
5. When a P3 item merges into `phase-p3-p4`: merge `phase-p3-p4` into `phase-p5-p6`, rerun the checks, and re-verify the H2 "pending P3" ACs.
6. After wave 3: phase verification. When P3/P4 are on main, open the PR `phase-p5-p6` → `main` for the human. Update memory.

## Worker prompt template (filled per unit)

```
You are implementing {unit title} ({CQ-0XX}) for Clear Quote TQL, part of building P5 (LO Tier B) and P6 (Borrower Tier B/C).
Repo: this worktree. FIRST: `git fetch origin && git switch -c {branch} origin/phase-p5-p6`. Never touch main, phase-p2, phase-p3-p4 or other worktrees.
Read in order: AGENTS.md, docs/design/system-design.md (sections named in the spec), docs/design/data-field-catalog.md, docs/backlog/{folder}/spec.md, docs/backlog/phase-p5-p6-plan.md (H1–H5, E1–E17). Use `graphify query` for docs questions and codegraph (if indexed) or grep for code.
Scope of this unit: {scope; for split items, which ACs you own}. Owned files: {owned}. Do not edit files outside them except small, logged necessities.
Run the AGENTS.md agent loop stages 1–8 yourself, using the templates in docs/backlog/_templates/:
 - Stages 1–3: fill docs/backlog/{folder}/plan.md from _templates/plan.md (Decisions & questions, tasks, owned files, waves, a test for every AC). Big gap → Kaneo comment on task {kaneo id} + `needs-input` label, stop, report.
 - Stage 4: TDD. Backend: features/<feature>/<sub>/ router/models/schemas/service/tests; register in core/registry.py; routes live under /api/v1; errors from core/errors.py; auth from core/auth.py (CurrentStaff + scope_applications/get_scoped_application, require_roles for admin; CurrentBorrower + ensure_borrower_owns_client). Use core/clock.now(), core/pagination, core/storage. Money math only in quote_engine (Decimal); frontends never compute money. Primary loans never show rent/DSCR/cashflow/cost seg/PPP; never show LTR and STR together. After API changes run `make api-client` (never hand-edit packages/api-client). Frontend: packages/ui tokens and components, src/features/<feature>/, Vitest, `npx react-doctor -y --blocking error`.
 - Stage 5: `make lint` and `make test` green; log in post-dev.md (from _templates/post-dev.md).
 - Stage 7: acceptance checklist with evidence in post-dev.md. ACs that need unbuilt P3 items: verify with fixtures/factories and mark "pending P3 re-check".
 - Stage 8: conventional commits prefixed `{CQ-0XX}:`, ending with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>". Run `graphify update .`. Move Kaneo task {kaneo id} only by commenting; the orchestrator moves status.
CONTEXT CAP: never exceed 400K tokens. At ~350K: commit WIP, append a handoff entry to docs/backlog/{folder}/handoff.md (from _templates/handoff.md), push, and stop with `PR: none — handoff at <sha>`. If you are mid-way through a critical atomic step (migration, half-applied refactor, test being fixed), you may continue to ~450K to reach a consistent state, then hand off.
E2E recipe (slot {N}): {recipe above}.

After you finish implementing the change:
1. **Code review** — Invoke the `Skill` tool with `skill: "code-review"` to find correctness bugs (it reports findings; it does not edit code). Fix any findings it surfaces before continuing.
2. **Run unit tests** — Run the project's test suite (check for package.json scripts, Makefile targets, or common commands like `npm test`, `bun test`, `pytest`, `go test`). If tests fail, fix them.
3. **Test end-to-end** — Follow the e2e test recipe from the coordinator's prompt (below). If the recipe says to skip e2e for this unit, skip it.
4. **Commit and push** — Commit all changes with a clear message, push the branch, and create a PR with `gh pr create`. Use a descriptive title. If `gh` is not available or the push fails, note it in your final message.
5. **Report** — End with a single line: `PR: <url>` so the coordinator can track it. If no PR was created, end with `PR: none — <reason>`.
(PR base: `--base phase-p5-p6`.)
```

## Verification (phase level)

- **Per PR:** the worker's evidence and the fresh-reviewer verdict. After each merge on `phase-p5-p6`: `make lint`, `make test`, `alembic heads` = 1, and `make demo-reset` under 60 s.
- **P5 milestone:** as a Manager, the dashboard counts match the seed (CQ-025 AC1). Resolving Aisha's missing-occupancy flag in the workspace takes her to Priced, and she leaves the attention list.
- **P6 milestone:** a new borrower's application flows to Intake and auto-prices (CQ-032 AC1, Playwright against slot 0 with the worker running).
- **After P3 merges:** re-run the H2 "pending P3" ACs (CQ-030 AC5, CQ-029 AC2, the stale-marker reconciliation).
