"""`import_from_los`: the pipeline's Import stage.

Owned by CQ-010 (per the orchestrator's ownership split -- see
`docs/backlog/CQ-010-seed-data/plan.md` decision #2). CQ-011 later wraps this
exact function as its `import_application` activity (see that item's
spec.md "Contracts" table): `application_id -> ImportResult`.

Scope (deliberately narrow): given an `applications` row that already has
`los_loan_guid`, `occupancy`, `strategy` and `requested_price` set (written
by whoever created the row -- the LO-import UI, the apply wizard, or
`seed/loader.py` for demo data), this function fetches the loan file from
`LosClient` and writes the five tables the item's spec names:borrower/
co-borrower `application_parties`, `housing_history`, `employment`,
`liabilities` and `assets`. It does **not** create the `applications` row,
does not touch `occupancy`/`strategy`/`purchase_price` (already known at
intake), and does not write `field_values` (CQ-013's enrichment stage owns
that). On success it flips `status` `intake -> verifying`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import (
    Application,
    ApplicationParty,
    BusinessVesting,
    MaritalStatus,
    PartyRole,
)
from app.integrations.los.mock import MockLosClient
from app.integrations.los.schemas import LoanFileDTO

# Catalog values (Title Case, as Encompass would show them) -> our enums.
# Matched case-insensitively so a persona fixture can use either casing.
_MARITAL_STATUS_MAP: dict[str, MaritalStatus] = {
    "married": MaritalStatus.MARRIED,
    "unmarried": MaritalStatus.UNMARRIED,
    "separated": MaritalStatus.SEPARATED,
}
_BUSINESS_VESTING_MAP: dict[str, BusinessVesting] = {
    "title + lien in llc": BusinessVesting.TITLE_LIEN_IN_LLC,
    "personal name": BusinessVesting.PERSONAL_NAME,
}
_HOUSING_STATUS_MAP: dict[str, HousingStatus] = {
    "own": HousingStatus.OWN,
    "rent": HousingStatus.RENT,
    "living rent-free": HousingStatus.RENT_FREE,
    "rent_free": HousingStatus.RENT_FREE,
}


def _lookup(mapping: Mapping[str, object], raw: str | None, default: object) -> object:
    if raw is None:
        return default
    return mapping.get(raw.strip().lower(), default)


@dataclass
class ImportResult:
    """What `import_from_los` wrote -- CQ-011's `import_application` activity
    returns this unchanged (spec.md "Contracts")."""

    application_id: uuid.UUID
    parties_created: int
    housing_rows_created: int
    employment_rows_created: int
    liabilities_created: int
    assets_created: int


def _build_borrower_party(loan_file: LoanFileDTO) -> ApplicationParty:
    full_name = loan_file.borrower_full_name or ""
    first_name = loan_file.borrower_first_name or full_name.split(" ")[0] or "Unknown"
    last_name = loan_file.borrower_last_name or (
        " ".join(full_name.split(" ")[1:]) if " " in full_name else "Unknown"
    )
    return ApplicationParty(
        role=PartyRole.BORROWER,
        first_name=first_name,
        last_name=last_name,
        ssn_encrypted=loan_file.borrower_ssn,
        dob=loan_file.borrower_dob,
        marital_status=_lookup(_MARITAL_STATUS_MAP, loan_file.marital_status, None),  # type: ignore[arg-type]
        dependents_count=loan_file.dependents_count or 0,
        email=loan_file.borrower_email,
        cell_phone=loan_file.borrower_cell_phone,
        home_phone=loan_file.borrower_home_phone,
        work_phone=loan_file.borrower_work_phone,
        business_vesting=_lookup(_BUSINESS_VESTING_MAP, loan_file.business_vesting, None),  # type: ignore[arg-type]
        llc_entity_name=loan_file.llc_entity_name,
        no_co_applicant_check=bool(loan_file.no_co_applicant_check),
    )


def _build_co_borrower_party(loan_file: LoanFileDTO) -> ApplicationParty | None:
    if not loan_file.has_co_borrower:
        return None
    full_name = loan_file.co_borrower_full_name or ""
    parts = full_name.split(" ")
    first_name = parts[0] if parts and parts[0] else "Unknown"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else "Unknown"
    return ApplicationParty(
        role=PartyRole.CO_BORROWER,
        first_name=first_name,
        last_name=last_name,
        ssn_encrypted=loan_file.co_borrower_ssn,
        dob=loan_file.co_borrower_dob,
    )


def _build_housing_rows(loan_file: LoanFileDTO) -> list[HousingHistory]:
    rows: list[HousingHistory] = []
    if loan_file.current_street_address is not None:
        rows.append(
            HousingHistory(
                sequence=0,
                street_address=loan_file.current_street_address,
                city=loan_file.current_city or "",
                state=loan_file.current_state or "",
                zip=loan_file.current_zip or "",
                housing_status=_lookup(  # type: ignore[arg-type]
                    _HOUSING_STATUS_MAP, loan_file.current_housing_status, HousingStatus.RENT
                ),
                residence_years=loan_file.current_residence_years or 0,
                residence_months=loan_file.current_residence_months or 0,
                vom_completed=bool(loan_file.vom_completed),
            )
        )
    if loan_file.previous_street_address is not None:
        rows.append(
            HousingHistory(
                sequence=1,
                street_address=loan_file.previous_street_address,
                city="",
                state="",
                zip="",
                housing_status=HousingStatus.RENT,
                residence_years=loan_file.previous_residence_years or 0,
                residence_months=0,
            )
        )
    return rows


async def import_from_los(application_id: uuid.UUID, db: AsyncSession) -> ImportResult:
    """Fetches the application's loan file from `LosClient` (by
    `applications.los_loan_guid`) and writes `application_parties`,
    `housing_history`, `employment`, `liabilities` and `assets`. Flips
    `status` `intake -> verifying` on success. Commits once at the end.

    Raises whatever `MockLosClient.get_loan_file` raises (`LoanNotFoundError`,
    `ProviderUnavailableError`) if the LOS lookup fails -- CQ-011's workflow
    treats that as non-retryable-or-not per its own retry policy, not
    something this function decides.
    """
    application = await db.get(Application, application_id)
    if application is None:
        raise ValueError(f"No application with id {application_id}")
    if not application.los_loan_guid:
        raise ValueError(f"Application {application_id} has no los_loan_guid to import from")

    los_client = MockLosClient(db)
    loan_file = await los_client.get_loan_file(application.los_loan_guid)

    parties: list[ApplicationParty] = [_build_borrower_party(loan_file)]
    co_borrower = _build_co_borrower_party(loan_file)
    if co_borrower is not None:
        parties.append(co_borrower)
    for party in parties:
        party.application_id = application_id
        db.add(party)

    housing_rows = _build_housing_rows(loan_file)
    for row in housing_rows:
        row.application_id = application_id
        db.add(row)

    for emp in loan_file.employment:
        db.add(
            Employment(
                application_id=application_id,
                employer_name=emp.employer_name,
                monthly_income=emp.monthly_income,
                years_at_job=emp.years_at_job,
                self_employed=emp.self_employed,
            )
        )

    for liability in loan_file.liabilities:
        db.add(
            Liability(
                application_id=application_id,
                creditor_name=liability.creditor_name,
                account_type=liability.account_type,
                monthly_payment=liability.monthly_payment,
                balance=liability.balance,
            )
        )

    for asset in loan_file.assets:
        db.add(
            Asset(
                application_id=application_id,
                account_type=asset.account_type,
                institution=asset.institution,
                verified_amount=asset.verified_amount,
            )
        )

    application.status = ApplicationStatus.VERIFYING
    await db.flush()
    await db.commit()

    return ImportResult(
        application_id=application_id,
        parties_created=len(parties),
        housing_rows_created=len(housing_rows),
        employment_rows_created=len(loan_file.employment),
        liabilities_created=len(loan_file.liabilities),
        assets_created=len(loan_file.assets),
    )
