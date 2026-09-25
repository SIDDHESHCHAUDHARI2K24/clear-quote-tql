# CQ-007 Data model & migrations

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-004 |
| Kaneo task | CQ-007 in Kaneo (task id `c0f4xk5paitioqj31c54yth9`) |
| Branch | `cq-007-data-model` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

Every later item (engine, adapters, rules, pipeline, API, UI) reads and writes the same tables and enums. When this is done, `alembic upgrade head` builds the full schema on a clean Postgres and every feature's `models.py` imports from it without guessing column names.

## Scope

All tables in `system-design.md`'s Data model section (plus `integration_calls`, needed by CQ-009/CQ-029 and not named there — see Decision below), the enums implied by the status machine and the catalog overrides, indexes on every FK and filterable column, and SSN encryption at rest. One Alembic migration builds the whole schema; CQ-007 also seeds the `settings` table's default rows (fee constants, ratios, config), not persona data.

## Out of scope

- Adapter implementations that read `provider_*` tables (CQ-009).
- `quote_engine` computation logic (CQ-008) — tables here only store its JSONB inputs/outputs.
- Verification rule logic that writes `flags`/`field_values` (CQ-012) — this item only defines the tables.
- Pricing/enrichment service logic (CQ-013).
- Auth/session/OTP logic for `users`/`borrower_accounts` (CQ-014, CQ-015) — this item only defines the tables.
- Persona and generated seed rows, `make demo-reset` (CQ-010).

## References

- `docs/design/system-design.md` — "Application status machine", "Data model", "Emulated integrations", "Repo layout", Decisions log #1, #2.
- `docs/design/data-field-catalog.md` — sections 1–5, 7, 9, 11, 12; overrides O1, O2, O9, O11, O12.

## Enums

Cross-cutting enums live in `backend/app/core/enums.py` (imported by many features' models — avoids circular imports). Feature-specific enums live beside their owning model (noted below). `native_enum=True` (Postgres enum types); values are lower_snake_case.

| Enum | Values | Home |
| --- | --- | --- |
| `UserRole` | `lo`, `manager`, `admin` | `core/enums.py` |
| `ApplicationStatus` | `intake`, `verifying`, `needs_attention`, `ready_to_price`, `priced`, `sent`, `viewed`, `option_selected`, `inquiry`, `stale`, `withdrawn`, `closed` | `core/enums.py` — mirrors the status machine incl. terminal `withdrawn`/`closed` set by the LO |
| `Occupancy` | `primary`, `investment` | `core/enums.py` — per override O2, no `second_home` |
| `Strategy` | `ltr`, `str` | `core/enums.py` — null on `applications.strategy` when `occupancy = primary` |
| `LoanPurpose` | `purchase` | `core/enums.py` — single member per override O1; kept as an enum (not a bool) so refinance can be added later without a column type change |
| `PartyRole` | `borrower`, `co_borrower` | `applications/models.py` |
| `MaritalStatus` | `married`, `unmarried`, `separated` | `applications/models.py` |
| `BusinessVesting` | `title_lien_in_llc`, `personal_name` | `applications/models.py` |
| `HousingStatus` | `own`, `rent`, `rent_free` | `applications/housing/models.py` |
| `PropertyAddressStatus` | `specific_address`, `tbd` | `applications/property/models.py` |
| `PropertyType` | `single_family`, `two_to_four_unit`, `condo`, `townhome` | `applications/property/models.py` |
| `FieldSource` | `encompass`, `rentcast`, `airdna`, `smartasset`, `steadily`, `optimal_blue`, `credit_bureau`, `property_search`, `lo_entry`, `formula`, `default`, `lo_override` | `core/enums.py` — drives the source badge + revert-to-source UI |
| `ApplicationTab` | `borrowers`, `housing`, `credit`, `assets`, `property`, `pricing`, `send` | `core/enums.py` — matches the 7 workspace tabs |
| `FlagSeverity` | `info`, `warning`, `blocking` | `core/enums.py` — **Decision**: `blocking` halts pipeline progression (Verifying → NeedsAttention) and blocks Send; `warning` is a visible tab count only; `info` is reserved for auto-fix outcomes and never becomes a `flags` row |
| `BorrowerAction` | `option_selected`, `inquiry` | `quotes/send/models.py` |
| `ConsentType` | `hard_pull` | `borrower/consent/models.py` |
| `EmailStatus` | `queued`, `sent`, `failed` | `notifications/outbox/models.py` |
| `RateSheetProgram` | `conventional`, `dscr` | `integrations/pricing/models.py` |
| `DealGrade` | `great_buy`, `good_buy` | `integrations/property_search/models.py` |
| `CreditPullType` | `soft_pull`, `hard_pull` | `integrations/credit/models.py` |

## Conventions (all tables)

- PK `id: Mapped[uuid.UUID]` = `postgresql.UUID(as_uuid=True)`, `default=uuid.uuid4`.
- `created_at: Mapped[datetime]` = `DateTime(timezone=True)`, `server_default=func.now()`. `updated_at` same, plus `onupdate=func.now()`. Append-only tables (`activity_events`, `consents`) omit `updated_at`.
- Every FK column is indexed. Child-of-application tables cascade on delete (`ondelete="CASCADE"`).
- Migrations: `alembic/versions/<rev>_<slug>.py` (Alembic's default `%(rev)s_%(slug)s` template). This item's migration slug is `initial_schema`, generated with `uv run alembic revision --autogenerate -m "initial schema"`, plus one data-only follow-up migration `seed_settings_defaults` that inserts the default `settings` rows. Later items add their own numbered revisions; never edit a merged revision.

## Tables by owning module

### `backend/app/features/auth/models.py`

| Table | Columns |
| --- | --- |
| `users` | id, email (unique, indexed), password_hash, role (`UserRole`), full_name, nmls (nullable), title (nullable), phone (nullable), created_at, updated_at |
| `borrower_accounts` | id, client_id (FK `clients.id`, unique), email (unique, indexed), last_login_at (nullable), created_at, updated_at |

### `backend/app/features/clients/models.py`

| Table | Columns |
| --- | --- |
| `clients` | id, full_name, email (indexed), phone (nullable), assigned_lo_id (FK `users.id`), crm_contact_id (nullable), created_at, updated_at |

### `backend/app/features/applications/models.py`

| Table | Columns |
| --- | --- |
| `applications` | id, client_id (FK `clients.id`), lo_id (FK `users.id`), los_loan_guid (nullable, unique), status (`ApplicationStatus`, default `intake`, indexed), occupancy (`Occupancy`), strategy (`Strategy`, nullable), program (nullable string), purpose (`LoanPurpose`, default `purchase`), requested_price (Numeric 12,2, nullable), subject_state (String(2), nullable, indexed — denormalized for the applications-list filter), created_at, updated_at |
| `application_parties` | id, application_id (FK, cascade), role (`PartyRole`), first_name, last_name, ssn_encrypted (LargeBinary, nullable — see Encryption below), dob (Date, nullable), marital_status (`MaritalStatus`, nullable), dependents_count (Integer, default 0), email (nullable), cell_phone/home_phone/work_phone (nullable), business_vesting (`BusinessVesting`, nullable), llc_entity_name (nullable), no_co_applicant_check (Boolean, default false), created_at, updated_at. Unique (application_id, role) |

### `backend/app/features/applications/housing/models.py`

| Table | Columns |
| --- | --- |
| `housing_history` | id, application_id (FK, cascade, indexed), sequence (Integer, 0 = current), street_address, city, state (String(2)), zip (String(5)), housing_status (`HousingStatus`), residence_years (Integer), residence_months (Integer), vom_completed (Boolean, default false), created_at, updated_at |

### `backend/app/features/applications/credit/models.py`

| Table | Columns |
| --- | --- |
| `liabilities` | id, application_id (FK, cascade, indexed), creditor_name, account_type, monthly_payment (Numeric 10,2), balance (Numeric 12,2), created_at, updated_at |

`total_monthly_liabilities` and `representative_fico`/`credit_score_bracket` are not stored columns — they are `field_values` entries (FICO/bracket come from `CreditClient`; the liabilities total is `SUM(liabilities.monthly_payment)`), so a re-import never leaves a stale cached total.

### `backend/app/features/applications/assets/models.py`

| Table | Columns |
| --- | --- |
| `assets` | id, application_id (FK, cascade, indexed), account_type (nullable), institution (nullable), verified_amount (Numeric 12,2), created_at, updated_at |
| `employment` | id, application_id (FK, cascade, indexed), party_id (FK `application_parties.id`, nullable), employer_name (nullable), monthly_income (Numeric 12,2, nullable), years_at_job (Numeric 4,1, nullable), self_employed (Boolean, default false), created_at, updated_at — **Decision**: the catalog has no defined employment schema (override O12 only says the fields were "added"); this is the minimal shape `dti_primary` (CQ-012) needs. Expand if a later item needs more. |
| `documents` | id, application_id (FK, cascade, indexed), doc_type (string: `pay_stub`/`w2`/`tax_return`/`bank_statement`/...), object_key (MinIO key), received_at (DateTime, nullable), created_at, updated_at |

### `backend/app/features/applications/property/models.py`

| Table | Columns |
| --- | --- |
| `properties` | id, application_id (FK, cascade, unique), address_status (`PropertyAddressStatus`), street_address/city (nullable), state (String(2), nullable), zip (String(5), nullable), county (nullable), property_type (`PropertyType`), number_of_units (Integer, default 1), buy_box_states (ARRAY(String), default `[]`), buy_box_metros (ARRAY(String), default `[]`), recommend_matches (Boolean, default true), created_at, updated_at |

### `backend/app/features/applications/verification/models.py`

CQ-012 owns the rule logic that populates these; this item defines the shape.

| Table | Columns |
| --- | --- |
| `field_values` | id, application_id (FK, cascade, indexed), field_key (String, indexed), value (JSONB), source (`FieldSource`), source_ref (nullable — e.g. a `provider_*` row id), overridden_by (FK `users.id`, nullable), overridden_at (nullable), created_at, updated_at. Unique (application_id, field_key) |
| `flags` | id, application_id (FK, cascade, indexed), tab (`ApplicationTab`), field_key (String), rule (String — rule id, e.g. `housing_history_24mo` or `ob_required_field`), severity (`FlagSeverity`), resolved_at (nullable), created_at, updated_at. Index (application_id, resolved_at) |

### `backend/app/features/applications/timeline/models.py`

| Table | Columns |
| --- | --- |
| `activity_events` | id, application_id (FK, cascade, indexed), actor (String — user id or `"system"`), type (String — e.g. `stage.completed`, `email.sent`, `flag.raised`), payload (JSONB), at (DateTime, indexed), created_at |

### `backend/app/features/pricing/scenarios/models.py`

| Table | Columns |
| --- | --- |
| `scenarios` | id, application_id (FK, cascade, indexed), inputs (JSONB), config_snapshot (JSONB — the `settings` snapshot used, per system-design "old quotes never change when defaults do"), dscr_bucket (String, nullable — one of CQ-008's `DSCRBucket` member names: `BELOW_1_00`/`ONE_TO_1_25`/`GE_1_25`), created_at, updated_at |

### `backend/app/features/quotes/builder/models.py`

| Table | Columns |
| --- | --- |
| `quotes` | id, scenario_id (FK, cascade, indexed), investor, product, rate (Numeric 6,3), points (Numeric 6,3), lock_days (Integer), computed (JSONB — full `quote_engine` output), label (String — `Par`/`Buydown`/`Manual`), priced_at (DateTime), created_at, updated_at |

### `backend/app/features/quotes/send/models.py`

| Table | Columns |
| --- | --- |
| `quote_packages` | id, application_id (FK, indexed), quote_ids (ARRAY(UUID)), recommended_quote_id (FK `quotes.id`, nullable), lo_note (Text, nullable), letter_key (String, nullable — MinIO key), report_token (String, unique, indexed — the magic-link token), sent_at/expires_at/viewed_at (nullable), borrower_action (`BorrowerAction`, nullable), created_at, updated_at |

### `backend/app/features/borrower/consent/models.py`

| Table | Columns |
| --- | --- |
| `consents` | id, application_id (FK, cascade, indexed), type (`ConsentType`), text_hash (String), ip (String), at (DateTime), created_at |

### `backend/app/features/notifications/outbox/models.py`

| Table | Columns |
| --- | --- |
| `outbox_emails` | id, to_email, subject, html (Text), attachment_keys (ARRAY(String), default `[]`), status (`EmailStatus`, default `queued`), application_id (FK, nullable, indexed), created_at, updated_at |

### `backend/app/features/settings/models.py`

| Table | Columns |
| --- | --- |
| `settings` | key (String, PK), value (JSONB), description (String, nullable), updated_at, updated_by (FK `users.id`, nullable) |

Default rows inserted by the `seed_settings_defaults` migration (not CQ-010 persona seed): `fee_lender_processing=995.00`, `fee_lender_underwriting=795.00`, `title_pct=0.007`, `str_expense_ratio=0.20`, `insurance_default_pct=0.005`, `land_allocation_pct=0.20`, `accelerated_property_pct=0.25`, `bonus_depreciation_pct=1.00`, `investor_marginal_tax_rate=0.32`, `prepaid_interest_days=15`, `prepaid_insurance_months=14`, `prepaid_tax_months=3`, `reserves_months_primary=2`, `reserves_months_investment=6`, `stale_quote_days=21`, `report_link_expiry_days=7`.

### `backend/app/integrations/<name>/models.py` — provider seed tables

Read-only from the mock adapters' point of view (CQ-009 writes seed rows via CQ-010; adapters only `SELECT`).

| Table | Module | Columns |
| --- | --- | --- |
| `provider_los_records` | `integrations/los/models.py` | id, loan_number (unique), payload (JSONB — full mocked 1003 record, field names from the catalog), created_at |
| `provider_rate_sheet` | `integrations/pricing/models.py` | id, investor_name, product_name, program (`RateSheetProgram`), base_rate (Numeric 6,3), base_price (Numeric 6,3), min_fico (Integer), max_ltv (Numeric 5,2), dscr_bucket (String, nullable), ppp_years (Integer, nullable), str_only (Boolean, default false), lead_source (String, nullable), lock_days (Integer), fico_adjustment_bps (Numeric 6,2, default 0), ltv_adjustment_bps (Numeric 6,2, default 0), active (Boolean, default true), created_at |
| `provider_rents` | `integrations/rent/models.py` | id, zip (String(5)), beds (Integer), market_rent (Numeric 10,2), rent_low/rent_high (Numeric 10,2), comps_count (Integer), as_of (Date), created_at |
| `provider_str_revenue` | `integrations/str/models.py` | id, zip (String(5)), beds (Integer), annual_revenue (Numeric 12,2), occupancy_pct (Numeric 5,2), adr (Numeric 8,2), comps_count (Integer), as_of (Date), created_at |
| `provider_tax_rates` | `integrations/tax/models.py` | id, county, state (String(2)), annual_rate_pct (Numeric 6,4), source_name, as_of (Date), created_at. Unique (county, state) |
| `provider_insurance_factors` | `integrations/insurance/models.py` | id, state (String(2), unique), annual_rate_pct (Numeric 6,4, default 0.50), source_name (default `Steadily`), created_at |
| `provider_listings` | `integrations/property_search/models.py` | id, address, city, state (String(2)), zip (String(5)), metro, list_price (Numeric 12,2), beds (Integer), baths (Numeric 3,1), sqft (Integer), property_type (`PropertyType`), image_url, deal_grade (`DealGrade`), tagline (nullable), created_at |
| `provider_credit_reports` | `integrations/credit/models.py` | id, loan_number, pull_type (`CreditPullType`), experian_score/equifax_score/transunion_score (Integer, nullable), middle_score (Integer), tradelines (JSONB), created_at |
| `crm_events` | `integrations/crm/models.py` | id, contact_id, event_type, payload (JSONB), at (DateTime), created_at — **Decision**: not a `provider_*` seed table (CRM is written to, not read); kept in the CRM adapter's own module |
| `integration_calls` | `integrations/common/models.py` | id, adapter (String), request_summary (JSONB), success (Boolean), latency_ms (Integer), error_code (String, nullable), application_id (FK `applications.id`, nullable, indexed), called_at (DateTime, indexed), created_at — **Decision**: not named in system-design.md's Data model table; added because CQ-009's adapter-call log and CQ-029's Integration panel need somewhere to read "last call, latency, result" from |

## SSN encryption

Fernet symmetric encryption (`cryptography.fernet.Fernet`). `backend/app/core/encryption.py` defines `EncryptedString(TypeDecorator)` (impl `LargeBinary`): `process_bind_param` encrypts UTF-8 plaintext to a Fernet token before insert; `process_result_value` decrypts on read. The key comes from settings field `field_encryption_key: str`, populated from env `FIELD_ENCRYPTION_KEY` (32-byte urlsafe-base64, `Fernet.generate_key()` format). App startup (`core/config.py`, from CQ-004) fails fast if `FIELD_ENCRYPTION_KEY` is unset outside `APP_ENV=test` (CQ-004's actual settings field/env var is `app_env`/`APP_ENV`, not a separate `ENVIRONMENT` var — `backend/conftest.py` sets `APP_ENV=test` for the pytest session). Only `application_parties.ssn_encrypted` uses this type; DOB is plain `Date` (not masked in the catalog).

## Acceptance criteria

- [ ] AC1 — `alembic upgrade head` succeeds on a clean DB; model tests pass. *(roadmap exit check)*
- [ ] AC2 — Every table listed above exists with the FK relationships and cascade rules described; a test walks `Base.metadata.tables` and asserts the full set of table names.
- [ ] AC3 — Every enum above exists as a Postgres enum type with exactly its listed values; `ApplicationStatus` includes `withdrawn` and `closed`.
- [ ] AC4 — Writing an `application_parties` row with a plaintext SSN and reading it back through raw SQL (bypassing the ORM) returns ciphertext, not the original digits; starting the app without `FIELD_ENCRYPTION_KEY` set and `APP_ENV` not `test` raises at import/startup.
- [ ] AC5 — `alembic downgrade base` then `alembic upgrade head` round-trips without error (migration reversibility).
- [ ] AC6 — After `seed_settings_defaults`, every key listed under `settings` above is present with its documented value.
- [ ] AC7 — All 9 `provider_*`/`crm_events`/`integration_calls` tables from the integrations table exist, so CQ-009 has a target schema to read/write against.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Migration | `uv run alembic upgrade head` against a throwaway test DB (CI/local Postgres) |
| AC2 | Unit | `pytest backend/tests/test_schema.py::test_all_tables_present` |
| AC3 | Unit | `pytest backend/tests/test_schema.py::test_enum_values` |
| AC4 | Unit | `pytest backend/app/core/tests/test_encryption.py` |
| AC5 | Migration | `uv run alembic downgrade base && uv run alembic upgrade head` |
| AC6 | Integration | `pytest backend/app/features/settings/tests/test_defaults.py` |
| AC7 | Unit | `pytest backend/tests/test_schema.py::test_provider_tables_present` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: enum placement (`core/enums.py` vs feature module) as tabulated above — done to avoid circular imports between features that share a status/severity/source vocabulary.
- Decision: `FlagSeverity` semantics (blocking/warning/info) — not specified in system-design.md; CQ-012 and CQ-013 depend on this meaning, so treat it as load-bearing, not cosmetic.
- Decision: `settings` is a single key/value table rather than typed columns per config item, so Admin (Tier C) can add new keys without a migration.
- If Postgres native enums prove painful for later additions (adding a value needs `ALTER TYPE ... ADD VALUE` outside a transaction), a follow-up item may switch to `String` + `CheckConstraint`; log that as a `Decision:` in this item's `plan.md` if it happens, don't silently deviate.
