# CQ-025 — Post-development notes

## Summary

Built `GET /api/v1/dashboard` (`backend/app/features/dashboard/`): seven
role-scoped tile counts, plus "Needs your attention" (NeedsAttention/
Inquiry/OptionSelected, oldest status change first, with the flag
message/inquiry excerpt/selected-option label as the reason), "Going
stale" (recommended quote or latest sent version older than 21 days, via
`core.clock.now()`) and "Recent activity" (latest 20 events, actor
resolved to a display name). The LO console's `/` route (`(staff)/page.tsx`)
now renders the real dashboard (`src/features/dashboard/`): seven tile
links, the three lists with `EmptyState`, a Manager/Admin LO filter kept in
the URL (`?lo_id=`), and a 30s refresh that pauses while the tab is hidden
and never blanks out already-loaded data on a failed refresh.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET /api/dashboard` | `GET /api/v1/dashboard` | AGENTS.md: every feature mounts under `/api/v1`; the spec path is shorthand for that (plan.md Decision #6). |
| — | Tile hrefs carry `&lo_id=` when a Manager/Admin has one LO selected | Not specified, but needed so the destination list (once CQ-027 exists) matches the tile's own `lo_id`-scoped count (plan.md Decision #5). |
| — | `ActivityItem.actor` is a resolved display label ("System" or the staff user's `full_name`), not the raw `ActivityEvent.actor` string | The raw value is `"system"` or a `User.id`; spec.md's "actor" clearly means something a human reads, and resolving it is one batched query (schemas.py docstring). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — every tile count matches a direct SQL count | Done | `test_dashboard_tiles_match_sql` (backend/app/features/dashboard/tests/test_dashboard.py) |
| AC2 — LO sees only own files; Manager filtering by that LO matches | Done | `test_dashboard_scoping` |
| AC3 — Aisha (missing-field reason), Luis (selected option), Grace (age in days) | Done | `test_dashboard_lists_personas` (fixtures); **also verified live** against `make demo-reset`'s real seed via `e2e/lo-console/dashboard-tiles.spec.ts` ("Aisha, Luis and Grace show up in the right lists with their reasons") — Aisha's reason "Cannot price: missing Occupancy", Luis's reason "Par" (his selected option's label), Grace 25 days old. **Re-verified in Fix round 1** (cq-025-fix) after the `pre_approvals_sent` fix below: re-ran live against slot 12 post-`make demo-reset` — unchanged, still passing |
| AC4 — tile link opens the matching filtered list with the matching count | **Done, now that CQ-027 is merged.** | Backend: `test_sent_or_later_matches_dashboard` (`backend/app/features/dashboard/tests/test_dashboard.py`) asserts the dashboard's `pre_approvals_sent` tile equals `GET /api/v1/applications?status=sent_or_later`'s `total`, for a Manager and for one LO. Frontend: `Tiles.test.tsx` (hrefs, unit). E2E, live against slot 12 post-`make demo-reset` with the API (8112) and LO console (3112) running: `e2e/lo-console/dashboard-tiles.spec.ts` — "tiles are links with the spec.md query parameters" (all 7 hrefs, incl. `&lo_id=` composition) and the new "each Applications-linked tile opens the list with exactly the tile's count" (navigates all 6 Applications-linked tiles — Applications, Pre-approvals sent, With a property, Awaiting your review, Needs attention, Stale quotes — and asserts the Applications list's `Pagination` total equals the tile's own number). "Clients" is excluded (still CQ-026's stub, out of scope per spec.md); its href is still asserted. |
| AC5 — resolving a flag removes the application from the attention list within one refresh | **Pending — re-check after CQ-028.** Today: resolved directly in the DB (flag + status, since CQ-028's re-verify doesn't exist yet) | `test_attention_list_updates_after_resolve`; `e2e/lo-console/dashboard-tiles.spec.ts` ("resolving a flag directly in the DB…") run live against slot 12 |
| AC6 — responds in < 300 ms with ~200 seeded applications | Done | `test_dashboard_latency` (pytest, generous 1 s CI ceiling); **live measurement** against `make demo-reset`'s 210 applications (26 NeedsAttention, 10-item attention list, 12 Stale, 1 stale-list item): 4 consecutive requests at 30 ms, 22 ms, 20 ms, 19 ms (`curl -w "%{time_total}"`) |
| AC7 — react-doctor passes; tiles/lists keyboard navigable | Done | `npx react-doctor -y --blocking error` on `apps/lo-console`: 86/100, 0 errors (2 pre-existing warnings, both in `features/workspace/`, unrelated to this item); every tile/list row is a `next/link` `<a>` (native keyboard focus + activation, no custom key handling needed). **Re-run in Fix round 1**: 87/100, 0 errors, same 2 pre-existing unrelated warnings |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (dashboard) | `uv run pytest backend/app/features/dashboard` | 7 passed |
| Backend tests (full) | `uv run pytest backend` | 501 passed |
| Seed tests | `uv run pytest seed` | 32 passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | clean |
| Frontend (dashboard) | `pnpm --filter @cq/lo-console run test -- --run src/features/dashboard` | 21 files / 78 tests passed |
| Frontend (full) | `pnpm -r run test` | ui 163, lo-console 78, borrower-portal 95, api-client 2 — all passed |
| Full suite | `make test` | backend 501, seed 32, api-client 2, ui 163, lo-console 78, borrower-portal 95 — all passed (a first `make test` run, executed concurrently with a separate `pnpm -r run test` in another shell while `make demo-reset`'s DB was also being hit, threw 40 fixture-setup `ERROR`s from Postgres connection contention across the two heavy concurrent runs — not a code issue: a clean, non-concurrent re-run passed outright, matching the flake note in `docs/backlog/phase-p5-p6-foundation.md`'s own test log) |
| react-doctor | `npx react-doctor -y --blocking error` (apps/lo-console) | 86/100, 0 errors, 2 pre-existing unrelated warnings |
| e2e (live, slot 12) | `playwright test e2e/lo-console/dashboard-tiles.spec.ts e2e/lo-console/shell.spec.ts --workers=1` against `make demo-reset` + API (8112) + LO console (3112) | 7 passed |

### Fix round 1 test log (cq-025-fix)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests (dashboard + listing) | `uv run pytest backend/app/features/dashboard backend/app/features/applications/listing` | 34 passed (9 dashboard, incl. the 2 new tests; 25 listing) |
| Backend tests (full) | `uv run pytest backend` | 559 passed (a first concurrent run, sharing the shared Postgres/Temporal infra with several other worktree agents active on the same machine at the time, threw the same connection-contention `ERROR`s already noted above; a clean re-run passed outright) |
| Seed tests | `uv run pytest seed` | 32 passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | clean (also regenerated `packages/api-client` twice via `make api-client` -- once after the merge, once after the `LoOption` → `DashboardLoOption` rename) |
| Frontend (dashboard) | `pnpm --filter @cq/lo-console run test -- --run src/features/dashboard` | 27 files / 108 tests passed (full lo-console suite; the merge brought in CQ-027's Applications-list tests alongside dashboard's) |
| react-doctor | `npx react-doctor -y --blocking error` (apps/lo-console) | 87/100, 0 errors, same 2 pre-existing unrelated warnings |
| e2e (live, slot 12), before the `_latest_sent_versions` review fix | `playwright test e2e/lo-console/dashboard-tiles.spec.ts e2e/lo-console/shell.spec.ts --workers=1` against `make demo-reset` + API (8112) + LO console (3112) | 8 passed (incl. the new AC4 "opens the list with exactly the tile's count" test) |
| e2e (live, slot 12), after the review fix | same command, fresh `make demo-reset` | 8 passed |

## Review findings (stage 6)

Fresh-subagent `code-review` (medium effort) on the diff:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | `DashboardPage`'s 30 s background poll (or an `lo_id` filter change) replaced an already-rendered dashboard with the full-page error screen on any transient fetch failure, discarding valid data still on screen | Fixed: `LoadState`'s `ready` variant now carries a `refreshFailed` flag; a failed *refresh* (there's already data) sets that flag and keeps rendering the last good data with a small "Couldn't refresh -- showing the last loaded numbers." notice instead of tearing down the page. Only a failure on the *first* load (no data yet) still shows the full error screen. New test: "a failed poll refresh keeps showing the last loaded dashboard instead of blanking it out" (`DashboardPage.test.tsx`) |
| Low (perf, not a correctness bug) | `_build_attention` issued one extra sequential DB round-trip per attention-list row (`_attention_reason`) instead of batching -- up to 10 extra awaited queries, not exercised by the latency test's all-PRICED fixture | Fixed: `_needs_attention_reasons`/`_latest_sent_versions` batch-fetch every attention-list row's reason data in one `DISTINCT ON` query each (`sqlalchemy.dialects.postgresql.distinct_on`), replacing the per-row awaits. Verified against live `make demo-reset` data (26 NeedsAttention apps, 10-item attention list): dashboard response time dropped from ~100 ms to ~20 ms |
| Info (latent, not reachable today) | `_latest_sent_version`'s "highest version wins" pick would read the wrong (unacted-on) version's reason once a resend can happen after OPTION_SELECTED/INQUIRY, since a resend supersedes the acted-on version with a fresh one whose `borrower_action` is `None` | Not fixed -- CQ-020's resend path isn't wired into a router yet (`portal/reports/versions.py`'s own comment: "CQ-020's future send/resend path"), so this can't be triggered today. Logged as a follow-up below for whichever item wires up resend. |

## Fix round 1 (cq-025-fix, stage-6 major)

Fresh-subagent, PR #16 fix branch `cq-025-fix` off `origin/cq-025-dashboard`, merged forward onto `phase-p5-p6` (now that CQ-027 has landed there).

**Bug:** `dashboard/service.py`'s `_PRE_APPROVAL_SENT_STATUSES` frozenset counted *every* `Stale` application toward the "Pre-approvals sent" tile, including one that aged out straight from `Priced` without ever being sent (CQ-030 spec.md: an application can reach `Stale` either from a sent quote going cold, or from a priced-but-never-sent quote going cold). Spec.md's own definition is "Sent, Viewed, Inquiry, OptionSelected, or **Stale after a send**" -- the tile silently over-counted, and disagreed with CQ-027's own `sent_or_later` filter (E10), which already got this right.

**Fix:**
- `backend/app/features/dashboard/service.py`: removed `_PRE_APPROVAL_SENT_STATUSES`; the `pre_approvals_sent` tile query now applies `applications.listing.service.build_sent_or_later_filter()` directly -- the one function CQ-027 exports specifically so the two definitions can't drift apart again (its own docstring says as much).
- `backend/app/features/dashboard/tests/test_dashboard.py`: `test_dashboard_tiles_match_sql` (AC1) now seeds a Stale-and-sent application (must count) alongside a Stale-and-never-sent one (must not), and its independent SQL oracle encodes "Stale only when a `quote_package_versions` row exists" with its own `EXISTS` subquery (not by importing the app's own filter, to keep the oracle a genuinely separate check).
- New `test_sent_or_later_matches_dashboard`: cross-checks the dashboard's `pre_approvals_sent` tile against `GET /api/v1/applications?status=sent_or_later`'s `total`, for a Manager (sees everyone) and for one LO (sees only their own) -- closes AC3/E10's cross-check.
- `e2e/lo-console/dashboard-tiles.spec.ts`: added "each Applications-linked tile opens the list with exactly the tile's count", closing AC4 for the six tiles that link into the now-real Applications list (Clients still links to CQ-026's stub, out of scope).
- Unrelated but blocking: once CQ-027's `applications.listing` router is also mounted, its `LoOption` FastAPI schema collided by name with this feature's own `LoOption` schema, so `openapi-typescript` fell back to the fully-qualified component name and broke the frontend's `components["schemas"]["LoOption"]` re-export (`tsc` failure). Renamed this feature's schema to `DashboardLoOption` (backend `schemas.py`/`service.py`; frontend `dashboard/api.ts`'s `LoOption` type alias now points at `DashboardLoOption` -- every other consumer of the frontend's own `LoOption` name is unaffected).

**Merge:** `cq-025-fix` (from `origin/cq-025-dashboard`) merged `origin/phase-p5-p6` per the coordinator's conflict rules -- `graphify-out/*` took theirs then `graphify update .`; `packages/api-client/*` took theirs then `make api-client` (twice, after the `LoOption` rename); `core/registry.py` kept both `FEATURE_ROUTERS` entries; `(staff)/page.test.tsx` and `e2e/lo-console/shell.spec.ts` kept both sides' stub-row removals (auto-merged cleanly for the `.spec.ts`, one comment-only conflict in the `.test.tsx`).

### Review round 1 (fresh subagent, cq-025-fix)

Fresh-subagent `code-review` (medium effort) on the `cq-025-fix` diff (dashboard `service.py`/`schemas.py`/`tests/test_dashboard.py`, `e2e/lo-console/dashboard-tiles.spec.ts`, `apps/lo-console/src/features/dashboard/api.ts`):

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `_latest_sent_versions` (`service.py`) picked the "latest sent" `QuotePackageVersion` per application by `version DESC` alone (via `DISTINCT ON (application_id)`), not by `sent_at`. `quote_packages.application_id` has no unique constraint, so if an application ever ended up with more than one `QuotePackage` row, an older package's higher version number would win over a newer package's lower version number -- picking the wrong (stale) `borrower_action`/reason. `_build_stale`'s own `latest_sent_at` subquery already defines "latest sent" as `MAX(sent_at)`, so the same file computed it two different, inconsistent ways. | Fixed: `_latest_sent_versions` now orders by `sent_at DESC` first (version as a same-`sent_at` tiebreaker), matching `_build_stale`'s definition. Not reachable via today's application code (one `QuotePackage` per application; CQ-020's resend path adds a version to the *same* package, not a new one, per the model's own docstring) -- fixed anyway since it's a one-line, zero-risk change and the two "latest sent" definitions should not disagree. New test: `test_attention_reason_uses_the_most_recently_sent_version` (two `QuotePackage` rows for one application, older-but-higher-version vs. newer-but-lower-version; verified the test fails against the pre-fix ordering and passes against the fix). |

## How to test manually

1. `bash scripts/worktree-env.sh 12 && make demo-reset`
2. Start the API from the repo root: `uv run uvicorn app.main:app --app-dir backend --port 8112` (not `cd backend` first -- `Settings`' `env_file=".env"` resolves relative to cwd, so it must run from the repo root to find the root `.env`).
3. Start the LO console: `pnpm --filter @cq/lo-console exec next dev -p 3112`.
4. Sign in as `riley.admin@clearquote-demo.test` (password `.env`'s `SEED_STAFF_PASSWORD`; OTP from Mailpit at `http://localhost:8025`). The dashboard loads at `/` with 7 tiles, the three lists and (as an Admin) the LO filter above the tiles.
5. `curl -b <cookie jar> http://localhost:8112/api/v1/dashboard | python3 -m json.tool` to inspect the raw response, or time it with `curl -w "%{time_total}\n" -o /dev/null ...`.
6. `LO_BASE_URL=http://localhost:3112 PORTAL_BASE_URL=http://localhost:3212 npx playwright test e2e/lo-console/dashboard-tiles.spec.ts e2e/lo-console/shell.spec.ts --workers=1` (needs `SEED_STAFF_PASSWORD`/`DATABASE_URL` exported from `.env` into the shell running Playwright).

## Follow-ups

- ~~CQ-027: once the real Applications list exists, re-run AC4's Playwright
  assertion to also check the list shows exactly the tile's count~~ --
  **Done in Fix round 1** (cq-025-fix): `e2e/lo-console/dashboard-tiles.spec.ts`
  now navigates each Applications-linked tile and asserts the list's total.
- CQ-028: once the real re-verify endpoint exists, re-run AC5 through it
  instead of a direct DB update.
- Whichever item wires up CQ-020's quote-package resend path: `_latest_sent_versions`
  now orders by `sent_at DESC` (Fix round 1, review finding), so it always
  reflects the version that was *actually sent* most recently -- but a
  resend still opens a new `QuotePackageVersion` whose `borrower_action` is
  `None` until the borrower acts on it again. Once a resend can happen
  after OPTION_SELECTED/INQUIRY, that fresh, unacted-on version becomes the
  most-recently-sent one and will silently revert the attention-list
  reason to the generic fallback text ("Selected an option" / "Borrower
  has a question") until the borrower re-acts. Fixing this still needs
  picking the *latest version with a non-null `borrower_action`* (not
  simply the latest-sent version) -- left as a follow-up since it isn't
  reachable today (original code-review finding, still open).
- `apps/lo-console/src/app/(staff)/page.test.tsx` is shared scaffolding
  from the P5/P6 foundation stub (it tests every `(staff)` reserved route
  in one file); this item removed only the Dashboard row and left the
  other stub-page rows for CQ-026/027/029 to remove themselves when they
  land -- as expected, the cq-025-fix merge with `phase-p5-p6` (CQ-027
  already merged there) hit exactly this conflict, a comment-only merge,
  not a real regression.
- `e2e/lo-console/shell.spec.ts`'s "the nav links go to the stub pages"
  test (owned by the foundation, not this item) asserted the Dashboard nav
  link still showed the CQ-025 stub text; updated it in place (small
  necessity, AGENTS.md) to assert the real dashboard heading instead once
  navigated to `/`, since the stub it was testing no longer exists.
