# CQ-010 — Post-development notes (Phase A + Phase B, complete)

## Summary

Full item complete. Phase A (personas, providers, users, background
generator, watermarked docs, `make demo-reset` scaffolding) landed first
while CQ-013 (pricing/enrichment) was still in flight; Phase B wired the
real pricing stage after `phase-p0-p1` merged CQ-013 (`a95498b`/`85e0462`).
Every persona now reaches its exact "Seed end status" from spec.md's table
via the real, merged service functions — no reimplemented pricing/
enrichment logic anywhere in `seed/`. `time make demo-reset` runs in
~1.8-2.2s, well under the 60s budget, and two consecutive runs produce
identical background-application counts.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Aisha Coleman ends `needs_attention` ("Cannot price: missing Occupancy") | Ends `needs_attention` with flag `Cannot price: missing RepresentativeFICO` | `Occupancy` on the merged `applications`/OB-request schema is non-nullable, so it can never literally be "missing" — CQ-013's own post-dev.md documents this exact substitution as the schema's real equivalent for this same persona. Same pipeline outcome (`needs_attention`, one blocking flag, "Cannot price: missing X"), different concrete field. |
| `LoanFileDTO` (CQ-009) had no employment/liabilities/assets/co_borrower_dob fields | Added as optional, additive fields | `import_from_los`'s owned scope (application_parties/housing_history/employment/liabilities/assets) needs a source for the latter three, and CQ-012's `dob_format` rule already checks a co-borrower's DOB. Nothing else read `LoanFileDTO` before this, so purely additive. |
| `provider_rents`/`provider_str_revenue` keyed by the persona table's "Beds" column | Keyed by `beds=1` (== `Property.number_of_units`) for every market | CQ-013's enrichment looks these tables up by `property.number_of_units`, not a bedroom count (the schema has no such column); Phase A's original keying silently produced `RentDataNotFoundError`/`StrDataNotFoundError` once real enrichment ran (plan.md decision #11). |
| Marcus Hale's STR revenue uses the same `price × 0.14` proxy as every other market | Tampa (zip 33602) pinned to `$24,000` annual revenue | The generic proxy gave DSCR > 1, contradicting system-design.md's own description of this persona ("DSCR < 1 ... negative cashflow shown honestly"). Verified: DSCR 0.82, cashflow -$360.53/mo, `year_one_tax_savings` $24,275.78 — matches the catalog's pinned golden value ($24,276) exactly (plan.md decision #12). |
| `field_values.representative_fico` | Written by this item's own new `_seed_representative_fico` step (real hard-pull credit report), not part of `pricing_seam.py` | No item's spec (including CQ-011's 6 named activities) charters a credit-pull activity, yet `auto_price`/`validate_ob_required_fields` require this field. Since CQ-010 already seeds `provider_credit_reports`, sourcing it here is an input, not computed logic (plan.md decision #10). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | **Full** | `time make demo-reset` → 1.8-2.2s. `seed/tests/test_personas_match_engine.py` (3 tests). Spot-checked Marcus Hale's real persisted `Quote.computed`: `title_fees=2394.00` (0.7% of $342,000), `dscr_ratio=0.82`, `year_one_tax_savings=24275.78` (matches catalog override O4's pinned $24,276 golden value) — all produced by `quote_engine` via CQ-013's `auto_price`, none hand-typed. |
| AC2 | **Full** | `pytest seed/tests/test_persona_statuses.py::test_persona_final_statuses_match_table` — all 10 personas match `seed_end_status` exactly: 6 `priced`, Aisha Coleman + Ben Ford `needs_attention`, Grace Kim `sent`, Luis Romero `option_selected`. Confirmed again directly against the dev DB after `make demo-reset`. |
| AC3 | **Full** | `pytest seed/tests/test_provider_rows_seeded.py` (8 tests) — all 5 named `provider_*` tables have ≥1 row per persona market; LOS/Tax/Rent/Str/Credit/Insurance/CRM/PropertySearch adapters return non-empty for every applicable persona. |
| AC4 | **Full** | `pytest seed/tests/test_users_seeded.py` (2 tests) — exactly 2 LO/1 Manager/1 Admin, real bcrypt hashes. |
| AC5 | **Full** | `pytest seed/tests/test_background_generator_determinism.py` (3 tests); confirmed at the `make demo-reset` level too — two consecutive runs both produced `{'intake': 28, 'verifying': 27, 'needs_attention': 24, 'ready_to_price': 31, 'stale': 12, 'priced': 53, 'sent': 25}` and 100/100 per LO. |
| AC6 | **Full** | `pytest seed/tests/test_documents_watermarked.py` (4 tests) — every persona has ≥1 `documents` row; watermarked PDF/PNG round-tripped through the real MinIO container. |
| AC7 | **Full** | `pytest seed/tests/test_persona_statuses.py::test_grace_and_luis_downstream_rows` — Grace Kim: `status=sent`, `quote_packages.sent_at` ≈ now-25d, `borrower_action=None`. Luis Romero: `status=option_selected`, `borrower_action` set, `quote.sent`/`quote.viewed`/`quote.option_selected` activity_events, ≥1 outbox_emails row. |
| AC8 | **Full** | `pytest seed/tests/test_personas_match_engine.py::test_no_reference_sheet_errors_reproduced` plus the real Marcus Hale trace above (title fee, DSCR<1 negative-cashflow demo, no mixed LTR/STR inputs — structurally enforced by `ScenarioInputs`). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed tests | `uv run pytest backend seed` | 231 passed |
| `make test` (backend + seed + all frontend packages) | `make test` | all green (209 backend, 22 seed, 1+27+3+3+4+4 frontend) |
| `make lint` (ruff, mypy, eslint, tsc, prettier) | `make lint` | all green |
| Demo reset timing | `time make demo-reset` (run twice) | `elapsed: 1.8s` / `1.8s`, identical background counts both times |

## Review findings (stage 6)

(left for the fresh reviewer)

## How to test manually

1. `make up` (if the shared stack is down).
2. `make demo-reset` — prints a summary; every persona should land at its
   spec.md "Seed end status".
3. `uv run pytest backend seed -q`.
4. `make lint` / `make test`.

## Follow-ups

- None outstanding for this item. `seed/pricing_seam.py` calls CQ-013's
  functions directly with no fallback branch to maintain.
- If CQ-011's real Temporal workflow (still in progress) ever needs a
  credit-pull activity, `seed/loader.py::_seed_representative_fico` is the
  reference implementation for what that activity should do (same mock
  client, same field_key).
