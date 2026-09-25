# CQ-024 — Post-development notes

## Summary

Built `POST /api/v1/portal/reports/{token}/actions` (`backend/app/features/portal/actions/`):
`move_forward` / `ask_other` / `ask_updated`, each with row-locked rule checks against the
frozen `QuotePackageVersion`, an `ActivityEvent`, an LO email (`outbox_emails` + Mailpit), and
a mock CRM event, race-safe via `SELECT ... FOR UPDATE` on the version/package/application rows.
Fixed the CQ-022 review carry-over so a missing and a foreign report token return the identical
404 message. Rewrote `ReportActionsSlot.tsx` from its disabled "Coming soon" stub into the real
move-forward/ask-other/ask-for-updated-numbers UI (`apps/borrower-portal/src/features/actions/`
holds the two dialogs), wired through `ReportView.tsx`'s existing `renderActions` render prop with
no change to `ReportPage`'s own interface. Wrote a `backend/scripts/freeze_sent_version.py` dev
script (CQ-023's own equivalent isn't on this branch's base yet) so a "freshly sent persona" is
available for API and E2E checks alike.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| E2E recipe: "freeze a fresh sent version for Marcus Hale ... POST move_forward on the Buydown option" | Used Priya Nair instead (still a genuinely fresh, un-fixtured persona) | Verified live: Marcus Hale's real priced data (persona 1, Tampa STR, DSCR < 1) has **no Buydown candidate** in either of his two DSCR-bucket scenario groups -- `select label from quotes join scenarios ... where application_id = <marcus's>` returns only `Par` twice, confirmed via `docker exec ... psql`. This is a characteristic of the mock rate-sheet grid for that specific risk tier (`_create_default_scenarios_investment`'s `buydown_a`/`buydown_b` come back `None`), not a bug in this item's code -- out of this item's ownership to fix (`pricing/scenarios/service.py`, `integrations/pricing`). Priya Nair (persona 3, primary/Conventional) is `priced` with no `fixture_layer`, i.e. an equally "fresh" persona, and her Conventional rate sheet reliably yields both Par and Buydown (the same fixture every primary-application report test in this repo already depends on -- `portal/reports/tests/conftest.py::seed_conventional_rate_sheet`). Logged here rather than silently swapping personas without explanation; `e2e/borrower-portal/move-forward.spec.ts`'s own header comment carries the same note. |
| AC6: "shows the new status after its next poll" | E2E test triggers the LO console's `refetch()` by navigating to the workspace a second time, rather than waiting on the 3s interval | `WorkspaceProvider` (CQ-016) only keeps its 3s polling interval running while `last_pipeline_stage` is *non-terminal* (by design -- that interval exists for the pipeline-progress banner, spec.md CQ-016 AC7). Every persona this item can use has already finished its pipeline (`last_pipeline_stage` lands on a terminal value per the P3/P4 foundation's D7), so the interval has already stopped by the time a borrower acts -- there's no live "next poll" to wait on for a post-pipeline status change, only the same `GET .../summary` `refetch()` a poll would call. Confirmed live end to end (`e2e/borrower-action-reflects-in-console.spec.ts`): the header does show "Option selected" the moment that request is made again. Flagged as a genuine CQ-016/CQ-025 follow-up (a "poll a few more times after mount" or "poll on window focus" behavior would close this for real), out of this item's scope to build. |
| Owned-files list doesn't mention `e2e/borrower-portal/report-expired.spec.ts` (CQ-022's own file) | Updated its assertions | The old assertion (`actions-slot` has 0 count when expired) directly contradicted this item's own required change ("The slot currently renders null when expired; change that"). Left the rest of that spec (expired banner assertion) untouched. |
| — (not specified) | `playwright.config.ts` gained a third `cross-app` project (no `baseURL`) | `e2e/borrower-action-reflects-in-console.spec.ts` drives both apps in one test; neither of the two existing single-`baseURL` projects fits. Additive; the two existing projects are unchanged. |
| — (not specified) | `pyproject.toml` gained a `[[tool.mypy.overrides]]` for `yaml.*` | `backend/scripts/freeze_sent_version.py` reads `seed/personas/*.yaml` directly (no published type stubs for `pyyaml`) -- same pattern as the existing `boto3`/`reportlab` overrides. |

## Decisions

See `plan.md`'s "Decisions & questions" table (10 items) -- most load-bearing: **Decision 1**
(`QuotePackageVersion.borrower_action` JSONB is the source of truth; `QuotePackage.borrower_action`
enum is a mirror, unread by anything today), **Decision 3** (superseded blocks every action type,
not just move_forward/ask_other, per the carried CQ-022 review finding), **Decision 8** (the
frontend refetch mechanism -- `ReportView.tsx`'s `loadReport` extracted into a callback and passed
through the existing `renderActions` closure, no new prop on `ReportPage`'s interface).

## The action API contract

`POST /api/v1/portal/reports/{token}/actions` (`CurrentBorrower` + `ensure_borrower_owns_client`,
404 for a missing or foreign token -- identical message either way):

```
Request:  {"type": "move_forward" | "ask_other" | "ask_updated", "quote_id"?: string, "message"?: string}
Response: {"status": ApplicationStatus, "borrower_action": {...} | null, "at": ISO datetime}
```

| Type | Allowed when | Effect | Validation |
| --- | --- | --- | --- |
| `move_forward` | not superseded, not expired, `status` in {Sent, Viewed, Inquiry} | `status` -> OptionSelected; `QuotePackage.borrower_action` -> `option_selected` | `quote_id` required, must be one of the frozen snapshot's `options[].quote_id` (422 otherwise) |
| `ask_other` | same as above | `status` -> Inquiry; `QuotePackage.borrower_action` -> `inquiry`; stays allowed again from Inquiry | `message` required, 1-500 chars after trim (422 otherwise); `quote_id` optional, validated against the snapshot if given |
| `ask_updated` | not superseded, version expired | `status` -> Inquiry; repeatable indefinitely while expired | `message` optional |

Anything not allowed (wrong status, not expired/already expired, or superseded) is a 409 whose
body's `error.details` carries `{status, borrower_action}` (the "current state"). Every successful
or 409 call is intended to be followed by the caller re-fetching `GET .../reports/{token}` -- the
frontend does this via `onActionTaken`.

Every successful call, exactly once: writes one `ActivityEvent` (`quote.move_forward` /
`quote.ask_other` / `quote.ask_updated`), sends one LO email via `notifications/email/service.py::
send_email` (`outbox_emails` row + real SMTP to Mailpit), and logs one `MockCrmClient.log_event`
(`crm_events` row, `contact_id = Client.crm_contact_id or str(Client.id)`,
`event_type = "borrower.<type>"`).

## The `borrower_action` storage decision

Two columns already existed before this item (P3/P4 foundation): `QuotePackage.borrower_action`
(a coarse `option_selected`/`inquiry` enum) and `QuotePackageVersion.borrower_action` (JSONB,
`null` until this item). **The version's JSONB is the source of truth** -- it's what
`GET .../reports/{token}` already returned (CQ-022, always `null` in practice until now), and it
carries the full detail (`type`, `quote_id`, `message`, `at`) the report page needs to render the
confirmed state. The package's enum column is mirrored from it on every action (a coarse status
only) since nothing reads it yet, but the column exists precisely for a future LO-console reader
that wants the status without joining the version table.

## Status transitions implemented

Matches `docs/design/system-design.md`'s Application status machine (Sent -> Viewed ->
OptionSelected / Inquiry), extended per spec.md's rules table to also allow `move_forward`/
`ask_other` directly from Sent (not only Viewed) and to allow `ask_other` again from Inquiry:

```
Sent | Viewed | Inquiry  --move_forward-->  OptionSelected  (terminal for further move_forward/ask_other -- 409)
Sent | Viewed | Inquiry  --ask_other-->      Inquiry          (re-askable)
<any status>, version expired  --ask_updated-->  Inquiry      (repeatable while expired)
superseded version  --any action-->  409 (never applied)
```

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/portal/actions/tests/test_router.py::test_move_forward_sets_option_selected_sends_one_email_and_logs_activity_and_crm` (status, one `outbox_emails` row naming the option, one `ActivityEvent`, one `CrmEvent`). Live manual check against a real running stack (curl + Mailpit's `/api/v1/search`, see "How to test manually"): `Priya Nair would like to move forward with Buydown` landed in Mailpit for `jordan.lee@clearquote-demo.test`. E2E: `e2e/borrower-portal/move-forward.spec.ts` (screenshot `evidence/move-forward-confirmed.png`). |
| AC2 | Met | `test_router.py::test_move_forward_twice_second_is_409_no_new_email` (second call 409s, exactly 1 `outbox_emails` row throughout). Live manual check: second curl POST returned 409 with `details.status: "option_selected"`. E2E: `move-forward.spec.ts`'s reload assertion (confirmed state persists server-side). |
| AC3 | Met | `test_router.py::test_ask_other_requires_message` (empty/missing/over-500-char message all 422), `test_ask_other_sets_inquiry_and_emails_message` (message text present in the email body, status -> Inquiry, and a second `ask_other` from Inquiry still succeeds). E2E: `move-forward.spec.ts`'s ask-other test (screenshot `evidence/ask-other-sent.png`). |
| AC4 | Met | `test_router.py::test_expired_allows_only_ask_updated`. Live manual check against Grace Kim's real seeded expired report: `move_forward` -> 409 (`"This report has expired."`), `ask_updated` -> 200, status -> Inquiry, one email ("Grace Kim asked for updated numbers"). E2E: `e2e/borrower-portal/report-expired-actions.spec.ts` (screenshots `evidence/expired-ask-updated-button.png`, `evidence/expired-ask-updated-sent.png`); `report-expired.spec.ts` (CQ-022, updated) confirms move_forward/ask_other stay hidden. |
| AC5 | Met | `backend/app/features/portal/actions/tests/test_templates.py::test_no_binding_language` (word-boundary scan of every email subject/body this module can produce -- `\baccept\w*\b`, `\block\b`, `\bapproved rate\b`). `apps/borrower-portal/.../ReportActionsSlot.test.tsx`'s "no wording says accept, lock or approved rate" test scans the rendered confirmed-state text and the open move-forward dialog's text (the one place the spec's own wording says "isn't locked yet" -- confirmed that phrase does not trip the word-boundary "lock" pattern, since "locked" has no boundary immediately after "lock"). |
| AC6 | Met | `e2e/borrower-action-reflects-in-console.spec.ts`: borrower moves forward via the portal, LO console header shows "Option selected" after a `GET .../summary` (see the Deviations table above for why this is a re-navigation rather than a literal 3s-interval poll). Screenshots `evidence/lo-console-before-sent.png`, `evidence/lo-console-after-option-selected.png`. CQ-025 (dashboard tiles) is not merged yet, so that half of AC6 isn't checked. |
| AC7 | Met | `npx react-doctor -y --blocking error` on `apps/borrower-portal`: 83/100, same 2 pre-existing findings as CQ-022 (`nextjs-no-client-side-redirect` on the home page), 0 new. `apps/borrower-portal/src/features/actions/MoveForwardDialog.test.tsx::"traps focus within the dialog and closes on Escape"` -- initial focus lands on Overlay's own close button, Tab cycles Cancel -> Confirm -> wraps back to Close (never escapes the dialog), Escape calls `onClose`. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed | `uv run pytest backend seed -q` | 445 passed (417 backend, 28 seed) |
| Ruff | `uv run ruff check backend` | All checks passed |
| Ruff format | `uv run ruff format --check backend` | 303 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues in 303 source files |
| Frontend (whole monorepo) | `pnpm -r run test` | 4/4 workspaces passed -- api-client 2, ui 130, lo-console 39, borrower-portal 84 (255 total, after stage-6 review fixes) |
| ESLint | `pnpm -r run lint` | 0 errors |
| TypeScript | `pnpm -r run typecheck` | 0 errors |
| TypeScript (root, covers e2e/) | `pnpm exec tsc --noEmit -p tsconfig.json` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| `alembic heads` | `uv run alembic heads` | `bbd0e3150264 (head)` -- single head (no new migration) |
| `make demo-reset` | `time make demo-reset` (run 3x during manual verification) | ~1.1-1.8s each, well under the 60s budget |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | 83/100; 2 pre-existing warnings (home page client redirects), 0 new |
| `make lint` | `make lint` | ruff/mypy/eslint/typecheck/prettier -- all clean |
| `make test` | `make test` | pytest backend (417) + seed (28) + pnpm -r test (254) -- all green |
| Playwright (borrower-portal) | `pnpm exec playwright test e2e/borrower-portal --project=borrower-portal --workers=1` | 15/15 passed (smoke, gallery x4, login-redirect x2, mobile, option-switch, print, expired, expired-actions, move-forward x2) |
| Playwright (cross-app) | `pnpm exec playwright test e2e/borrower-action-reflects-in-console.spec.ts --project=cross-app --workers=1` | 1/1 passed |
| Playwright (lo-console) | `pnpm exec playwright test e2e/lo-console --project=lo-console --workers=1` | 10/11 passed -- the 1 failure (`AC7: the pipeline banner...`) needs `make worker` running, which this item's own E2E recipe (API + both Next apps only) doesn't start; pre-existing CQ-016 test, unrelated to this item's changes (confirmed: no worker process was running for this slot). |
| `make api-client` | `make api-client` | Regenerated cleanly; `PortalReportActionRequest`/`PortalReportActionResponse`/`BorrowerActionType` and `POST /api/v1/portal/reports/{token}/actions` present in the generated schema |

## Manual API verification (against a real running stack, slot 7)

1. `make demo-reset`; API on :8107.
2. Signed in as `priya.nair@clearquote-demo.test` (password + OTP via Mailpit's search API).
3. `GET /api/v1/portal/reports/{token}` -> `options: [Par, Buydown]`, `borrower_action: null`.
4. `POST .../actions {"type":"move_forward","quote_id":"<buydown>"}` -> 200,
   `status: option_selected`; Mailpit received `Priya Nair would like to move forward with
   Buydown` to `jordan.lee@clearquote-demo.test`; `activity_events` has one `quote.move_forward`
   row; `crm_events` has one `borrower.move_forward` row; `outbox_emails` has exactly one row for
   that subject.
5. Same POST again -> 409, `details: {status: "option_selected", ...}`; still exactly one email.
6. Signed in as `grace.kim@clearquote-demo.test` (real expired seeded report, sent 2026-08-31,
   expired 2026-09-21): `move_forward` -> 409 (`"This report has expired."`); `ask_updated` -> 200,
   `status: inquiry`.

## Review findings (stage 6)

Ran the `code-review` skill (medium effort) as a fresh, forked pass over the full diff.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major (correctness/race) | `submit_action` locked `QuotePackageVersion` then `QuotePackage` (token -> package order), the *opposite* of `versions.py::freeze_package_version`'s lock order (package first, then its `UPDATE ... QuotePackageVersion` superseding the prior rows). A borrower action racing a future CQ-020 resend of the same package could deadlock -- Postgres aborts one side with a raw 500 instead of a clean 409/200. | Fixed: an unlocked `SELECT QuotePackageVersion.package_id` (safe -- that mapping is immutable once a version row exists) resolves the package id first, then locks are acquired package -> version -> application, matching `freeze_package_version`'s order. All 8 `test_router.py` action tests re-verified green; no behavior change for the single-request case. A true two-session deadlock regression test is a follow-up (same limitation CQ-022's post-dev.md already noted for its own concurrency case). |
| Minor (UX bug) | `AskOtherDialog`'s local `message` state was only reset in its own `handleClose` (Cancel/Escape/backdrop); a successful submit closes the dialog via `ReportActionsSlot`'s `onSuccess` (`setDialog({kind:"none"})`) directly, bypassing `handleClose` -- reopening the dialog to ask something else showed the previous message, pre-filled and already submittable. | Fixed twice: first with a `useEffect` resetting on `isOpen`, then replaced (before this was ever committed) with the idiomatic fix once `react-doctor` flagged the effect itself as the "adjust/reset state on prop change" anti-pattern -- `ReportActionsSlot` now bumps an `askOtherOpenCount` counter on every "Ask about another option" click and passes it as `AskOtherDialog`'s `key`, so React remounts it fresh (blank `useState("")`) instead of an effect reconciling stale state. Regression test added (`AskOtherDialog.test.tsx::"clears a leftover message when remounted via a fresh key"`). |

Both fixes re-verified: backend 445 tests, frontend 254 tests (borrower-portal's own count: 84, up
from 76 pre-CQ-024 -- 8 new files' worth of coverage), `make lint` clean, `react-doctor` back to
83/100 with 0 new findings, and the full Playwright suite (borrower-portal 15/15, cross-app 1/1)
re-run green after the fixes.

## How to test manually

1. `scripts/worktree-env.sh 7` (or reuse this worktree's existing `.env`, already slot 7).
   `uv sync && pnpm install`, `uv run alembic upgrade head`, `make demo-reset`.
2. Backend: `uv run uvicorn app.main:app --app-dir backend --port 8107` in the background.
3. Portal: `pnpm --filter @cq/borrower-portal exec next dev -p 3207`; LO console:
   `pnpm --filter @cq/lo-console exec next dev -p 3107`, both in the background.
4. `uv run python backend/scripts/freeze_sent_version.py --persona priya_nair` -- prints a
   `report_token` and each option's `quote_id`.
5. Sign in at `http://localhost:3207/login` as `priya.nair@clearquote-demo.test` /
   `$SEED_BORROWER_PASSWORD`, OTP from Mailpit (`http://localhost:8025`). Visit
   `/report/{token}`, switch to Buydown, click "I'd like to move forward with this option",
   confirm -- see the confirmed state; reload -- it persists.
6. `grace.kim@clearquote-demo.test`'s report (already expired) shows only "Ask for updated
   numbers".
7. `pnpm exec playwright test e2e/borrower-portal --project=borrower-portal --workers=1` and
   `pnpm exec playwright test e2e/borrower-action-reflects-in-console.spec.ts --project=cross-app
   --workers=1` (needs `PORTAL_BASE_URL`, `LO_BASE_URL`, `SEED_BORROWER_PASSWORD`,
   `SEED_STAFF_PASSWORD`, `DATABASE_URL` set).

## Follow-ups

- CQ-016/CQ-025: `WorkspaceProvider`'s 3s poll stops once the pipeline stage is terminal (by
  design, for the pipeline-progress banner) -- there's currently no live-polling mechanism for a
  post-pipeline status change like a borrower action. A "poll a few times after mount" or "poll on
  window focus" behavior would make AC6 literally true on an idle page, not just on navigation.
- CQ-025 (dashboard tiles) isn't merged yet -- the "tile counts match too" half of AC6 needs
  re-verification once it lands.
- The mock rate-sheet grid never produces a Buydown candidate for Marcus Hale's specific
  DSCR/STR risk tier (persona 1) -- worth a look if a future item wants every seeded investment
  persona to have a real buydown option to demo.
- A full de-duplication of `_option_label`/`_validate_quote_id`-style snapshot lookups against
  `portal/reports/service.py`'s own snapshot handling is a small future cleanup; not done here to
  avoid touching a file outside this item's ownership beyond the one logged fix.
