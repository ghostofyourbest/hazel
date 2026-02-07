"""
test.py

Unit tests for eirmodelling.py using pytest. Tests include:
- correctness of EIR extraction for amortizing and bullet loans (EIR should match contract rate)
- behavior on invalid cashflows
- carrying value adjustment computation per IFRS principle (PV of revised cash flows discounted at original EIR)
- an illustrative test based on the IFRS 9 principle: initial carrying amount (after fees) equals PV of contractual cash flows discounted at the EIR

Run with: pytest -q
"""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import numpy as np
import pytest

from eirmodelling import (
    generate_test_schedule,
    calculate_eir_for_loan,
    compute_carrying_value_adjustments,
    compute_pv_of_cashflows,
    xirr,
)

def test_amortizing_schedule_eir_matches_contract_rate():
    # Level annuity amortizing loan: EIR should equal the contract coupon when schedule generated
    principal = 100_000.0
    annual_rate = 0.05
    start = "2026-01-01"
    term = 5
    schedule = generate_test_schedule(principal, annual_rate, start, term_years=term, payments_per_year=1, amortizing=True)

    computed_eir = calculate_eir_for_loan(schedule)
    assert computed_eir == pytest.approx(annual_rate, rel=1e-6)

def test_bullet_schedule_eir_matches_contract_rate():
    # Bullet loan (interest only, principal repaid at maturity) should have EIR equal to coupon
    principal = 10_000.0
    annual_rate = 0.06
    start = "2026-01-01"
    term = 3
    schedule = generate_test_schedule(principal, annual_rate, start, term_years=term, payments_per_year=1, amortizing=False)

    computed_eir = calculate_eir_for_loan(schedule)
    assert computed_eir == pytest.approx(annual_rate, rel=1e-8)

def test_xirr_requires_mixed_signs():
    # Cashflows with only positive values are invalid for IRR
    s = pd.Series([100, 50, 50], index=pd.to_datetime(["2026-01-01", "2027-01-01", "2028-01-01"]))
    with pytest.raises(ValueError):
        xirr(s)

def test_compute_carrying_value_adjustment_matches_manual_pvs():
    # Original: amortizing loan
    principal = 1000.0
    rate = 0.05
    start = "2026-01-01"
    term = 5
    orig = generate_test_schedule(principal, rate, start, term_years=term, payments_per_year=1, amortizing=True)

    # Reforecast at end of year 1: assume bank expects remaining receipts to be 95% of original
    reforecast_date = pd.Timestamp("2027-01-01")
    remaining_orig = orig[orig.index >= reforecast_date]
    reforecast = remaining_orig * 0.95

    df = compute_carrying_value_adjustments(orig, {reforecast_date: reforecast}, eir=None)
    # manual PVs
    eir = calculate_eir_for_loan(orig)
    pv_orig_manual = compute_pv_of_cashflows(remaining_orig, eir, reforecast_date)
    pv_rf_manual = compute_pv_of_cashflows(reforecast, eir, reforecast_date)
    assert df.loc[reforecast_date, "pv_original"] == pytest.approx(pv_orig_manual, rel=1e-12)
    assert df.loc[reforecast_date, "pv_reforecast"] == pytest.approx(pv_rf_manual, rel=1e-12)
    assert df.loc[reforecast_date, "adjustment"] == pytest.approx(pv_rf_manual - pv_orig_manual, rel=1e-12)

def test_ifrs_principle_example_initial_carrying_equals_discounted_contractual_cashflows():
    # This test is an illustration of the IFRS 9 principle: the original carrying amount (i.e., proceeds
    # received) equals the present value of contractual cash flows discounted at the EIR that equates
    # those cash flows to the proceeds. We model a loan where the entity receives net proceeds after fees.

    # Contractual contractual receipts: borrower will pay 400 each year for 3 years (total 1200)
    # Entity receives net proceeds (after origination fee) of 950 at initial date
    start = pd.Timestamp("2026-01-01")
    proceeds = 950.0
    # Build cashflow series: initial cashflow is the proceeds outflow (-proceeds) from entity perspective,
    # and subsequent receipts are positive
    cf_dates = [start, start + pd.DateOffset(years=1), start + pd.DateOffset(years=2), start + pd.DateOffset(years=3)]
    cfs = pd.Series(data=[-proceeds, 400.0, 400.0, 400.0], index=cf_dates)

    # EIR should be the rate that discounts future receipts to -initial carrying amount
    e = calculate_eir_for_loan(cfs)
    # Discount cashflows at e to the start date -- the NPV should be approximately zero
    npv = compute_pv_of_cashflows(cfs, e, start)
    assert np.isclose(npv, 0.0, atol=1e-8)

    # Additionally, the PV of the future contractual receipts (excluding initial proceeds) discounted
    # at the EIR should equal the proceeds (initial carrying amount)
    future_receipts = cfs[cfs.index > start]
    pv_receipts = compute_pv_of_cashflows(future_receipts, e, start)
    assert pv_receipts == pytest.approx(proceeds, rel=1e-10)


if __name__ == "__main__":
    # Execute tests when run directly
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))