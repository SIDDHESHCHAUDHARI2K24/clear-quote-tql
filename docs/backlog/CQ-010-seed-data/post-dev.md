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
| CI (GitHub Actions, push to `cq-010-seed-data`) | `gh run view 36107535016` | **success** — `backend` job (ruff/mypy/`pytest backend`) 55s, `frontend` job (eslint/tsc/prettier/vitest) 35s |
| CI (review round 1 fix commit `89bcf5f`) | `gh run view 36110425999` | **success** — `backend` job 48s, `frontend` job 30s |

Note: CI's `backend` job runs `uv run pytest backend` only (not `seed`) — `.github/workflows/ci.yml` is CQ-006's owned file and out of this item's scope to change. `seed/`'s YAML/config files are still checked by the frontend job's `pnpm exec prettier --check .`. `seed`'s own pytest/ruff/mypy suite is verified locally (this table, above) and via `make test`/`make lint`.

## Review findings (stage 6)

Fresh reviewer (did not write this code). Verified live against the shared
stack, not just by reading the post-dev log.

### Commands re-run

| Command | Result |
| --- | --- |
| `make up` | stack already healthy; confirmed all 6 `clear-quote-*` containers healthy |
| `time make demo-reset` (run 1) | `elapsed: 1.8s`; 10/10 personas at spec.md's exact "Seed end status"; background: `{'intake': 28, 'verifying': 27, 'needs_attention': 24, 'ready_to_price': 31, 'stale': 12, 'priced': 53, 'sent': 25}`, 100/100 by LO |
| `time make demo-reset` (run 2) | `elapsed: 1.7s`; identical status/LO counts to run 1 (AC5 confirmed live) |
| Direct `psql` query, `cq_dev` | all 10 personas present with correct `status`/`occupancy`/`strategy`; Marcus Hale's persisted `quotes.computed`: `dscr_ratio=0.82`, `monthly_cashflow=-360.53`, `year_one_tax_savings=24275.78`, `title_fees=2394.00` (0.7% of $342,000) — matches post-dev.md's claims exactly |
| Direct `psql` query, `cq_dev` | Grace Kim `quote_packages.sent_at` = 2026-08-31 (25 days before today, 2026-09-25), `borrower_action` null; Luis Romero `sent_at`=09-22 (3d), `viewed_at`=09-23 (2d), `borrower_action='option_selected'` — AC7 confirmed live |
| DB isolation check | `\l` on the shared Postgres shows `cq_dev`, `cq_dev_p2`, `cq_test`, `cq_test_p2`, `temporal`, `temporal_visibility` as separate databases; `seed/reset.py` calls `get_settings().database_url` (`DATABASE_URL`→`cq_dev`), never `TEST_DATABASE_URL`; confirmed `cq_test` untouched |
| `make lint` | pass — ruff, ruff format, mypy, eslint (4 pkgs), tsc (4 pkgs), prettier all clean |
| `make test` | pass — `seed`: 22/22; frontend: 1+27+4+4 all green (backend suite already covered by CI, see below) |
| `gh run view 36107535016 --job=... --log` | confirms `backend` job ran `uv run pytest backend`, **collected 209 items**, no `seed` tests in that job's log (see finding #6) |
| `gh run view 36107711947` | success, same shape as above |

### Findings

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | major | `docs/backlog/CQ-010-seed-data/plan.md:19-25` (decision #10), `seed/loader.py:272-290` | Persona 7 (Aisha Coleman) is promised identically in three docs — `docs/design/system-design.md:332` ("Cannot price: missing Occupancy"), this item's own `spec.md` persona table row 7, and `docs/backlog/CQ-012-verification-rules/spec.md:96` (which prescribes `write_flag(..., field_key="occupancy_type", ...)` by name and is itself unit-tested that way in `backend/app/features/applications/verification/tests/test_personas.py:96` — `assert flag.field_key == "occupancy_type"`). The actual seeded/live Aisha Coleman instead produces `flags.field_key = "RepresentativeFICO"` (confirmed live via `psql`: `aisha.coleman@... | pricing | RepresentativeFICO | ob_required_field | blocking`), i.e. "Cannot price: missing RepresentativeFICO". The technical claim ("Occupancy is non-nullable so it can't literally be missing") is correct against the current schema (`backend/app/features/applications/models.py:63`, `Mapped[Occupancy]` non-nullable) and against `ob_request.py:105` (`Occupancy` is always derived from that non-nullable column, never `None`) — but that constraint is itself a byproduct of this item's own earlier decision #2 (occupancy is LO-entered at intake, before `import_from_los` ever runs, so it's never sourced from the LOS import at all). Two of this item's own decisions combine to silently break a demo narrative that three separate specs promise word-for-word, with no Kaneo `needs-input` comment raised (AGENTS.md's gate for "big gaps") and no test anywhere that pins the flag text/field_key CQ-010 actually produces for this persona — a future regression to a third field would go undetected. | Either (a) get explicit sign-off (Kaneo comment) to formally retire the "missing Occupancy" wording project-wide and update `system-design.md` §"Seed data personas" + CQ-012's spec text to match `RepresentativeFICO`, adding a test in `seed/tests/` that pins Aisha's actual `flags.field_key`/message; or (b) make `applications.occupancy` nullable until the LO (or a real LOS-sourced value) sets it, so persona 7's LOS-side defect can propagate as originally designed. |
| 2 | major | `seed/loader.py:272-290` (`_seed_representative_fico`) | `system-design.md:116` ("Soft pull on import; liabilities imported...") and the integrations table (`:231`, `CreditClient`: "Soft pull (Experian only) or hard pull (3 scores → middle)") both describe representative FICO as populated by a **soft** pull at import time, with a **hard** pull being a distinct, LO-triggered, consent-gated action. `_seed_representative_fico` instead calls `credit_client.pull_credit(loan_number, CreditPullType.HARD_PULL)` directly. More importantly, this function isn't part of `import_from_los` (this item's owned pipeline stage) or any CQ-013/CQ-011 stage — grep confirms `MockCreditClient.pull_credit` is called nowhere else in `backend/app` outside tests, meaning the **real** (non-seeded) Temporal pipeline (CQ-011, in flight) has no path today to ever populate `field_values.representative_fico`; `auto_price`/`validate_ob_required_fields` will always fail "Cannot price: missing RepresentativeFICO" for any real, non-seed-created application. This directly undercuts Decision D1's own stated guarantee ("demo-reset and the real pipeline agree") for this one field, and was decided-and-logged (plan.md decision #10, post-dev.md follow-up) rather than raised to Kaneo as the missing-pipeline-stage gap it actually is. | Charter a real "soft pull on import" step (ideally inside `import_from_los` or a small new owned service CQ-011 can wrap as an activity, per Decision D1's own pattern) that calls `CreditClient` with `SOFT_PULL`; have seeding rely on that same function instead of a seed-only helper using the wrong pull type. Flag this to CQ-011's owner now, since it's in flight and will otherwise wrap `import_from_los` without ever getting a FICO. |
| 3 | major (FIXED, round 2) | `seed/users.yaml:19,27,35,43` (as of round 1) | A plaintext demo password was committed to the repo, reused verbatim across all 4 staff accounts (2 LO, Manager, Admin). Once CQ-014 wires real login, this would become a live, working, identical credential for every seeded staff account, visible to anyone with read access to the repo/git history. | **Fixed:** the plaintext no longer appears anywhere in the tree (grepped clean, docs included). `seed/loader.py::seed_users` now reads it from env `SEED_STAFF_PASSWORD` (`.env.example`, empty by default) and bcrypt-hashes it at seed time; `make demo-reset` fails fast with a clear message (before touching the DB) if the var is unset. `seed/users.yaml` carries no `password` field at all. |
| 4 | minor | `backend/app/features/pricing/enrichment/service.py:172-177`, `seed/providers/rents.yaml`, `seed/providers/str_revenue.yaml` | `system-design.md:227-228` specifies RentCast/AirDNA lookups "by zip × beds", but CQ-013's `_enrich_str_revenue`/LTR equivalent query `provider_rents`/`provider_str_revenue` by `(zip, property.number_of_units)` — a different, unrelated concept (`number_of_units` is 1 for SFR regardless of bedroom count; `Property` has no beds column at all). CQ-010 correctly adapted its own fixtures to match the code it depends on (out of scope to fix CQ-013's lookup) and documented this as decision #11 — reasonable given item boundaries — but the underlying spec-vs-implementation mismatch in CQ-013 (already merged/in-review) was not raised to CQ-013's owner or logged as a follow-up; post-dev.md's Follow-ups section says "None outstanding." | File a Kaneo comment / follow-up against CQ-013 noting the beds-vs-number_of_units mismatch so a future item doesn't have to rediscover it when adding a second bedroom count to the persona set. |
| 5 | minor | `.github/workflows/ci.yml` (CQ-006-owned) | CI's `backend` job runs `uv run pytest backend` only — confirmed via `gh run view --log` on both cited runs ("collected 209 items", no `seed` tests present). All 8 of this item's ACs are therefore verified only by local/manual runs (this table, above, and the author's own log), never continuously by CI. Disclosed transparently in post-dev.md's note, but not filed as a Kaneo follow-up against CQ-006. | Add a `uv run pytest seed` step (or a separate job with its own Postgres/MinIO services) to `ci.yml`, coordinating with CQ-006's owner since that file is out of this item's scope. |
| — | none | `seed/providers/str_revenue.yaml` (Tampa, zip 33602) | Checked per the brief: the Tampa STR revenue fixture (`annual_revenue: "24000"`) is a raw provider **input**, not a typed output — DSCR 0.82 / cashflow -$360.53 / tax savings $24,275.78 are all computed downstream by `quote_engine` and independently confirmed via direct `psql` query against the live DB. Compliant with AGENTS.md's money-math-in-quote_engine-only rule. No finding. |
| — | none | `backend/app/integrations/los/schemas.py` | `LoanFileDTO`'s new fields (`employment`, `liabilities`, `assets`, `co_borrower_dob`) are genuinely additive/optional with safe defaults; nothing else read this DTO before, confirmed via grep. No finding. |
| — | none | `seed/users.yaml` (Jordan Lee `id`), `.env.example` `DEV_LO_ID` | Pinning matches; grepped `seed/` and `docs/` for other plaintext secrets — none found beyond finding #3. No finding beyond #3. |

Minor/nit count beyond the table above: 0 additional.

## Review round 2 (fixes for round 1's findings #1/#2/#3)

New migration: **`e7b20ff388a7`** ("applications occupancy nullable"),
`down_revision = 8aa99c7f2577`. `alembic check` clean; `upgrade` /
`downgrade -1` / `upgrade` cycle verified against the shared stack.
`export_openapi.py` re-run: byte-identical `openapi.json` (no
API-exposed schema references `occupancy`), so no `packages/api-client`
regen was needed.

| Finding | Fix | Evidence |
| --- | --- | --- |
| #1 (major) — Aisha Coleman doesn't produce "Cannot price: missing Occupancy" | `applications.occupancy` now nullable; `import_from_los` copies it from the LOS record (`None` for Aisha); `ob_request.py`'s `Occupancy` field is `None` (not defaulted) when unknown; `enrichment/service.py` maps that one field to `flags.field_key="occupancy_type"` | Live psql check after `make demo-reset`: `occupancy=None, status=needs_attention`, `activity_events.payload={'reason': 'Cannot price: missing Occupancy'}`, `flags: tab=pricing, field_key=occupancy_type, rule=ob_required_field, severity=blocking`. Pinned in `backend/app/features/pricing/enrichment/tests/test_occupancy_validation.py` (2 tests: exact message/field_key, and resolve-once-fixed). |
| #2 (major) — no path to `representative_fico` for the real pipeline | `import_from_los` now runs a real soft credit pull and writes `field_values.representative_fico` itself; `seed/loader.py::_seed_representative_fico` deleted | `backend/app/features/applications/tests/test_service.py`: `test_import_from_los_writes_representative_fico_from_soft_pull`, `test_import_from_los_raises_when_credit_report_missing`, `test_import_from_los_copies_occupancy_from_los_record` |
| #3 (major) — plaintext password committed | `seed/users.yaml`'s `password` field removed; `seed_users` reads `get_settings().seed_staff_password` (`.env`'s `SEED_STAFF_PASSWORD`, empty by default); `demo-reset` fails fast (before touching the DB) if unset | `grep -rn "ClearQuoteDemo" .` (docs included) → clean. `seed/tests/test_users_seeded.py::test_seed_users_fails_clearly_when_password_setting_unset`. Live: `make demo-reset` with the var unset printed the clear error and exited 1 without touching the schema. |

Live re-verification, all 10 personas, after both fixes (`time make
demo-reset`, run twice): `elapsed: 1.3s` / `1.3s` (well under 60s).
`marcus_hale/kathleen_mcreynolds/priya_nair/daniel_ortiz/sam_reed/
tom_lisa_brandt → priced`, `aisha_coleman/ben_ford → needs_attention`,
`grace_kim → sent`, `luis_romero → option_selected` — identical both runs.

## How to test manually

1. `make up` (if the shared stack is down).
2. Set `SEED_STAFF_PASSWORD` in `.env` (see `.env.example`).
3. `make demo-reset` — prints a summary; every persona should land at its
   spec.md "Seed end status".
4. `uv run pytest backend seed -q`.
5. `make lint` / `make test`.

## Follow-ups

- Minor finding #4 (CQ-013's `provider_rents`/`provider_str_revenue` keyed
  by `property.number_of_units`, not a bedroom count) — left as-is per
  orchestrator's call; flag to CQ-013's owner if a second bedroom count
  is ever added to the persona set.
- Minor finding #5 (CI's `backend` job doesn't run `uv run pytest seed`) —
  left as-is; orchestrator will handle in the CI pass (`.github/workflows/
  ci.yml` is CQ-006-owned, out of this item's scope).
- If CQ-011's real Temporal workflow (still in progress) wraps
  `import_from_los` as its `import_application` activity, it now gets a
  real soft-pull FICO for free — no separate credit-pull activity needed.
