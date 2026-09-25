# Data Field Catalog

Catalog of data fields extracted from the video walkthroughs (Chris Paliska kickoff and Evan Hoy live workflow demo), the Encompass LOS screens, the Optimal Blue pricing engine, the loan advisor Excel models, the pre-approval letter templates and the Project Brief v3.

Each field is mapped to its **source of truth** (Encompass, third-party API, loan officer entry or formula) and its **target deliverable** (LO Console, Optimal Blue payload, borrower email/portal, pre-approval PDF, detailed PDF).

## Read this first: overrides from `system-design.md`

This catalog is the raw source. Where it disagrees with `docs/design/system-design.md`, **the design doc wins**. CQ-007 trims this catalog to the fields the data model needs.

| # | Catalog says | Binding decision |
| --- | --- | --- |
| O1 | `loan_purpose` includes `Refinance_Rate_Term`, `Refinance_Cash_Out` | Purchase only. Refinance is out of scope |
| O2 | `occupancy_type` includes `Second_Home` | Occupancy is Primary, LTR or STR only |
| O3 | Program examples include FHA-style options | Primary loans are Conventional only |
| O4 | `year_one_tax_deduction = accelerated_basis_amount × bonus_depr_pct` | Deduction = A × bonus% + (B − A) / 27.5 (straight-line on the remainder). This reproduces $75,862 / $24,276 for $342,000 |
| O5 | `cap_rate = NOI / purchase_price` (NOI undefined) | Cap rate = qualifying rent × 12 × 75% ÷ price |
| O6 | "Four numbers" lists 5 items | Primary: 3 hero numbers (payment, cash to close, loan amount + rate). Investment: 4 (payment, cash to close, cashflow, year-1 tax savings). Purchase price sits in the report header |
| O7 | Scenario comparison matrix example mixes down payments, LTR/STR cashflow and inconsistent CTC | Example values are illustrative only. All seed numbers come from the quote engine |
| O8 | `title_escrow_fees` example $2,100 on $342,000 | 0.7% of price ($2,394 on $342,000); the $2,100 figure is for $300,000 |
| O9 | `quote_status` enum | Use the application status machine in `system-design.md` (Intake → … → OptionSelected, Stale, Inquiry, Withdrawn, Closed) |
| O10 | Borrower "accepts" a quote | Borrower chooses "I'd like to move forward with this option" (non-binding) |
| O11 | `asset_sufficiency_check = assets ≥ cash to close` | Assets ≥ cash to close + reserves |
| O12 | Income, employment and DTI fields are absent | Added for primary loans (see `employment` table and verification rules in CQ-012) |

---

## Table of contents

1. Borrower & co-borrower profile fields
2. Housing history & verification fields
3. Credit, assets & liabilities fields
4. Property & buy-box geography fields
5. Loan structure & guideline setup fields
6. Optimal Blue (OB) API integration fields
7. Third-party data enrichment fields
8. Fee engine & closing cost fields
9. Investment analysis & cost segregation fields
10. Borrower "four numbers" & deliverables presentation fields
11. Property match engine fields
12. CRM, system state & audit logging fields

---

## 1. Borrower & co-borrower profile fields

*Captured from the borrower POS (nCino/SimpleNexus) into the Encompass mailbox and mapped into the 1003 application.*

| Field name | Type | Source / origin | Target | Business rules & video notes |
| :--- | :--- | :--- | :--- | :--- |
| `borrower_first_name` | String | Encompass / POS | All | Primary borrower first name. |
| `borrower_last_name` | String | Encompass / POS | All | Primary borrower last name. |
| `borrower_full_name` | String | Encompass / POS | All | e.g. "Kathleen McReynolds", "Marcus Hale". |
| `borrower_ssn` | String (masked) | Encompass / POS | Encompass, Credit | Required for credit pull verification. |
| `borrower_dob` | Date | Encompass / POS | Encompass | Used for identity verification. |
| `marital_status` | Enum | Encompass / POS | Encompass | `Married`, `Unmarried`, `Separated`. |
| `dependents_count` | Integer | Encompass / POS | Encompass | Required on conventional 1003. |
| `borrower_email` | Email | Encompass / POS | CRM, Send Quote | Delivery address for quote & portal links. |
| `borrower_cell_phone` | Phone | Encompass / POS | Encompass, CRM | Evan noted: borrowers enter cell phone, but Encompass requires home phone. |
| `borrower_home_phone` | Phone | Encompass (mapped) | Encompass | Copy `borrower_cell_phone` to `borrower_home_phone` automatically to prevent Encompass validation error. |
| `borrower_work_phone` | Phone | Encompass / POS | Encompass | Optional. |
| `has_co_borrower` | Boolean | Encompass / POS | Encompass | Default `False`. |
| `no_co_applicant_check` | Boolean | Encompass / LO entry | Encompass | **Explicitly flagged by Evan**: "No Co-applicant" must be checked in 1003 or loan validation fails. |
| `co_borrower_full_name` | String | Encompass / POS | Encompass | Populated only if `has_co_borrower = True`. |
| `co_borrower_ssn` | String (masked) | Encompass / POS | Encompass | Populated only if `has_co_borrower = True`. |
| `business_vesting` | Enum | LO entry / intro call | Excel, Letter | `Title + Lien in LLC`, `Personal Name`. DSCR investors frequently vest in an LLC. |
| `llc_entity_name` | String | LO entry | Pre-approval PDF | Used when borrower is taking title under an entity. |

## 2. Housing history & verification fields

*Required for underwriting validation before pre-approval issuance.*

| Field name | Type | Source / origin | Target | Business rules & video notes |
| :--- | :--- | :--- | :--- | :--- |
| `current_street_address` | String | Encompass / POS | Encompass | Current residence street address. |
| `current_city` | String | Encompass / POS | Encompass | Current residence city. |
| `current_state` | String (2-char) | Encompass / POS | Encompass | Current residence state. |
| `current_zip` | String (5-digit) | Encompass / POS | Encompass | Current residence zip. |
| `current_housing_status` | Enum | Encompass / POS | Encompass | `Own`, `Rent`, `Living Rent-Free`. |
| `current_residence_years` | Integer | Encompass / POS | Encompass | Must verify full **2-year (24-month)** history. |
| `current_residence_months` | Integer | Encompass / POS | Encompass | If `years < 2`, previous address fields must be populated. |
| `previous_street_address` | String | Encompass / POS | Encompass | Populated if prior residency < 24 months. |
| `previous_residence_years` | Integer | Encompass / POS | Encompass | Combined total must be ≥ 2 years. |
| `vom_completed` | Boolean | Encompass / LO | Encompass | Verification of mortgage / rent completed. |

## 3. Credit, assets & liabilities fields

| Field name | Type | Source / origin | Target | Business rules & video notes |
| :--- | :--- | :--- | :--- | :--- |
| `credit_pull_type` | Enum | LO entry | Credit bureau API | `Soft_Pull` (pre-qual) vs `Hard_Pull` (full underwriting). Soft pull only pulls Experian (Evan noted). |
| `credit_score_model` | String | Encompass | Encompass / OB | Defaults to `Classic FICO`. |
| `representative_fico` | Integer | Credit API / Encompass | OB, Excel, PDF | Middle score of 3 bureaus or soft-pull score (e.g. 781, 715). |
| `credit_score_bracket` | String | Formula | Pre-approval PDF | e.g. `"780+"`, `"700–719"`. Letter displays score band rather than exact score. |
| `total_monthly_liabilities` | Currency | Encompass ("Import") | Encompass, DTI | Auto-populated by clicking "Import Liabilities". |
| `liabilities_breakdown` | JSON / table | Encompass | Encompass | Table of creditor, account type, monthly payment, balance. |
| `total_verified_assets` | Currency | Encompass / bank statement | PDF, underwrite | Total verified liquid funds (e.g. $135,000). |
| `verified_assets_display` | String | Formula | Pre-approval PDF | Formatted as `"Verified Assets $135K+"`. |
| `asset_sufficiency_check` | Boolean | Formula | LO validation | See override O11: assets ≥ cash to close + reserves. |

## 4. Property & buy-box geography fields

| Field name | Type | Source / origin | Target | Business rules & video notes |
| :--- | :--- | :--- | :--- | :--- |
| `has_subject_property` | Boolean | LO entry / POS | System | `True` if evaluating a specific property; `False` if pre-approval / TBD. |
| `property_address_status` | Enum | System | Pre-approval PDF | `Specific_Address` or `TBD`. |
| `subject_street_address` | String | POS / LO entry | OB, APIs, Letter | e.g. `"4412 W Gray St"` or `"TBD"`. |
| `subject_city` | String | POS / LO entry | OB, APIs, Letter | e.g. `"Tampa"`, `"Asheville"`. |
| `subject_state` | String (2-char) | POS / LO entry | OB, APIs, Letter | e.g. `"FL"`, `"NC"`. |
| `subject_zip` | String (5-digit) | POS / LO entry | OB, APIs, Tax | e.g. `"28803"`, `"33896"`. |
| `subject_county` | String | Zip lookup / Encompass | OB, tax lookup | e.g. `"Buncombe County"`, `"Polk County"`. Required for county tax millage lookups. |
| `property_type` | Enum | POS / LO entry | OB, APIs, Excel | `Single_Family` (SFR), `2-4_Unit`, `Condo`, `Townhome`. |
| `number_of_units` | Integer | POS / LO entry | OB, Encompass | 1 for SFR/Condo; 2, 3 or 4 for multi-unit. |
| `number_of_stories` | Integer | POS / Encompass | Encompass | Standard Encompass property metadata. |
| `buy_box_states` | Array[String] | LO entry (multi-select) | Property match | States the borrower wants to invest in (e.g. `["FL", "TX", "NC"]`). LO can tag in 12 seconds. |
| `buy_box_market_cities` | Array[String] | LO entry (multi-select) | Property match | Metros nested under state (e.g. `["Tampa", "Orlando", "Gatlinburg", "Cleveland"]`). |

## 5. Loan structure & guideline setup fields

| Field name | Type | Source / origin | Target | Business rules & video notes |
| :--- | :--- | :--- | :--- | :--- |
| `loan_purpose` | Enum | Encompass / LO entry | OB, Output | See override O1: `Purchase` only. |
| `occupancy_type` | Enum | Encompass / LO entry | OB, All | See override O2: `Primary_Residence`, `Investment_Property`. **Key decision gate for the entire UI.** |
| `investment_strategy` | Enum | LO entry | All | `Long_Term_Rental` (LTR) vs `Short_Term_Rental` (STR). Never display both strategies side by side. |
| `loan_program_name` | String | OB / matrix | Excel, PDF | e.g. `"Conventional 30 YR Fixed"`, `"DSCR 30 YR Fixed"`. |
| `amortization_term_years` | Integer | LO entry / OB | OB, Excel | Default `30` (360 months). |
| `amortization_type` | Enum | LO entry / OB | OB, Excel | `Fixed`, `ARM`. |
| `purchase_price` | Currency | POS / LO entry | OB, Excel, PDF | Approved or contract price (e.g. $300,000, $342,000, $800,000). |
| `appraised_value` | Currency | Encompass / LO entry | OB, Encompass | For purchase, equal to `purchase_price`. |
| `down_payment_pct` | Percentage | LO entry | OB, Excel, PDF | Primary: 3%, 5%, 10%, 15%, 20%. Investment: 15%, 20%, 25%. |
| `down_payment_amount` | Currency | Formula | Excel, summary | `= purchase_price × down_payment_pct`. |
| `base_loan_amount` | Currency | Formula | OB, Excel, PDF | `= purchase_price − down_payment_amount`. |
| `total_loan_amount` | Currency | Formula | OB, Excel, PDF | Equal to base loan amount (unless financing fees). |
| `ltv` | Percentage | Formula | OB, MI matrix | `= total_loan_amount / purchase_price × 100` (e.g. 75.00%, 80.00%, 85.00%). |
| `cltv` / `hcltv` | Percentage | Formula | OB, Encompass | Combined / high combined LTV (equal to LTV if no second lien). |
| `prepayment_penalty_term` | Enum | LO entry / scenario | OB, Excel, PDF | `None`, `1_Year`, `2_Years`, `3_Years`, `5_Years`. **Only applies to DSCR loans; suppressed for primary.** |
| `automated_uw_system` | Enum | Encompass | OB | `Manual_Traditional`, `DU`, `LP`, `Investor_AUS`. DSCR uses `Manual_Traditional`. |
| `lead_source` | Enum | Encompass | OB | `BiggerPockets`, `Zillow`, `Rabbu`, `OfferCloud`, `Employee_Loan`. OB maps pricing adjustments per lead tier. |

## 6. Optimal Blue (OB) API integration fields

*These are the parameters that caused past integration failures when missing or unmapped. The mock `PricingClient` rejects a request that lacks any required field and names the field in the error.*

### Outbound search request payload (Encompass → OB)

```json
{
  "LoanPosition": "First",
  "LoanType": "Conventional",
  "LoanPurpose": "Purchase",
  "BaseLoanAmount": 225000.00,
  "TotalLoanAmount": 225000.00,
  "PurchasePrice": 300000.00,
  "AppraisedValue": 300000.00,
  "LTV": 75.00,
  "CLTV": 75.00,
  "HCLTV": 75.00,
  "RepresentativeFICO": 781,
  "Occupancy": "InvestmentProperty",
  "PropertyType": "SingleFamily",
  "NumberOfUnits": 1,
  "State": "NC",
  "County": "Buncombe",
  "ZipCode": "28803",
  "AmortizationType": "Fixed",
  "AmortizationTerm": 360,
  "PrepaymentPenalty": "5 Years",
  "IncomeVerificationType": "Investor - DSCR",
  "DSCR": 1.00,
  "ShortTermRental": "Yes",
  "Rural": "Yes",
  "LeadSource": "BiggerPockets",
  "AutomatedUW": "Manual/Traditional",
  "DesiredLockDays": 30,
  "SelfEmployed": "No",
  "FirstTimeHomeBuyer": "No",
  "FirstTimeInvestor": "No",
  "CorporateRelocation": "No"
}
```

Value notes: `LoanType` may be `Conventional`, `Conforming`, `Non-Conforming`. `Occupancy` is `PrimaryResidence` or `InvestmentProperty`. `PropertyType` is `SingleFamily`, `Condo`, `TwoToFourUnit`. `PrepaymentPenalty` is `"None"` for primary. `IncomeVerificationType` is `"Full Doc"` for primary. `DSCR` is the assumed or computed value (see the DSCR pricing loop). `Rural` is a conservative worst-case toggle. `DesiredLockDays` is 15, 30, 45 or 60.

### Inbound pricing return fields (OB → Clear Quote)

| Field name | Type | OB mapping | Notes / use |
| :--- | :--- | :--- | :--- |
| `investor_name` | String | Investor / lender | e.g. `"Verus Mortgage Capital"`, `"Deephaven Mortgage"`. |
| `product_name` | String | Product name | e.g. `"Investor Solutions DSCR 30 Yr Fixed - EQ"`. |
| `lock_period_days` | Integer | Lock days | `15`, `30`, `45`, `60`. Standard is 30. |
| `note_rate` | Percentage | Note rate | e.g. 7.125%, 6.875%, 7.500%. |
| `price` / `price_pct` | Percentage | Price | Raw OB price (e.g. `100.250`, `99.125`). |
| `discount_points_pct` | Percentage | Discount points % | Negative is a credit; positive is a discount fee. |
| `discount_points_amount` | Currency | Discount points $ | `= total_loan_amount × discount_points_pct`. |
| `is_par_rate` | Boolean | Formula | Rate closest to 0 points. |
| `is_buydown_rate` | Boolean | Formula | Lower note rate bought with ~0.75%–1.00% points. |
| `piti_ob_estimate` | Currency | P&I amount | Principal and interest returned by OB (the engine recomputes it). |

## 7. Third-party data enrichment fields

| Field name | Type | API source | Fallback / default rule | Target |
| :--- | :--- | :--- | :--- | :--- |
| `market_rent_ltr` | Currency | **RentCast** | Zip median rent | LTR qualifying, cashflow |
| `gross_annual_revenue_str` | Currency | **AirDNA / AIRROI** | Comp-set average annual STR | STR qualifying |
| `gross_monthly_str_revenue` | Currency | Formula | `= gross_annual_revenue_str / 12` | STR cashflow |
| `str_expense_ratio` | Percentage | Configuration | Default **20.00%** | STR calculations |
| `underwritten_str_rent` | Currency | Formula | `= gross_monthly_str_revenue × (1 − 0.20)` | DSCR qualification |
| `property_tax_annual_rate` | Percentage | **SmartAsset / county** | e.g. Buncombe 0.601%, Hillsborough 1.15% | Taxes |
| `property_tax_monthly` | Currency | Formula / tax API | `= purchase_price × property_tax_annual_rate / 12` | PITIA |
| `homeowners_ins_annual` | Currency | **Steadily** | Default **0.50%** of purchase price | PITIA |
| `homeowners_ins_monthly` | Currency | Formula / API | `= homeowners_ins_annual / 12` (Evan padded to $150) | PITIA |
| `hoa_fee_monthly` | Currency | Redfin / Zillow / listing | `$0.00` if SFR; imported if condo | PITIA |

## 8. Fee engine & closing cost fields

*Replicates the loan advisor Excel spreadsheet and the Encompass settlement fee sheet.*

| Field name | Type | Formula / origin | Target | Business rules & notes |
| :--- | :--- | :--- | :--- | :--- |
| `monthly_principal_interest` | Currency | PMT(rate/12, 360, loan_amount) | Excel, summary | e.g. $1,515.87 at 7.125% on $225k. |
| `monthly_property_taxes` | Currency | Tax lookup or override | Excel, summary | e.g. $150.25 (or entered $155.00). |
| `monthly_hazard_insurance` | Currency | Insurance lookup or override | Excel, summary | e.g. $150.00. |
| `monthly_mortgage_insurance` | Currency | MI matrix (LTV × FICO) | Excel, summary | **Primary only**: applies if LTV > 80%. **$0 on DSCR/investment.** |
| `total_monthly_payment` | Currency | P&I + taxes + insurance + MI + HOA | Hero number | Total monthly housing obligation (PITIA). |
| `lender_processing_fee` | Currency | Constant `$995.00` | Excel, closing | Lender-controlled. |
| `lender_underwriting_fee` | Currency | Constant `$795.00` | Excel, closing | Processing + UW = **$1,790.00** (yellow in Excel). |
| `lender_controlled_fees` | Currency | Processing + underwriting | Breakdown | **$1,790.00**. |
| `discount_points_fee` | Currency | `total_loan_amount × discount_points_pct` | Excel, closing | $0 at par; e.g. $1,968.75 for 0.875%. |
| `title_escrow_fees` | Currency | `purchase_price × 0.007` | Excel, closing | Title estimate; see override O8. |
| `prepaid_interest_days` | Integer | Assumption (15 days) | Prepaids | Per-diem interest before first payment. |
| `prepaid_escrows` | Currency | 3 months taxes + 14 months insurance (configurable) | Excel, closing | e.g. $3,867.05 on the $300k reference. |
| `total_closing_costs` | Currency | Lender fees + title + points + prepaids | Breakdown | All transaction costs. |
| `total_cash_to_close` | Currency | Down payment + total closing costs − credits | Hero number | Funds the borrower wires to closing. |
| `appraisal_fee_range` | String | Standard estimate | Excel, PDF | **"~$600–900"**, paid before closing, not in the wire. |

## 9. Investment analysis & cost segregation fields

*Suppressed on primary loans. Shown on investment (LTR/STR) loans.*

| Field name | Type | Formula / origin | Target | Business rules & notes |
| :--- | :--- | :--- | :--- | :--- |
| `dscr_ratio` | Decimal (2 dp) | qualifying_rent / total_monthly_payment | Strategy check | e.g. $2,440 / $2,704.11 = 0.90. Targets ≥ 1.00 or ≥ 1.25. |
| `gross_rent_target_ltr` | Currency | total_monthly_payment × target_dscr | Excel / LO | Break-even monthly rent (at DSCR 1.00 equals PITIA). |
| `gross_rent_target_annual_str` | Currency | total_monthly_payment × 12 / 0.80 | Excel / LO | e.g. $1,820.87 × 12 / 0.8 = **$27,313/yr**. |
| `monthly_net_cashflow` | Currency | qualifying_rent − total_monthly_payment | Hero number | e.g. −$264/mo (STR, Marcus Hale). |
| `annual_net_cashflow` | Currency | monthly_net_cashflow × 12 | Summary | e.g. −$3,169.33/yr. |
| `cap_rate` | Percentage | See override O5 | Property card | e.g. 6.42%. |
| `land_allocation_pct` | Percentage | Config (default **20%**) | Tax calc | Non-depreciable land portion. |
| `land_value_allocation` | Currency | purchase_price × 0.20 | Tax breakdown | e.g. $68,400 on $342,000. |
| `depreciable_building_basis` | Currency | purchase_price × 0.80 | Tax breakdown | e.g. $273,600. |
| `accelerated_property_pct` | Percentage | Config (default **25%**) | Tax calc | 5/7/15-year property. |
| `accelerated_basis_amount` | Currency | depreciable_building_basis × 0.25 | Tax breakdown | e.g. $68,400. |
| `bonus_depreciation_pct` | Percentage | Tax-year config (e.g. 100% / 80%) | Tax calc | First-year bonus %. |
| `year_one_tax_deduction` | Currency | See override O4 | Tax summary | e.g. $75,862. |
| `investor_marginal_tax_rate` | Percentage | LO config (default **32%**) | Tax calc | 24%, 32%, 35%, 37%. |
| `estimated_year_one_tax_savings` | Currency | year_one_tax_deduction × tax_rate | Hero number | e.g. **$24,276** (~$2,023/month). |
| `net_cashflow_incl_tax_benefit` | Currency | monthly_net_cashflow + tax_savings / 12 | Pro forma | e.g. $1,758.87/mo. |

## 10. Borrower "four numbers" & deliverables presentation fields

See override O6 for the binding hero-number set.

### Scenario comparison matrix (side by side)

Compares up to 3 options (par vs buydown vs low cash to close, or 15/20/25% down, or 1y/3y/5y PPP on DSCR). Fields per column: `scenario_name`, `scenario_recommended`, `down_payment_pct`, `prepay_penalty`, `note_rate`, `discount_points_pct`, `monthly_payment`, `cash_to_close`, `monthly_cashflow`, `dscr_ratio`. Example values in the original brief are illustrative only (override O7).

### Pre-approval letter template variables

- `letter_date` — generated date (e.g. `03/29/2026`).
- `borrower_name` — `borrower_full_name` (or `llc_entity_name` when vesting in an LLC).
- `lo_name`, `lo_title`, `lo_nmls`, `lo_phone`, `lo_email` — the assigned LO.
- `lender_entity_name` — Total Quality Lending, NMLS #1933377.
- `purchase_price`, `ltv_percentage`, `loan_term_years`, `fico_bracket`.
- `property_address` or `TBD`.
- `verification_checklist` — documents received (pay stubs, W-2s, tax returns) and asset threshold (e.g. $135K+), generated from the documents table.
- `disclaimer_core` — standard uncommitted-lending disclaimer.
- `portal_url` — link to the borrower report.

## 11. Property match engine fields

| Field name | Type | Source / logic | Target | Rules & notes |
| :--- | :--- | :--- | :--- | :--- |
| `match_floor_price` | Currency | approved_purchase_price × 0.70 | Filter | **Hard floor**: a $1M borrower sees nothing under $700k. |
| `match_ceiling_price` | Currency | approved_purchase_price × 1.00 | Filter | **Hard ceiling**: never show what they cannot finance. |
| `matched_property_id` | String | Property search DB | Match card | Unique reference. |
| `property_image_url` | URL | Search platform | Match card | Exterior image. |
| `property_address` | String | Search platform | Match card | Street, city, state, zip. |
| `bed_bath_sqft` | String | Search platform | Match card | e.g. `"4 bd · 2 ba · 1,710 sqft"`. |
| `deal_grade_badge` | Enum | Search platform criteria | Match card | `Great_Buy`, `Good_Buy`. |
| `deal_ranking_score` | Decimal | Formula | Match order | LTR ranked by monthly cashflow; STR ranked by DSCR. |
| `property_tagline` | String | Search platform | Match card | e.g. `"12 min to theme-park corridor; STR-zoned community"`. |

## 12. CRM, system state & audit logging fields

| Field name | Type | Description & purpose |
| :--- | :--- | :--- |
| `encompass_loan_guid` | String | Unique Encompass identifier; key for re-ingestion. |
| `quote_id` | UUID | Unique Clear Quote ID. |
| `created_at` / `updated_at` | Timestamp | Creation and modification tracking. |
| `rate_lock_expiration` | Timestamp | Used to flag stale rates. |
| `is_rate_stale` | Boolean | True if quote age > 21 days; forces re-pricing before send. |
| `quote_status` | Enum | See override O9. |
| `crm_contact_id` | String | Lead ID in the CRM. |
| `crm_sync_status` | Enum | `Pending`, `Synced`, `Failed`. Logs quote and PDF send history to the contact timeline. |

---

## Why previous builds failed (validation targets)

1. **Missing Encompass → Optimal Blue parameters.** OB returned generic errors because `Occupancy`, `LTV`, `AmortizationType`, `IncomeVerificationType`, `PrepaymentPenalty` and `DSCR` were empty or mis-mapped. Clear Quote validates these before calling OB.
2. **Missing 1003 validation checks.** Not copying `borrower_cell_phone` to `borrower_home_phone`, or leaving `no_co_applicant_check` unchecked, blocked loan creation.
3. **Primary vs investment contamination.** Rent, cashflow, DSCR and cost seg appeared on primary pre-approvals. They are suppressed when `occupancy_type == Primary_Residence`.
4. **Free-text geography.** LOs typed city/state manually for buy-boxes. The two-tier state → metro multi-select replaces it.
