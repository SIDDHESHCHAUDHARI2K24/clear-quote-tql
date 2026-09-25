"""Per-tab validation rules (CQ-032 spec table; AC2)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from app.features.portal.apply.validation import (
    MSG_AGE,
    MSG_CHECKBOX,
    MSG_DOWN_PAYMENT,
    MSG_INCOME_PRIMARY,
    MSG_METRO_REQUIRED,
    MSG_METRO_UNKNOWN,
    MSG_NON_NEGATIVE,
    MSG_PRICE,
    MSG_PRIOR_ADDRESS,
    MSG_REQUIRED,
    MSG_SSN,
    MSG_TYPED_NAME,
    TabName,
    ValidationContext,
    context_for,
    first_incomplete_tab,
    validate_all,
    validate_tab,
)

Tabs = Callable[[], dict[str, dict[str, Any]]]
METROS = {"FL": frozenset({"Tampa", "Davenport"})}
TODAY = date(2026, 9, 25)


def _ctx(**kwargs: Any) -> ValidationContext:
    base: dict[str, Any] = {
        "occupancy": "str",
        "full_name": "Tina Tampa",
        "known_metros": METROS,
        "today": TODAY,
    }
    base.update(kwargs)
    return ValidationContext(**base)


def test_valid_tabs_pass(valid_tabs: Tabs) -> None:
    tabs = valid_tabs()
    for tab in TabName:
        model, errors = validate_tab(tab, tabs[tab.value], _ctx())
        assert errors == {}, (tab, errors)
        assert model is not None


def test_apply_tab_validation(valid_tabs: Tabs) -> None:
    """AC2: a primary applicant without income cannot pass tab 3; 14 months
    at the current address requires a prior address."""
    tabs = valid_tabs()

    income = tabs["income"]
    _, errors = validate_tab(TabName.INCOME, income, _ctx(occupancy="primary"))
    assert errors == {"monthly_income": MSG_INCOME_PRIMARY}

    # The same tab passes for an investor (income optional).
    _, errors = validate_tab(TabName.INCOME, income, _ctx(occupancy="str"))
    assert errors == {}

    you = tabs["you"] | {"residence_years": 1, "residence_months": 2}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"prior_address": MSG_PRIOR_ADDRESS}

    you["prior_address"] = {
        "street": "9 Old St",
        "city": "Orlando",
        "state": "FL",
        "zip": "32801",
        "residence_years": 2,
        "residence_months": 0,
    }
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {}


def test_primary_income_other_fields_required(valid_tabs: Tabs) -> None:
    income = valid_tabs()["income"] | {"monthly_income": "8000"}
    _, errors = validate_tab(TabName.INCOME, income, _ctx(occupancy="primary"))
    assert errors == {"employer_name": MSG_REQUIRED}


def test_age_must_be_18(valid_tabs: Tabs) -> None:
    you = valid_tabs()["you"] | {"dob": "2009-01-01"}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"dob": MSG_AGE}

    you["dob"] = "2008-09-25"  # 18 today
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {}


@pytest.mark.parametrize("ssn", ["12345678", "1234567890", "12345678a", ""])
def test_ssn_must_be_nine_digits(valid_tabs: Tabs, ssn: str) -> None:
    you = valid_tabs()["you"] | {"ssn": ssn}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"ssn": MSG_REQUIRED if ssn == "" else MSG_SSN}


def test_co_borrower_same_rules(valid_tabs: Tabs) -> None:
    you = valid_tabs()["you"] | {"has_co_borrower": True}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"co_borrower": MSG_REQUIRED}

    you["co_borrower"] = {
        "first_name": "Cody",
        "last_name": "Tampa",
        "cell_phone": "8135550100",
        "dob": "2010-01-01",
        "ssn": "98765432",
        "marital_status": "unmarried",
        "dependents_count": 0,
    }
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"co_borrower.dob": MSG_AGE, "co_borrower.ssn": MSG_SSN}


@pytest.mark.parametrize("price", ["0", "-5"])
def test_price_must_be_positive(valid_tabs: Tabs, price: str) -> None:
    prop = valid_tabs()["property"] | {"target_price": price}
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"target_price": MSG_PRICE}


def test_metro_required_without_address(valid_tabs: Tabs) -> None:
    prop = valid_tabs()["property"] | {"buy_box_metros": []}
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"buy_box_metros": MSG_METRO_REQUIRED}

    prop["buy_box_metros"] = ["Atlantis"]
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"buy_box_metros": MSG_METRO_UNKNOWN}

    # A metro outside the chosen states is not accepted either.
    prop = valid_tabs()["property"] | {"buy_box_states": ["TX"]}
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"buy_box_metros": MSG_METRO_UNKNOWN}


def test_address_replaces_metros(valid_tabs: Tabs) -> None:
    prop = valid_tabs()["property"] | {
        "has_property": True,
        "buy_box_metros": [],
        "address": {"street": "4412 W Gray St", "city": "Tampa", "state": "FL", "zip": "33609"},
    }
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {}

    prop["address"] = None
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"address": MSG_REQUIRED}


def test_down_payment_options_depend_on_occupancy(valid_tabs: Tabs) -> None:
    prop = valid_tabs()["property"] | {"down_payment_pct": "0.05"}
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {"down_payment_pct": MSG_DOWN_PAYMENT}

    prop["occupancy"] = "primary"
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert errors == {}


def test_numbers_must_be_non_negative(valid_tabs: Tabs) -> None:
    income = valid_tabs()["income"] | {"liquid_assets": "-1", "monthly_debts": "-2"}
    _, errors = validate_tab(TabName.INCOME, income, _ctx())
    assert errors == {"liquid_assets": MSG_NON_NEGATIVE, "monthly_debts": MSG_NON_NEGATIVE}

    you = valid_tabs()["you"] | {"dependents_count": -1}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {"dependents_count": MSG_NON_NEGATIVE}


def test_consent_boxes_and_typed_name(valid_tabs: Tabs) -> None:
    consent = valid_tabs()["consent"] | {"contact_consent": False, "typed_name": "Tina Tampah"}
    _, errors = validate_tab(TabName.CONSENT, consent, _ctx())
    assert errors == {"contact_consent": MSG_CHECKBOX, "typed_name": MSG_TYPED_NAME}

    # Case-insensitive, whitespace collapsed.
    consent = valid_tabs()["consent"] | {"typed_name": "  TINA   tampa "}
    _, errors = validate_tab(TabName.CONSENT, consent, _ctx())
    assert errors == {}


def test_empty_tab_reports_required_fields() -> None:
    _, errors = validate_tab(TabName.PROPERTY, {}, _ctx())
    assert errors["occupancy"] == MSG_REQUIRED
    assert errors["target_price"] == MSG_REQUIRED
    _, errors = validate_tab(TabName.YOU, {"first_name": "  "}, _ctx())
    assert errors["first_name"] == MSG_REQUIRED


def test_context_and_first_incomplete_tab(valid_tabs: Tabs) -> None:
    tabs = valid_tabs()
    context = context_for(tabs, METROS)
    assert context.full_name == "Tina Tampa"
    assert context.occupancy == "str"
    _, failures = validate_all(tabs, context)
    assert failures == {}
    assert first_incomplete_tab(failures) is TabName.CONSENT

    tabs["income"] = {}
    _, failures = validate_all(tabs, context_for(tabs, METROS))
    assert list(failures) == [TabName.INCOME]
    assert first_incomplete_tab(failures) is TabName.INCOME


def test_values_stay_inside_column_precision(valid_tabs: Tabs) -> None:
    """Review fix: a value the DB column cannot hold is a field error, not
    a 500 at submit."""
    income = valid_tabs()["income"] | {"years_employed": "1000", "monthly_debts": "150000000"}
    _, errors = validate_tab(TabName.INCOME, income, _ctx())
    assert set(errors) == {"years_employed", "monthly_debts"}

    you = valid_tabs()["you"] | {"dependents_count": 5000}
    _, errors = validate_tab(TabName.YOU, you, _ctx())
    assert set(errors) == {"dependents_count"}

    prop = valid_tabs()["property"] | {"target_price": "999999999999"}
    _, errors = validate_tab(TabName.PROPERTY, prop, _ctx())
    assert set(errors) == {"target_price"}


def test_unused_co_borrower_and_prior_address_are_ignored(valid_tabs: Tabs) -> None:
    """Review fix: a stale co-borrower block (box unticked) or a prior
    address no longer needed cannot fail tab 1."""
    you = valid_tabs()["you"] | {
        "has_co_borrower": False,
        "co_borrower": {"first_name": "Half"},
        "prior_address": {"street": "partial"},
    }
    model, errors = validate_tab(TabName.YOU, you, _ctx())
    assert errors == {}
    assert model is not None
