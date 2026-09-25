# CQ-022 Borrower report page

| Field | Value |
| --- | --- |
| Phase | P4 Borrower Tier A |
| Depends on | CQ-021, CQ-015 |
| Kaneo task | CQ-022 in Kaneo (task id `lu2ozfdjwkillbh9z0tymw42`) |
| Branch | `cq-022-borrower-report` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

The borrower opens the link from their email and lands on their numbers: 3 or 4 figures they understand in five seconds, a clear recommendation, and everything else one click away. This is the page the client will judge most closely.

## Scope

**Backend (owned by this item)**

- Migration: add `quote_package_versions` (package_id, version, snapshot JSONB `ReportViewModel`, letter_key, report_token, sent_at, expires_at, viewed_at, superseded, borrower_action JSONB) unless CQ-020 already added it. Stage 1 checks the CQ-007 models first: if versioning is already covered, reuse it and log a `Decision:`.
- `GET /api/portal/reports/{token}` (borrower session from password + email OTP, CQ-015; the token only selects the version and is not a credential) returns the frozen `ReportViewModel` from the `quote_package_versions` row for that token (written by CQ-020), with `expired` computed at request time (now > expires_at).
- Viewing: the first successful load sets `viewed_at` on the version, moves status Sent → Viewed, and writes an activity event. Later loads do not create new events.
- Access: a token for another borrower's package returns 404, never the data.

**Frontend (`apps/borrower-portal`)**

- Route `/report/[token]`, which needs a borrower session. When the visitor is signed out, it redirects to `/login?next=/report/{token}` (with a link to signup that prefills the email), and after OTP returns to the report.
- Page order, from `system-design.md` → Quote report:
  1. `ReportHeader`
  2. `OptionSwitcher` (hidden when there is only one option). The selection is kept in the URL (`?option=<quote_id>`) so a shared link or reload keeps it.
  3. `HeroNumbers` for the selected option
  4. `RecommendationCard`; when a non-recommended option is selected, a small note "You're viewing an alternative to our recommendation"
  5. `ExplainerCards` (investment only)
  6. Collapsible "See all N options we priced" → `ComparisonTable`
  7. Collapsible "See the full breakdown" → `BreakdownTable`, `CashflowTable`, `CostSegTable`
  8. Property matches slot (empty until CQ-023)
  9. Actions slot (buttons wired in CQ-024; render them disabled with "Coming soon" until then)
  10. `Disclosures` and an LO contact card
- States: loading skeleton, expired (ExpiredBanner, actions hidden, "Ask for updated numbers" button placeholder for CQ-024), superseded (SupersededBanner with a link to the newest version), invalid or foreign token (friendly 404).
- Print stylesheet: Save as PDF prints a clean document; collapsibles print expanded; switcher, actions and navigation are hidden; the selected option is printed; page breaks avoid splitting tables.
- Responsive: 375 px mobile layout with hero tiles stacked 2×2 (investment) or 1×3 (primary); desktop max width 1120 px.

## Out of scope

- Property matches (CQ-023), borrower actions (CQ-024), portal home (CQ-031).

## References

- `docs/design/system-design.md` — Borrower Portal → Quote report, Hero numbers, Decisions 3 and 5.
- Reference screens: `04-report-summary.png`, `06-report-pricing-options.png`.

## Acceptance criteria

- [ ] AC1 — Opening the link from Marcus Hale's email (after CQ-020) shows his report; the API response equals the frozen snapshot of that sent version.
- [ ] AC2 — First load moves his status to Viewed and writes one activity event; a reload writes none.
- [ ] AC3 — Selecting the Buydown option updates hero numbers and breakdown and sets `?option=`; reloading keeps the selection; the alternative-view note appears.
- [ ] AC4 — Grace Kim's report (sent 25 days ago) shows the expired banner and no action buttons.
- [ ] AC5 — A token belonging to another borrower, or a random token, returns 404 and the friendly not-found page.
- [ ] AC6 — Print preview (Playwright `page.pdf`) of Marcus Hale's report contains the hero numbers, both expanded sections and no switcher or buttons, with no table split across pages.
- [ ] AC7 — At 375 px width there is no horizontal scroll and hero tiles follow the stacked layout.
- [ ] AC8 — Priya Nair's report shows no investment content (reuses the CQ-021 gating check on the live page); Lighthouse accessibility score ≥ 95; react-doctor passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Integration test (send → fetch) | `test_portal_report_matches_snapshot` |
| AC2 | API test | `test_first_view_sets_viewed_once` |
| AC3 | Playwright | `e2e/report-option-switch.spec.ts` |
| AC4 | API + Playwright | `test_expired_flag`, `e2e/report-expired.spec.ts` |
| AC5 | API test | `test_report_token_isolation` |
| AC6 | Playwright PDF + text assertions | `e2e/report-print.spec.ts` |
| AC7 | Playwright viewport test | `e2e/report-mobile.spec.ts` |
| AC8 | Playwright + Lighthouse CI + react-doctor | evidence in post-dev.md |

## Notes for the agent

- This item can run before CQ-020 (the borrower lane runs parallel to the LO lane). Until real sent versions exist, tests create a sent-package snapshot with a factory that uses the CQ-021 builder. AC1 is verified with the factory first and re-checked end to end once CQ-020 is merged; record both in post-dev.md.
- The page composes CQ-021 components only; new visual pieces go into `packages/ui` so the LO preview stays identical.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
