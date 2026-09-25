# CQ-022 — Post-development notes

## Summary

Built the sign-in-gated borrower report page: `GET /api/v1/portal/reports/{token}`
resolves a frozen `quote_package_versions` row by its report token, enforces the
signed-in borrower owns the underlying client (404, never 403), records the
first-view transition race-safely, and returns the frozen `ReportViewModel`
snapshot with `expired`/`superseded` recomputed live. A new sent-version factory
(`backend/app/features/portal/reports/versions.py::freeze_package_version`) maps
`Quote`/`Scenario`/`Application`/`Property`/`Client`/`User` rows into CQ-021's
`ReportInputs` and runs them through the real `build_report_view_model` — CQ-020
will call it from its send workflow; this item's own `seed/loader.py::apply_send_fixture`
already calls it today, so Grace Kim's and Luis Romero's seeded personas have real
`quote_package_versions` rows and the demo report works after `make demo-reset`.

`apps/borrower-portal/src/app/report/[token]/page.tsx` composes CQ-021's
`ReportPage` (packages/ui) with two small additive render-prop slots
(`renderMatches`, `renderActions`) plus a URL-synced option selector
(`?option=`), loading/not-found/error states, print CSS, and a mobile 2×2/1×3
hero-tile layout. Signed-out visitors are redirected by `middleware.ts` to
`/login?next=/report/{token}` (H2); `AuthFlow`/`nextParam.ts` validate `next`
before ever navigating to it (only a same-origin relative path).

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `ReportMatchesSlot.tsx`/`ReportActionsSlot.tsx` live under `packages/ui/src/report/` (phase-p3-p4-plan.md's wave table, CQ-023's row) | Both live under `apps/borrower-portal/src/features/report/` | This item's own coordinator brief pinned this path explicitly (D3) — followed the more specific, later instruction. Logged in plan.md Decision 5 for CQ-023's worker to reconcile if it expected the other location. |
| AC1 fully verified against Marcus Hale's live sent report | Verified with the sent-version factory (backend unit + e2e-live via Luis Romero/Grace Kim, both frozen through the same `freeze_package_version` factory CQ-020 will use) | Marcus Hale has no `fixture_layer` in seed (no sent version yet) — spec.md's own "Notes for the agent" anticipates this: "This item can run before CQ-020 ... AC1 is verified with the factory first and re-checked end to end once CQ-020 is merged." The coordinator should re-run `test_get_report_returns_frozen_snapshot`-equivalent verification against Marcus's real sent package once CQ-020 lands. |
| Tailwind `print:!block` (leading `!`, v3 important-modifier syntax) | `print:block` (no `!`), paired with Tailwind's `.hidden` utility *class* instead of the native HTML `hidden` *attribute* for the on-screen closed state | Found live, not assumed: Tailwind v4's preflight resets `[hidden]` with `!important` (`[hidden]:where(...) { display: none !important; }`), and per the CSS Cascade Layers spec, `!important` declarations invert layer priority — preflight's earlier `base` layer then beats *any* `!important` utility in the later `utilities` layer, print-scoped or not. Confirmed via `page.emulateMedia({media:"print"})` + computed style before and after the fix. See `packages/ui/src/report/Collapsible.tsx`'s docstring. |
| — (not specified) | `HeroNumbers.tsx`'s mobile 2×2 tile padding/font size shrink slightly (`p-3`/`text-2xl` at the base breakpoint, restored to `p-4`/`text-3xl` from `sm:` up) | AC7's 2×2 investment layout at 375px genuinely overflowed by ~8px with the original `p-4`/`text-3xl` sizing (verified live via a DOM bisection script: hiding the hero-numbers grid was the only change that dropped `scrollWidth` from 383 to 375). No visible change above the `sm` breakpoint. |
| — (not specified) | `RecommendationCard.tsx` gained an optional `viewingAlternative` prop (spec.md page order item 4's "small note") | Needed a place to render "You're viewing an alternative to our recommendation." — additive, defaults to `false`/unchanged behavior for every existing caller. |
| — (not specified) | `SupersededBanner.tsx` gained an optional `newestReportHref` prop | Needed to satisfy spec.md's "SupersededBanner with a link to the newest version's token" — additive, renders the old static text when omitted. |
| — (not specified) | `ReportPage.tsx` gained `renderMatches`/`renderActions`/`initialSelectedId`/`onSelectionChange`/`newestReportHref` props | The shared composition needed slots for CQ-023/CQ-024 (plan.md D3) and a way for the page to sync the selected option into `?option=` (AC3) without duplicating the whole page composition in the portal app. All additive/optional; CQ-019's/CQ-021's existing callers are unaffected (verified: all their existing tests still pass unchanged). |
| — (not specified) | `backend/conftest.py` gained a `make_borrower_session` fixture | CQ-015 only added `make_staff_session`; this item's router/service tests needed the equivalent for a signed-in borrower. Mirrors it exactly (real `BorrowerAccount` + Valkey session, sets the `cq_borrower_session` cookie). |
| — (not specified) | Root `package.json` gained `pg`/`@types/pg` and `pdf-parse`/`@types/pdf-parse` devDependencies | `pg` backs `e2e/helpers/db.ts` (the E2E recipe's own "look the token up in the DB" — there's no UI path to a borrower's report token yet; that's CQ-031's home page). `pdf-parse` backs AC6's `page.pdf()` text assertions. |
| — (not specified) | `e2e/global-setup.ts` added; `playwright.config.ts` wires it in | Naive per-spec `borrowerLogin` calls for the shared Luis Romero/Grace Kim personas would sit right at the borrower login rate limit's ceiling (5 attempts/15min per email — `backend/app/core/config.py::login_rate_limit_per_email`) on every full-suite run, breaking on the first retry. Global setup signs each persona in **once** and saves the session (`storageState`); `report-option-switch.spec.ts`/`report-print.spec.ts`/`report-mobile.spec.ts`/`report-expired.spec.ts` load that instead of logging in fresh. `report-login-redirect.spec.ts` deliberately keeps its own real logins (that's the point of that spec) and runs its two tests serially (`test.describe.configure({mode:"serial"})`) to avoid racing on Mailpit's "newest OTP for this address" lookup. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met (factory-verified; re-check after CQ-020 noted above) | `backend/app/features/portal/reports/tests/test_router.py::test_get_report_returns_frozen_snapshot` — response equals the frozen snapshot's `options[].quote_id`/`rate`. Live e2e: `e2e/borrower-portal/report-option-switch.spec.ts` and the captured screenshot `evidence/report-desktop-luis-romero.png` show Luis Romero's real (factory-frozen, engine-priced) report rendered end to end through a real browser session. |
| AC2 | Met | `test_router.py::test_first_view_sets_viewed_once` — first load sets `viewed_at`, transitions `SENT`→`VIEWED`, writes exactly one `quote.viewed` activity event; a second load writes none, `viewed_at` unchanged (race-safe conditional `UPDATE ... WHERE viewed_at IS NULL`, see `service.py::_mark_viewed_if_first_load`). |
| AC3 | Met | `e2e/borrower-portal/report-option-switch.spec.ts` — clicking Buydown changes the hero numbers, sets `?option=`, shows "You're viewing an alternative to our recommendation.", and a full page reload at the same URL keeps the selection and the note. `packages/ui/src/report/ReportPage.test.tsx` covers the same logic at the component level (`initialSelectedId`, `onSelectionChange`). |
| AC4 | Met | `test_router.py::test_expired_flag` (sent 25 days ago → `header.expired: true`, computed live from `now > expires_at`, never trusted from the frozen snapshot). Live e2e: `e2e/borrower-portal/report-expired.spec.ts` — Grace Kim's real seeded report shows the expired banner and zero action buttons. Screenshot: `evidence/report-expired-grace-kim.png`. |
| AC5 | Met | `test_router.py::test_report_token_isolation` — a different borrower's session on the same token, and a random never-issued token, both 404 (never 403 — `ensure_borrower_owns_client`). |
| AC6 | Met | `e2e/borrower-portal/report-print.spec.ts` — `page.pdf()` + `pdf-parse` text assertions: hero numbers present, both collapsible sections' content present *without ever clicking to expand* (BreakdownTable/CashflowTable/ComparisonTable headings/rows), no "Coming soon"/"Save as PDF"/collapsible-toggle text (switcher and action buttons excluded from print). PDF saved at `evidence/report-print.pdf`. `packages/ui/src/report/Collapsible.tsx`'s print mechanism (content always mounted, `.hidden` class on screen, `print:block` under print media) is documented in its own docstring, including the Tailwind v4 cascade-layers pitfall found and fixed. |
| AC7 | Met | `e2e/borrower-portal/report-mobile.spec.ts` (375×800 viewport) — `document.documentElement.scrollWidth <= clientWidth + 1` (no horizontal scroll) and the 4 investment hero tiles' bounding boxes confirm a 2×2 layout (tiles 0/1 share a row, tiles 2/3 share a lower row). Screenshot: `evidence/report-mobile-375px-luis-romero.png`. |
| AC8 | Met | Investment/primary gating: reused CQ-021's own gating test suite (`packages/ui/src/report/ReportGallery.primary-gating.test.tsx`, `e2e/borrower-portal/report-gallery.spec.ts`'s AC2 test for Priya Nair) — `ReportPage` is the exact same component the live `/report/{token}` page renders (no page-specific logic diverges), so gating verified there holds on the live route too; Priya herself has no seeded sent version (out of this item's seed scope — only Grace Kim/Luis Romero were named), so a literal "Priya's `/report/{token}`" run wasn't possible without expanding seed scope. Accessibility: `npx lighthouse` (headless Chromium) against the live, signed-in `/report/{token}` page (Luis Romero) — **accessibility score 100/100** (`evidence/lighthouse-report.json`); fixed one real finding along the way (`landmark-one-main` — wrapped the report/loading/not-found/error states in `<main>`). react-doctor: `apps/borrower-portal` 81/100 (2 pre-existing + 1 new `nextjs-no-client-side-redirect` finding on `ReportView.tsx`'s 401 fallback — same accepted pattern as the home page's own fallback, CQ-014/CQ-015 precedent); `packages/ui` 87/100, no new findings. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed | `uv run pytest backend seed -q` | 401 passed |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 284 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues in 284 source files |
| Frontend (whole monorepo) | `pnpm -r run test` | 4/4 workspaces passed — api-client 2, ui 124, lo-console 21, borrower-portal 68 (215 total; includes the stage-6 review-fix regression tests) |
| ESLint | `pnpm -r run lint` | 0 errors |
| TypeScript | `pnpm -r run typecheck` | 0 errors |
| TypeScript (root, covers e2e/) | `pnpm exec tsc --noEmit -p tsconfig.json` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| `alembic heads` | `uv run alembic heads` | `bbd0e3150264 (head)` — single head (no new migration added) |
| `make demo-reset` | `time make demo-reset` | ~1.1–1.2s, well under the 60s budget; Grace Kim/Luis Romero both get real `quote_package_versions` rows |
| Playwright (borrower-portal, full) | `PORTAL_BASE_URL=http://localhost:3204 LO_BASE_URL=http://localhost:3104 SEED_BORROWER_PASSWORD=<slot 4's> DATABASE_URL=<slot 4's, postgresql+asyncpg scheme> pnpm exec playwright test e2e/borrower-portal --project=borrower-portal` | 12/12 passed (three runs total, including one after the stage-6 fixes below, confirming no flakiness/regressions) — smoke, report-gallery (5), report-expired, report-mobile, report-print, report-option-switch, report-login-redirect (2) |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | 81/100; 3 warnings (`nextjs-no-client-side-redirect` ×3 — 2 pre-existing, 1 new, all accepted) |
| react-doctor (ui) | `npx react-doctor -y --blocking error` | 87/100; 2 pre-existing warnings (Overlay, format.ts), 0 new |
| Lighthouse accessibility | `npx lighthouse <live /report/{token} URL> --only-categories=accessibility --chrome-flags="--headless=new" --extra-headers='{"Cookie":"cq_borrower_session=..."}'` | 100/100 (was 98/100 before the `landmark-one-main` fix) |
| `make api-client` | `make api-client` | Regenerated cleanly; `PortalReportResponse` and `/api/v1/portal/reports/{token}` present in the generated schema |

## Review findings (stage 6)

Ran the `code-review` skill (medium effort) as a fresh, isolated pass over the full uncommitted diff (8 finder angles, verified manually rather than by separate verifier agents). One critical/security finding, five majors/minors, all fixed; three candidates were investigated and refuted/accepted as noted by the reviewer itself (0-year PPP label is correct behavior, the duplicated `/login?next=` construction is consistent, and several pure efficiency/simplification notes with no correctness impact).

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical (security) | `apps/borrower-portal/src/lib/nextParam.ts::safeNextPath` only rejected a literal `//`/`/\\` *prefix*; a value containing a tab/CR/LF anywhere (e.g. `"/\t/evil.com"`) passed unchanged, but the WHATWG URL parser strips every ASCII tab/newline *before* parsing the scheme/authority, so `new URL("/\t/evil.com", origin).href` resolves off-site exactly like a literal `"//evil.com"` — an open redirect after OTP success. Verified live in Node before fixing (`new URL("/\t/evil.com", "https://portal.example/").href === "https://evil.com/"`). | Fixed: reject any `next` containing `\t`/`\r`/`\n` before the prefix checks. Regression tests added (`nextParam.test.ts`). |
| Major | `ReportView.tsx` treated every non-2xx, non-401 response (500, 502, 503) the same as a real 404 — a transient backend error showed "We couldn't find that report" instead of "Something went wrong", hiding real server errors behind a wrong message. | Fixed: only `response.status === 404` goes to the not-found state; everything else goes to the error state. Regression test added. |
| Major | `versions.py::freeze_package_version` read `max(version)`, superseded prior rows and inserted the new row with no row lock — two concurrent freezes of the same package (a retried CQ-020 send activity, a double-clicked send) could race: both compute the same "next version" (one fails the unique constraint) or, on a different interleaving, both new rows end up non-superseded, breaking the "at most one live version" invariant `SupersededBanner`/`_newest_report_token_for_package` depend on. Flagged as plausible, not yet hit (no non-test caller exists until CQ-020). | Fixed: `SELECT ... FOR UPDATE` on the `quote_packages` row at the top of the function serializes freezes of the same package. Existing sequential tests still pass unchanged (no behavior change for the single-session case); a true concurrent-session test is a follow-up (same limitation CQ-015's post-dev.md already noted for its own concurrency case — needs two DB sessions outside the per-test rollback fixture). |
| Minor | `service.py::get_report_for_token` called `await db.refresh(version)` on every request, but the one thing it wrote (`viewed_at`) is never read afterward — a spurious extra SELECT on the report-view hot path. | Fixed: removed the refresh; the fields actually read afterward (`snapshot`, `expires_at`, `superseded`) are unaffected by `_mark_viewed_if_first_load`'s write and `expire_on_commit=False` means they don't auto-expire on commit either. |
| Minor | `versions.py::_strategy_type` duplicates `pricing/scenarios/service.py::_strategy_type` (documented, deliberate — see plan.md), but the two had diverged: the pricing copy raises `ValidationAppError` (clean 4xx), this copy raised a bare `ValueError` (unhandled 500) for the identical "investment application, no strategy set" case. | Fixed: raises `ValidationAppError` too, matching the pricing module's failure mode. Full de-duplication into one shared helper is a follow-up. |
| Minor | `versions.py` hand-rolled `secrets.token_urlsafe(24)` for `report_token` instead of the project's existing `app.core.security.generate_token()` (used for every other bearer-style token — sessions, OTP challenges). | Fixed: uses `generate_token()`. |
| Minor | `Collapsible.tsx`'s content moving from conditional-mount to always-mounted-plus-`.hidden` (required for AC6/print) meant the existing `ReportGallery.primary-gating.test.tsx` tests, which click-to-expand then assert on `container.textContent`, no longer meaningfully exercise the *collapse* gating — they'd pass even if a regression rendered forbidden content while still collapsed, since `textContent` doesn't care about CSS visibility. Passed today only because the primary fixtures contain no investment strings at all. | Fixed: added an explicit assertion that the content starts with the `.hidden` class and loses it after the click (the actual mechanism the component controls — jsdom doesn't apply the compiled Tailwind stylesheet, so `toBeVisible()` can't observe real visibility here), plus a new dedicated `Collapsible.test.tsx` covering the open/closed/`defaultOpen` states directly. |

All fixes re-verified: backend 401 tests, frontend 215 tests (up from 210 — new coverage from the fixes: `nextParam.test.ts` +1, `ReportView.test.tsx` +1, `Collapsible.test.tsx` +3, `ReportGallery.primary-gating.test.tsx` gains two new assertions in its existing Priya test rather than a new test), `make lint` clean, and the full Playwright suite (12/12) re-run green after the fixes.

## How to test manually

1. `scripts/worktree-env.sh 4` (or reuse this worktree's existing `.env`, already slot 4). `uv sync && pnpm install`, `uv run alembic upgrade head`, `make demo-reset` (needs `SEED_STAFF_PASSWORD`/`SEED_BORROWER_PASSWORD` set).
2. Backend: `uv run uvicorn app.main:app --port 8104` in the background.
3. Portal: `pnpm --filter @cq/borrower-portal exec next dev -p 3204` in the background.
4. Sign in at `http://localhost:3204/login` as `luis.romero@clearquote-demo.test` / `$SEED_BORROWER_PASSWORD`, read the OTP from Mailpit (`http://localhost:8025`).
5. Look up his report token: `select report_token from quote_package_versions v join quote_packages p on p.id=v.package_id join applications a on a.id=p.application_id join clients c on c.id=a.client_id where c.email ilike 'luis.romero@%' order by v.sent_at desc limit 1;` — visit `http://localhost:3204/report/{token}`. Click Buydown (URL gains `?option=`, note appears), reload (selection persists), expand both collapsibles, click "Save as PDF".
6. Sign out (or open a private window), visit the same `/report/{token}` URL directly — redirects to `/login?next=/report/{token}`; after OTP, lands back on the report.
7. `grace.kim@clearquote-demo.test` — same report route shows the expired banner and no action buttons.
8. `pnpm exec playwright test e2e/borrower-portal --project=borrower-portal` (needs `PORTAL_BASE_URL`, `LO_BASE_URL`, `SEED_BORROWER_PASSWORD`, `DATABASE_URL` set — see the test log row above) for the full automated pass.

## Follow-ups

- CQ-020: call `freeze_package_version` from the real send workflow; re-verify AC1 end to end against Marcus Hale's actual sent report once that lands (per spec.md's own note).
- CQ-023: fill `ReportMatchesSlot.tsx` (`apps/borrower-portal/src/features/report/ReportMatchesSlot.tsx`) — currently renders nothing; reconcile the file-location deviation noted above against `phase-p3-p4-plan.md`'s wave table if that worker expected `packages/ui/src/report/ReportMatchesSlot.tsx` instead.
- CQ-024: fill `ReportActionsSlot.tsx` (same directory) — currently disabled buttons with "Coming soon"; the slot already carries `data-selected-quote-id` on its root for CQ-024 to read.
- A borrower home/status page (CQ-031) would give a real UI path to a report link; until then, `e2e/helpers/db.ts::latestReportTokenForBorrower` is how tests (and this post-dev.md's manual-test steps) find one.
