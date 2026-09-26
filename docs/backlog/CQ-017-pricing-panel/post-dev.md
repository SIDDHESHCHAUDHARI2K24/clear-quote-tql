# CQ-017 — Post-development notes

## Summary

Built the Pricing tab's top section: a new `GET /applications/{id}/pricing` view (current scenario inputs, every pricing-overridable `field_values` row with its source badge/override state, and the `quote_engine` breakdown), stale-marking on override/revert (`pricing/enrichment/service.py`), and `/quotes/preview` accepting either side of the down-payment %/$ link plus requiring staff auth (`pricing/scenarios/{router,schemas}.py`). Frontend: `PricingPanel` (`apps/lo-console/src/features/pricing/`) with a debounced (250ms) live preview, inline enriched-field editing with `SourceBadge`/revert, strategy gating (primary/LTR/STR), DSCR colouring, a cash-to-close breakdown, and `QuoteBuilderSlot` (CQ-018's stale banner + placeholder). All money/rate figures on the panel come straight from API responses — no arithmetic on them anywhere in the frontend, enforced by a scan test.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `GET/PUT/DELETE .../fields/{key}` | `GET .../pricing` (new), `PATCH .../field-values/{key}`, `POST .../field-values/{key}/revert` (CQ-013's built routes) | plan.md Decision 1 — CQ-013 already shipped different route names; spec's own note says use the built ones and log it. |
| "note rate... editable, by choosing a priced row" | Read-only display, with a fallback to the current scenario's own Par quote's rate when no recommendation exists (CQ-018 not built) | plan.md Decision 5 — without *some* rate, `compute_quote` can't run at all and every seeded demo persona would show a blank breakdown. Choosing a row is CQ-018's quote builder, out of this item's scope. |
| Fixtures "come from real API responses captured after `make demo-reset`" | Computed directly with the real `quote_engine.compute_quote` (same function, same rounding) via a one-off script, not literally captured from a running server | The Marcus Hale golden combo (20% down, 7.500%, $342,000) doesn't match his actual seeded default scenario (25% down, system default — `auto_price` doesn't read a persona's own declared `down_payment_pct`), so a literal capture wouldn't reproduce AC1's numbers. The fixtures are still real engine output, not hand-typed; AC1 itself is also proven against the real running stack (see Acceptance evidence). |
| — (no equivalent) | `MoneyInput`/`PercentInput` (`packages/ui`) gained an optional `onBlur` prop | plan.md Decision 13 — small, additive, needed so an enriched field's override commits on blur, not every keystroke. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/pricing/panel/tests/test_router.py::test_pricing_marcus_hale_golden_values` — seeds Marcus Hale through the real pipeline (`seed_persona`), reads his real seeded tax/insurance/STR-revenue off `GET .../pricing`, feeds them into `/quotes/preview` at the golden combo (20% down via `down_payment_amount`, 7.500%, $342,000) and asserts `loan_amount=273600.00`, `ltv_pct=0.8000`, `monthly_pi=1913.05`. Also confirmed live against the real running stack (curl, logged below) and `PricingPanel.test.tsx`'s fixture-based component test. |
| AC2 | Met | `DownPaymentLinkedInput.test.tsx` (4 tests): typing 25% updates the $ field to $85,500.00; typing $68,400 sets 20.00%; loan amount/LTV/purchase price render as passed; every field keyboard-accessible. |
| AC3 | Met | `pricing/enrichment/tests/test_stale_marking.py` (override + revert both mark stale, write one activity event, no-op with no quotes) + `pricing/panel/tests/test_router.py::test_override_property_tax_recomputes_breakdown_immediately` (the live breakdown, not just the field row) + `PricingPanel.test.tsx`'s AC3 test (badge → "LO override", total changes, stale banner appears, `refetch()` called) + `e2e/lo-console/pricing-panel.spec.ts`'s AC3 test against the real stack. |
| AC4 | Met | `PricingPanel.strategy-gating.test.tsx` (7 tests, 4 persona fixtures) + `e2e/lo-console/pricing-panel.spec.ts` (Priya no investment/PPP; Daniel — see below; Marcus STR-only; Kathleen LTR-only), all against real seeded personas. |
| AC5 | Met | `PricingPanel.strategy-gating.test.tsx` (Marcus 0.90 amber, Asheville/Sam Reed ≥1.25 green, Kathleen 1.00–1.24 neutral) + e2e (Marcus's live DSCR renders, amber via `text-status-warning`). |
| AC6 | Met | `apps/lo-console/src/features/pricing/pricing-no-money-math.test.ts` (10 tests) — scans every non-test file this item owns for an arithmetic operator adjacent to a money/rate field name derived from the fixtures; all clean. `format.ts`'s two unit-conversion helpers (percent-input-text ⇄ 0-1 fraction) are documented as translating the *input control's own display unit*, never combining two API-returned money/rate values — see that file's comment and plan.md Decision 6/10. |
| AC7 | Met | `e2e/lo-console/pricing-latency.spec.ts` against the real running stack: p95 = 380ms (samples: 362–381ms), well under 600ms. |
| AC8 | Met | `npx react-doctor -y --blocking error` exits 0 (score 74/100, warnings only — see Test log); `e2e/lo-console/pricing-panel.spec.ts`'s axe check on `<main>` (this item's own root, added per plan.md Decision 15) finds zero new violations; screenshot `evidence/pricing-panel-priya.png`. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend -q` | 425 passed (after the review round's fixes + new tests; was 418 after the first implementation pass) |
| Seed tests | `uv run pytest seed -q` | 27 passed |
| ruff / mypy | `make lint` (backend portion) | clean |
| Frontend tests | `pnpm -r run test` | 2 (api-client) + 112 (packages/ui) + 64 (lo-console) + 37 (borrower-portal) = 215 passed |
| eslint / tsc / prettier | `make lint` | clean |
| E2E typecheck | `pnpm exec tsc --noEmit -p tsconfig.json` | clean |
| react-doctor | `npx react-doctor -y --blocking error` | exit 0, score 74/100 ("Needs work" — no errors, only warnings; see Follow-ups) |
| `alembic heads` | `uv run alembic heads` | `bbd0e3150264 (head)` — one head, no new migration added by this item |
| `make demo-reset` | `time make demo-reset` | ~1.3s |
| E2E (slot 5, full recipe) | `SEED_STAFF_PASSWORD=<slot 5's> LO_BASE_URL=http://localhost:3105 PORTAL_BASE_URL=http://localhost:3205 pnpm exec playwright test e2e/lo-console --workers=1` (against a fresh `make demo-reset`, API on 8105, worker on `cq-s5`, LO console on 3105) | 18 passed: both smoke specs, gallery specs, staff-login, all 7 of `workspace.spec.ts`'s tests (unaffected), all 6 of `pricing-panel.spec.ts`'s AC-named tests, `pricing-latency.spec.ts`'s AC7 test |

## Review findings (stage 6)

Self-review during development (equivalent scrutiny to `code-review`) found and fixed two real issues before calling this done:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `panel/service.py::_inputs_and_config` originally read tax/insurance/HOA/rent from the current scenario's *frozen* `inputs` snapshot — an override never changed the displayed breakdown, breaking AC3 outright (only reprice, CQ-018, creates a new scenario). | Rewrote to always read those fields fresh from `field_values` (purchase price/down payment %/strategy still come from the scenario or system-design defaults) — plan.md Decision 12. Verified live against the real stack (curl round trip below) and with a new test, `test_override_property_tax_recomputes_breakdown_immediately`. |
| Major | `usePricingPreview.ts`'s original single-effect implementation (nested nested `setTimeout`s + an `AbortController` created inside the inner timeout) left `react-doctor`'s `effect-needs-cleanup` rule genuinely unsatisfied: a `recalcTimer` created inside the debounce's callback could fire `setIsRecalculating(true)` on an unmounted component, since it wasn't reachable from the effect's own cleanup. | Rewrote as two flat effects (debounce → `debouncedKey`; fire-preview-and-clean-up on `debouncedKey` change), each owning exactly one timer/AbortController declared directly in its own body, so cleanup is unambiguous. `react-doctor -y --blocking error` now exits 0 (previously 1 blocking error). All 25 pricing Vitest tests still pass unmodified. |
| Minor | `EnrichedPercentField`'s `useState` initializer ran `fractionToPercentInputValue(...)` on every render (react-doctor `rerender-lazy-state-init`). | Wrapped in a lazy initializer (`useState(() => ...)`). |

**Multi-angle automated review round** (8 relayed passes: efficiency, simplification, reuse, AGENTS.md compliance, correctness, root-cause, cross-file, removed-behavior). Full detail in plan.md's "Post-merge review round" table (#18-31); summary:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Must-fix | `panel/service.py` divided `insurance_annual / purchase_price` outside `quote_engine` (AGENTS.md violation) | Added `quote_engine.insurance_annual_rate_from_amount`, Decimal-tested, `NonPositivePriceError`-guarded; `panel/service.py` now calls it. |
| Must-fix | `QuotePreviewRequest`'s amount-based path could 500 on a missing/invalid `purchase_price` or `down_payment_amount` (`KeyError`/`InvalidOperation`, not caught by Pydantic's `ValueError`-only auto-wrap) | `_to_decimal` helper + explicit `ValueError`s (422 via Pydantic); `down_payment_pct_from_amount`/`insurance_annual_rate_from_amount` both gained a `purchase_price <= 0` guard (`NonPositivePriceError`); `panel/service.py::_inputs_and_config` guards the same case, degrading to `breakdown=None`. 5 new tests. |
| Perf | `_inputs_and_config` made up to 6 sequential `field_values` queries | Batched into one `field_key IN (...)` query. |
| Perf + correctness | `_mark_application_quotes_stale`'s SELECT-then-UPDATE raced under concurrent overrides (double activity-log entries possible) | Single `UPDATE ... WHERE id IN (SELECT ...) AND stale=false RETURNING id`. |
| Correctness | The stale-marking activity event was skipped entirely when no quote existed yet or all were already stale | Now always written (with `old_value`/`new_value` added to the payload) when the field is pricing-affecting; only `quote_ids` may be empty. |
| Consistency | `/quotes/preview` echoed the request's `down_payment_pct` instead of engine output | `QuoteComputation` itself now carries `down_payment_pct` (populated in both `compute_quote` branches); `QuotePreviewResponse` no longer redeclares it; `GET .../pricing`'s breakdown gets it for free too. Regression test pins `down_payment_pct + ltv_pct == 1`. |
| Reuse | `formatMoneyCents` duplicated `@cq/ui`'s `formatMoneyPrecise`; `toInputString` was dead code | `formatMoneyCents` now wraps `@cq/ui`'s `formatMoneyPrecise` (same null-handling, no new `Intl.NumberFormat` instance); `toInputString` deleted. |
| Logged, not fixed | `peek_source_value` loop, `get_pricing_view`'s sequential reads | Both share one `AsyncSession`, which can't be used concurrently — sequential is correct, not an oversight (plan.md #24/#25). |
| Logged, not fixed | `panel/service.py` vs. CQ-013's `scenarios/service.py::_gather_base_scenario_inputs` structural duplication | `scenarios/service.py` is outside this item's owned files (CQ-013's, 100+ tests) and the two functions have a genuine, intentional error-handling difference — logged for a future cross-cutting refactor rather than editing another item's file (plan.md #26). |
| Logged, not fixed | `PricingPanel.tsx`'s 5 enriched-field blocks aren't driven from a single config array; `dirty` state isn't derived; `_field_views` has no placeholder for a not-yet-enriched field; no "Unsaved — preview only" UX marker | All low-risk/low-priority per the reviewers' own notes or out of this item's acceptance criteria; logged in plan.md #28-31 rather than expanding scope further. |

No fresh-subagent review pass beyond this has been run on this branch (per the runbook, that happens via the `code-review` skill and/or the phase orchestrator's PR review before merge into `phase-p3-p4`).

## PR review round (fresh stage-6) -- PR #9

A fresh subagent (one that hadn't written this item's code) reviewed the open PR and found one CRITICAL and two MINOR issues. All three are fixed on this branch.

| Severity | Finding | Resolution |
| --- | --- | --- |
| CRITICAL | `EnrichedPercentField`'s `handleBlur` fired `onOverride` on a plain focus+blur with **no edit**, for small rates. `fractionToPercentInputValue` (x100, `.toFixed(3)`) then `percentInputValueToFraction` (/100, `.toFixed(4)`) round-trips lossily -- `"0.000089"` (a real seeded `property_tax_annual_rate`) becomes `"0.009"` on display, then `"0.0001"` when converted back, and `"0.0001" !== "0.000089"` fired an override the LO never made -- silently marking every quote on that application stale and flipping the badge to "LO override". Reproduced first as a failing Vitest test (`EnrichedPercentField.test.tsx`, all 4 rates from the finding), confirming the exact `"0.0001"` call. | Added a `touched` ref (not `useState` -- it's read only inside `handleBlur`, never rendered, so a ref avoids an unnecessary re-render and a `react-doctor` "state only used in handlers" finding) set `true` only by the input's own `onChange`, reset on a new `field.value` prop or after a blur is handled. `handleBlur` is now a no-op whenever `!touched.current`, so a no-edit blur can never call `onOverride` regardless of any display-rounding artifact. Also bumped `percentInputValueToFraction`'s fraction precision from `.toFixed(4)` to `.toFixed(6)` (a real edit of a small rate -- e.g. typing "0.0089" percent for a ~0.000089 fraction -- was itself being truncated to `"0.0001"` at 4dp even when the user *did* type it; 6dp covers the seeded tax-rate scale exactly, and is a no-op for every value that already fit in 4dp, since `toFixed` just adds trailing zeros). Applied the identical `touched`-ref rule to `EnrichedMoneyField` for consistency, even though `MoneyInput`'s `value`/`onChange` never round-trip through a unit conversion so it wasn't actually exposed to the round-trip bug itself. |
| MINOR | `PricingPanel.tsx`'s STR block hardcoded `"20.00%"` for the expense ratio instead of reading it from the API response. | Now renders `formatPercent2dp(breakdown?.config_snapshot.str_expense_ratio ?? null)` -- the same field CQ-021's report already reads for the same number (`report/builder.py`'s `_pct_2dp(c.config_snapshot.str_expense_ratio)`). No fixture/test changed output (every STR fixture's `str_expense_ratio` is already `"0.20"`), but the panel is no longer wrong if `Settings.str_expense_ratio` (or a future scenario-level override) ever differs from the 20% default. |
| MINOR (logged, now fixed too) | `pricing/scenarios/service.py:171` divided `insurance_annual / purchase_price` inline instead of calling `quote_engine.insurance_annual_rate_from_amount` (AGENTS.md: money math lives only in `quote_engine`) -- the same class of bug already fixed in `panel/service.py` during the first review round (#18), just missed in this sibling file. The engine function's own docstring already documented it as "matches `pricing.scenarios.service._gather_base_scenario_inputs`'s own unrounded formula for the same conversion" -- i.e. it was written to be a drop-in replacement here. | One-line change: `insurance_rate = insurance_annual_rate_from_amount(purchase_price, insurance_annual)`, using the existing import. Covered by the existing 121 `backend/app/features/pricing` tests (all still pass unmodified -- same unrounded division, just routed through the engine) rather than a new test, per the finding's own instruction ("a one-line change with the existing tests as the guard"). The broader `panel/service.py` vs. `scenarios/service.py` structural duplication (plan.md #26) is unchanged and still logged as a future cross-cutting refactor, not this fix's job. |

New tests added for the CRITICAL fix (all passing):
- `EnrichedPercentField.test.tsx` (7 tests): focus+blur with no typing calls `onOverride` zero times for `"0.000089"`, `"0.0064"`, `"0.0153"`, `"0.0225"`; typing a new value still overrides correctly (`"1.250"` -> `"0.012500"`); typing then backspacing back to the original displayed value does not override; typing a small edited value (`"0.0089"` -> `"0.000089"`) is no longer truncated to `"0.0001"`.
- `EnrichedMoneyField.test.tsx` (2 tests): same no-edit-no-override rule; typing a new value still overrides correctly.
- `e2e/lo-console/pricing-panel.spec.ts` gained an 8th test: tabs through every field (purchase price, down payment %/$, tax rate, insurance, HOA, market rent) on Kathleen McReynolds (LTR) with no edits, against the real running stack (slot 5, fresh `make demo-reset`), and asserts every `[data-source]` badge is unchanged and the stale banner never appears. Kathleen, not Marcus Hale, because this spec runs `test.describe.configure({ mode: "serial" })` against one shared seeded stack and the pre-existing AC3 test earlier in the same file already overrides-then-reverts Marcus's tax rate, which leaves his quotes permanently stale (no un-marking endpoint in this item's scope) -- Kathleen is untouched by every earlier test in the file, so her banner's absence is a real assertion, not a false negative.

**Verification after the fix (this round):** `make lint` clean; `uv run pytest backend -q` 425 passed; `uv run pytest seed -q` 27 passed; `pnpm -r run test` 224 passed (was 215 -- +9 new: 7 `EnrichedPercentField` + 2 `EnrichedMoneyField`); `npx react-doctor -y --blocking error` exit 0, **score unchanged at 74/100** (the `touched`-ref choice, not `useState`, avoids adding any new warnings -- verified: switching to `useState` first showed 4 new warnings, score dropped to 71/100, then the ref refactor brought it back to the exact same 12-issue baseline); `pricing-panel.spec.ts` 7/7 passed live against slot 5 (API restarted + warmed up after each `make demo-reset`, worker + LO console running).

## PR review round 2 (fresh subagent, `code-review` skill, medium effort)

The `code-review` skill was run against this branch (as required before merge) and found the fix above wasn't fully correct, plus a second real bug it surfaced along the way. Both fixed.

| Severity | Finding | Resolution |
| --- | --- | --- |
| CRITICAL (regression in the fix above) | `EnrichedPercentField`'s new `handleBlur` compared `draft` to `fractionToPercentInputValue(field.value)` (a *display* string) to decide whether a touched field's value actually changed. `field.value = "0.0064"` displays as `"0.640"`; an LO who selects the text and retypes `"0.64"` (the natural way to type it, without the trailing zero) produces a different string, so the guard didn't catch it and `onOverride` fired anyway -- the exact class of bug this PR set out to fix, just reachable a different way. Verified by the reviewer with a standalone reproduction of `fractionToPercentInputValue`/`percentInputValueToFraction`. | Extracted the touched-ref + reset-on-prop-change state machine into a shared hook, `useTouchedDraft` (`apps/lo-console/src/features/pricing/useTouchedDraft.ts` -- also fixes the MINOR duplication finding below in the same change). Its `commit(toWire)` now compares the *numeric* value of the resolved wire value to `field.value` (`Number(wire) === Number(wireValue)`), not the display string -- `touched` already guarantees this only runs after a real edit, so a numeric match means "typed a different-looking but equal value" (no-op), never "never touched it" (that case is filtered out earlier and never reaches the comparison). `field.value === null` skips the numeric check and always commits (`Number(null)` is `0`, not `NaN`, so it can't be trusted as "equal"). New test: `EnrichedPercentField.test.tsx`'s `"retyping the same rate without the display's trailing zero does not override (PR #9 regression)"` -- reproduces the reviewer's exact scenario, fails against the pre-fix code, passes now. |
| MINOR | `pricing/scenarios/service.py:176`'s one-line fix from review round 1 (routing insurance-rate math through `quote_engine.insurance_annual_rate_from_amount`) introduced a real regression of its own: that function raises `NonPositivePriceError` (a plain `ValueError`) for a non-positive `purchase_price`, but nothing between it and the route catches bare `ValueError`s -- `ScenarioCreateRequest.purchase_price` has no `gt=0` constraint, so a `0.00` (or negative) purchase price now reaches this function and surfaces as a generic 500, unlike every sibling "can't price" guard in the same function (missing FICO/tax/insurance/rent), which all raise `ValidationAppError` -> 422. | Wrapped the call in `try/except NonPositivePriceError as exc: raise ValidationAppError(f"Cannot price: {exc}") from exc`, matching the function's own established pattern. New test: `scenarios/tests/test_ob_validation.py::test_scenario_create_with_zero_purchase_price_is_422_not_500` -- `POST /applications/{id}/scenarios` with `purchase_price: "0.00"` now returns 422 with `VALIDATION_ERROR`, not a 500. |
| MINOR | The touched-ref + reset-on-prop-change pattern was duplicated verbatim between `EnrichedPercentField.tsx` and `EnrichedMoneyField.tsx` (flagged by the reviewer as a maintenance risk -- exactly the CRITICAL finding above happening in only one of the two copies is the concrete cost of that duplication). | Extracted into `useTouchedDraft.ts` (one hook, ~45 lines incl. comments), parameterized by a `toDisplay` formatter (module-level function references only -- an inline arrow would break the reset effect's dependency identity) and a `toWire` resolver passed into `commit()`. Both components now call the same hook; `EnrichedMoneyField`'s comparison is also numeric now (was a raw string compare), which is a strict improvement in the same direction as the percent-field fix, with no test asserting the old, less-correct behavior. |

**Verification after this round:** `make lint` clean (ruff, mypy, eslint, tsc, prettier); `uv run pytest backend -q` 472 passed (includes CQ-023's merged tests + the new 422 test); `uv run pytest seed -q` 28 passed; `pnpm -r run test` 75 (lo-console, was 73 -- +2: the new regression test, the money-math scanner picking up the new hook file) + 84 (borrower-portal) + others, all green; `npx react-doctor -y --blocking error` exit 0, **score improved to 77/100** (11 issues, down from 12 -- the hook extraction happens to also clear `EnrichedMoneyField`'s "all state reset on prop change" warning); `pricing-panel.spec.ts` 7/7 passed live against slot 5 (fresh `make demo-reset`, API restarted + warmed up, worker + LO console running); `alembic heads` = 1 (`e419a34bcdbd`, CQ-023's migration) after merging `origin/phase-p3-p4` a second time to pick up CQ-023.

## Pricing view response shape (`GET /applications/{id}/pricing`)

```jsonc
{
  "application_id": "uuid",
  "inputs": {
    "purchase_price": "342000.00",
    "down_payment_pct": "0.25",
    "strategy": "STR",           // PRIMARY | LTR | STR
    "prepayment_penalty_years": 5,
    "fico": 762,                  // not badge-carrying (spec's field list has no FICO badge)
    "insurance_annual_rate": "0.005"  // derived server-side; the panel never divides homeowners_ins_annual/purchase_price itself
  },
  "fields": [                     // only the 5 pricing-overridable field_values rows that exist
    {
      "field_key": "property_tax_annual_rate",
      "value": "0.000089",
      "source": "smartasset",      // FieldSource enum value -> SourceBadge label
      "source_ref": null,
      "overridden": false,
      "original_value": null       // populated only when overridden=true (peeked live, never stored)
    }
    // ... homeowners_ins_annual, hoa_fee_monthly, and market_rent_ltr OR gross_annual_revenue_str
  ],
  "note_rate": "0.07625",          // 0-1 fraction; null until at least one quote exists
  "breakdown": { /* QuoteComputation, byte-for-byte what /quotes/preview returns, or null */ },
  "has_stale_quotes": false
}
```

## How stale marking works

Every override (`PATCH .../field-values/{key}`) or revert (`POST .../field-values/{key}/revert`) on any of the 5 pricing-overridable field keys — `property_tax_annual_rate`, `homeowners_ins_annual`, `hoa_fee_monthly`, `market_rent_ltr`, `gross_annual_revenue_str` — sets `stale = true` on every non-stale `Quote` reachable through that application's `scenarios` (all scenario groups, not just the "current" one: tax/insurance/HOA are scenario-independent, so a tax override affects every strategy group identically). One `activity_events` row is written per call (`type="quotes.marked_stale"`, `payload={field_key, action: "override"|"revert", quote_ids}`). There is no un-marking endpoint in this item's scope — CQ-018's reprice clears it.

## What CQ-018 must know

- **`QuoteBuilderSlot.tsx`** (`apps/lo-console/src/features/pricing/QuoteBuilderSlot.tsx`) is CQ-018's file from here — replace its placeholder body with the real quote cards/overlay/AutoQuote UI. It takes one prop, `hasStaleQuotes: boolean` (from `PricingViewResponse.has_stale_quotes`), which `PricingPanel.tsx` already wires up.
- **The stale banner** ("Quotes are out of date — Re-price") is rendered by `QuoteBuilderSlot` itself when `hasStaleQuotes` is true; its "Re-price" button is present, keyboard-accessible, labelled, but `disabled` with `title="Arrives in CQ-018"` — CQ-018 wires the actual reprice action (presumably calling `pricing.scenarios.service.create_default_scenarios` again with the LO's current inputs) and clears `stale`.
- `Quote.stale` (the column CQ-018 clears) and the `applications.recommended_quote_id` FK (still unset by anything in P3 so far) are both foundation-migration columns; nothing in this item writes `recommended_quote_id`.
- The panel's `note_rate` fallback (current scenario's Par quote, or earliest quote) is a stand-in for CQ-018's real "recommended quote" flow — once CQ-018 sets `recommended_quote_id`, `panel/service.py::_current_quote` already prefers it first (checked before the Par-label fallback), so no change should be needed there.
- The 5 pricing-overridable `field_values` keys are now a public constant, `enrichment.service.OVERRIDABLE_FIELD_KEYS`, if CQ-018 needs the same list.

## Live verification against the real running stack (slot 5)

```
$ curl -s -b cookies.txt "http://localhost:8105/api/v1/applications/<marcus-id>/pricing" | python3 -m json.tool
# note_rate: 0.07625, breakdown.dscr_ratio: 0.82 (BELOW_1_00, amber) — his real seeded numbers

$ curl -s -b cookies.txt -X POST http://localhost:8105/api/v1/quotes/preview -d '{
  "purchase_price": "342000.00", "down_payment_amount": "68400.00", "note_rate": "0.075",
  "strategy": "STR", "fico": 762, "property_tax_annual_rate": "0.000089",
  "insurance_annual_rate": "0.005", ... "str_gross_annual_revenue": "24000.00" }'
# -> loan_amount: 273600.00, ltv_pct: 0.8000, monthly_pi: 1913.05   (AC1, exact)

$ curl -s -b cookies.txt -X PATCH .../field-values/property_tax_annual_rate -d '{"value":"0.02"}'
$ curl -s -b cookies.txt .../pricing
# -> has_stale_quotes: true, fields[tax].overridden: true, fields[tax].original_value: "0.000089"
#    breakdown.monthly_tax: 570.00 (was 2.54) — recomputed immediately (AC3)

$ curl -s -b cookies.txt -X POST .../field-values/property_tax_annual_rate/revert
# -> value back to "0.000089", source "smartasset"
```

## Note on seed data (not this item's to fix)

The real seeded `provider_tax_rates.annual_rate_pct` values (e.g. Hillsborough FL `"0.0089"`) are roughly 2 orders of magnitude smaller than the data-field-catalog's own illustrative examples ("Buncombe 0.601%, Hillsborough 1.15%") once divided by 100 at the enrichment boundary (`_fetch_tax`'s existing, correct conversion) — every seeded persona's real monthly tax figure is a few dollars, not a few hundred. Confirmed this is CQ-010's seed fixture data (`seed/providers/tax_rates.yaml`), not an enrichment bug: `_fetch_tax`'s conversion matches its own documented contract and CQ-013's tests. Flagging here since it makes any *unedited* seeded breakdown's tax line look wrong at a glance; out of this item's owned files (`pricing/enrichment/**`'s override/revert logic is correct — only the seeded rate table itself looks off).

## How to test manually

1. `source scripts/worktree-env.sh 5` (or your own slot).
2. `uv run alembic upgrade head && make demo-reset`.
3. In the background: `uv run uvicorn app.main:app --app-dir backend --port <API_PORT>`, `uv run python -m app.workflows.worker`, `pnpm --filter @cq/lo-console exec next dev -p <LO_PORT>`.
4. Sign in as `casey.nguyen@clearquote-demo.test` (Manager, password: `.env`'s `SEED_STAFF_PASSWORD`) — sees every seeded LO's applications.
5. Open Marcus Hale's application → Pricing tab. Type `20` into the down payment % field — the $ field updates to $68,400.00 within ~600ms; the breakdown recomputes.
6. Click into the tax annual rate field, change it, tab out — badge flips to "LO override" with a revert icon; the stale banner appears above the quote builder placeholder.
7. Click the revert icon — badge and value restore to SmartAsset's value; total recomputes again.
8. Open Daniel Ortiz's application, type `5` into down payment % — an MI line appears.

## Follow-ups

- `react-doctor`'s remaining warnings (score 74/100, no blocking errors): 5× pre-existing client-side-redirect (CQ-005/CQ-016, out of scope); `EnrichedMoneyField`/`WorkspaceProvider`'s "all state reset on prop change" (both intentional resyncs, same class CQ-016 already logged as intentional); `PricingPanel`'s high complexity / giant component (expected given its scope — top-half-of-the-tab is inherently a lot of gated sections; a future split into smaller presentational sub-components would help but wasn't done here to keep the file count owned-and-reviewable); `PricingPanel`'s "state update after await in an effect" (`load()`, same unguarded-async pattern `WorkspaceProvider.refetch` already uses); `Overlay`'s custom-modal warning and `report/format.ts`'s Intl-rebuild warning (both pre-existing, CQ-005/CQ-021).
- The two axe findings excluded from `pricing-panel.spec.ts`'s AC8 assertion (`StatusPill` colour contrast, `Card`'s h1→h3 heading jump) are real, pre-existing, cross-cutting `packages/ui`/workspace-shell issues — worth a dedicated a11y pass across the whole console, not scoped to this item.
- The seed-data tax-rate-magnitude note above (not a CQ-017 defect, but worth CQ-010's owner knowing about).
- CQ-018 should double check `_current_quote`'s Par-label/earliest-quote fallback once `recommended_quote_id` is actually being set — the code already prefers it, but this item couldn't exercise that path against real seed data (no seeded application has one yet).

## U3 (P5/P6 merge): stale-path change (appended)

Merge plan decision M4 (`docs/backlog/phase-p5-p6-main-merge-plan.md`, unit U3; details in `docs/backlog/phase-p5-p6-stale-clock.md`):

- The private `_mark_application_quotes_stale` in `pricing/enrichment/service.py` was removed. Overrides and reverts now flag quotes through CQ-030's `quotes.stale.service.mark_application_quotes_stale`, the one stale path. That helper now returns the ids it changed, and still uses one conditional `UPDATE … WHERE stale = false RETURNING id`.
- The call site (`_mark_quotes_stale_after_field_change`) still writes exactly one `quotes.marked_stale` event per override or revert. As before, it writes the event even when no quote changed. The payload keeps `field_key`, `action`, `old_value`, `new_value` and `quote_ids`, and adds `message`, for example "Quotes marked stale: property tax annual rate overridden", which the CQ-029 timeline shows.
- `overridden_at` and the event `at` read `core/clock.now()` (M5).
- The lock order is unchanged: quotes → application (U2).
- Evidence: `pricing/enrichment/tests/test_stale_marking.py::test_override_uses_the_shared_stale_path_with_one_messaged_event`. It spies on the shared helper, checks for exactly one event with the message and quote ids, and the other stale-marking tests there still pass.
