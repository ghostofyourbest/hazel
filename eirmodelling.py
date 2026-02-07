"""
eirmodelling.py

Functions to calculate Effective Interest Rate (EIR) and to compute carrying value adjustments
for reforecasted cash flows under IFRS principles (present value of future cash flows discounted
at the original EIR).

This file provides:

- xirr(cashflows: pd.Series) -> float
  Robust XIRR implementation (annual EIR, actual/365 daycount) for irregular dated cash flows.

- calculate_eir_for_loan(cashflows: pd.Series) -> float
  Determine the original EIR for a single loan given a pandas Series indexed by dates.

- calculate_eir_for_loans(loans: list[pd.Series]) -> pd.Series
  Batch EIR calculator for a list of loan cashflow series.

- compute_pv_of_cashflows(cashflows: pd.Series, discount_rate: float, base_date: pd.Timestamp)
  Helper to compute PV (discounting to base_date) using annual compounding with actual/365.

- compute_carrying_value_adjustments(original: pd.Series, reforecasts: dict[pd.Timestamp, pd.Series],
  eir: float | None = None) -> pd.DataFrame
  For each reforecast date provided, discount the remaining original cash flows and the
  reforecasted cash flows at the original EIR (if not provided, it is calculated from the
  original schedule) and return the PVs and adjustment (PV_reforecast - PV_original). This
  follows IFRS principle: when expected future cash flows change, carrying amount is adjusted
  to the present value of the revised cash flows discounted at the original EIR.

- generate_test_schedule(...) -> pd.Series
  Helper to generate deterministic schedules for testing: bullet maturity or fully amortizing
  fixed-rate loan with annual payments (or custom payments_per_year).

Notes / IFRS assumptions:
- Day count convention: Actual/365 (sufficient for whole-year tenors but handles irregular dates).
- Discounting uses annual compounding: cashflow_t / (1 + EIR)^(days_t / 365).
- The initial carrying amount used for EIR derivation is assumed to be the negative of the first
  cash flow in the provided series (i.e. disbursement). If fees/other adjustments exist, the
  initial carrying amount should be reflected in the provided cash flow series.

"""

from __future__ import annotations

from typing import List, Dict, Optional
import datetime as dt

import pandas as pd
import numpy as np

def _ensure_series_index_datetime(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        try:
            series = series.copy()
            series.index = pd.to_datetime(series.index)
        except Exception as e:
            raise ValueError("Cashflow series index must be datetime-like") from e
    return series.sort_index()

def compute_pv_of_cashflows(cashflows: pd.Series, discount_rate: float, base_date: pd.Timestamp) -> float:
    """
    Compute present value of a series of dated cash flows discounted to base_date using
    annual compounding and Actual/365 daycount.

    Parameters:
    - cashflows: pd.Series indexed by date (datetime-like). Values are cash amounts (positive receipts).
    - discount_rate: annual discount rate as decimal (e.g. 0.05 for 5%).
    - base_date: date to discount to (pd.Timestamp or convertible).

    Returns:
    - float: present value (same sign convention as cashflows)
    """
    if cashflows.empty:
        return 0.0
    series = _ensure_series_index_datetime(cashflows)
    base = pd.to_datetime(base_date)
    # Only consider cashflows at or after base_date
    remaining = series[series.index >= base]
    if remaining.empty:
        return 0.0
    days = (remaining.index.to_series() - base).dt.days.values.astype(float)
    # discount factor (1 + r)^(days/365)
    df = (1.0 + discount_rate) ** (days / 365.0)
    pv = (remaining.values.astype(float) / df).sum()
    return float(pv)

def xirr(cashflows: pd.Series, guess: float = 0.05, tol: float = 1e-8, max_iter: int = 200) -> float:
    """
    Compute the annual effective internal rate of return for irregular dated cash flows.

    Solves for r in: sum( cf_t / (1 + r)^(days_t/365) ) = 0

    Uses a robust bisection approach with expanding bounds; falls back to Newton if desired.

    Parameters:
    - cashflows: pd.Series indexed by date (datetime-like). Values are cash amounts. The series
      must contain at least one positive and one negative cashflow.
    - guess: initial guess (not required for bisection but kept for API compatibility)

    Returns:
    - annual EIR as decimal
    """
    series = _ensure_series_index_datetime(cashflows)
    if series.empty:
        raise ValueError("Cashflows series is empty")
    vals = series.values.astype(float)
    if not (np.any(vals > 0) and np.any(vals < 0)):
        raise ValueError("Cashflows must contain at least one positive and one negative value to compute an IRR")
    base = series.index[0]

    def npv(rate: float) -> float:
        # protect against rate <= -1
        if rate <= -0.9999999999:
            return np.inf
        days = (series.index.to_series() - base).dt.days.values.astype(float)
        df = (1.0 + rate) ** (days / 365.0)
        return float((vals / df).sum())

    # Bracket search
    lower = -0.9999
    upper = 10.0
    f_low = npv(lower)
    f_high = npv(upper)
    # Expand upper bound if necessary
    expansions = 0
    while f_low * f_high > 0 and expansions < 50:
        upper *= 2.0
        f_high = npv(upper)
        expansions += 1
        if upper > 1e6:
            break
    if f_low * f_high > 0:
        # As a fallback, try Newton-Raphson from guess
        rate = guess
        for i in range(max_iter):
            # compute derivative numerically
            f = npv(rate)
            h = 1e-6 if abs(rate) < 1 else abs(rate) * 1e-6
            f1 = npv(rate + h)
            df_dr = (f1 - f) / h
            if df_dr == 0:
                break
            new_rate = rate - f / df_dr
            if abs(new_rate - rate) < tol:
                return float(new_rate)
            rate = new_rate
        raise RuntimeError("Unable to bracket or converge when solving XIRR")

    # Bisection
    a, b = lower, upper
    fa, fb = f_low, f_high
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        fm = npv(m)
        if abs(fm) < tol:
            return float(m)
        # choose side
        if fa * fm <= 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    # final estimate
    return float(0.5 * (a + b))

def calculate_eir_for_loan(cashflows: pd.Series) -> float:
    """
    Calculate original EIR for a single loan cashflow series.

    Assumes the provided series contains the full contractual cash flows (including disbursement
    as the first, typically negative, cashflow). The returned EIR is an annual effective rate
    (decimal) using actual/365 daycount.
    """
    return xirr(cashflows)

def calculate_eir_for_loans(loans: List[pd.Series]) -> pd.Series:
    """
    Calculate EIR for a list of cashflow series. Returns a pandas Series indexed by integer
    loan position with the computed EIR values.
    """
    results = []
    for i, s in enumerate(loans):
        e = calculate_eir_for_loan(s)
        results.append(e)
    return pd.Series(results, index=list(range(len(loans))), name="eir")

def compute_carrying_value_adjustments(
    original: pd.Series,
    reforecasts: Dict[dt.date, pd.Series],
    eir: Optional[float] = None,
) -> pd.DataFrame:
    """
    For an original schedule and a set of reforecasted remaining schedules at specified
    reforecast dates (typically month-ends), compute the present value (discounted at the
    original EIR) of the remaining original cash flows and the reforecasted cash flows, and
    return the carrying value adjustment required under IFRS (PV_reforecast - PV_original).

    Parameters:
    - original: full original contractual cashflow series (pd.Series indexed by dates). The
      series should include the original disbursement and the full contractual receipts.
    - reforecasts: mapping from reforecast_date (datetime/date) to a pd.Series of reforecasted
      future cashflows (these reforecast series should be dated with absolute dates representing
      the expected timing of future receipts).
    - eir: optional pre-computed original EIR; if None the function will compute it from the
      original series.

    Returns:
    - pd.DataFrame with columns ['reforecast_date','pv_original','pv_reforecast','adjustment']
      where adjustment = pv_reforecast - pv_original.

    IFRS note:
    - The present values are computed by discounting the remaining cash flows to the reforecast
      date at the original effective interest rate. The difference represents the carrying value
      adjustment required under IAS/IFRS when cash flow estimates change.
    """
    orig = _ensure_series_index_datetime(original)
    if eir is None:
        eir = calculate_eir_for_loan(orig)
    rows = []
    for rd, rf_series in sorted(reforecasts.items()):
        rd_ts = pd.to_datetime(rd)
        # remaining original cashflows at or after reforecast date
        remaining_orig = orig[orig.index >= rd_ts]
        pv_orig = compute_pv_of_cashflows(remaining_orig, eir, rd_ts)
        rf = _ensure_series_index_datetime(rf_series)
        # ensure reforecast cashflows are dated at or after the reforecast date
        rf_remaining = rf[rf.index >= rd_ts]
        pv_rf = compute_pv_of_cashflows(rf_remaining, eir, rd_ts)
        adjustment = pv_rf - pv_orig
        rows.append({
            "reforecast_date": rd_ts,
            "pv_original": pv_orig,
            "pv_reforecast": pv_rf,
            "adjustment": adjustment,
        })
    df = pd.DataFrame(rows).set_index("reforecast_date")
    return df

def generate_test_schedule(
    principal: float,
    annual_rate: float,
    start_date: dt.date | str,
    term_years: int,
    payments_per_year: int = 1,
    amortizing: bool = True,
) -> pd.Series:
    """
    Generate a deterministic loan cashflow schedule for testing purposes.

    Parameters:
    - principal: positive amount disbursed at start_date (function will emit a negative cashflow at start)
    - annual_rate: coupon / contract rate used to compute payments (decimal, e.g. 0.05)
    - start_date: start/disbursement date (string or date)
    - term_years: integer number of whole years for the contract (1..n)
    - payments_per_year: payments per year (1 for annual, 12 for monthly etc.). IFRS task uses annual.
    - amortizing: if True a level-annuity amortizing loan is generated. If False, generate interest-only
      payments each period and repay principal at maturity (bullet).

    Returns:
    - pd.Series indexed by pd.Timestamp with the cashflow amounts. The first entry is the disbursement
      (negative), subsequent entries are receipts (positive).
    """
    start = pd.to_datetime(start_date)
    total_periods = term_years * payments_per_year
    dates = [start + pd.DateOffset(months=int(round(12 * i / payments_per_year))) for i in range(0, total_periods + 1)]
    # first date is disbursement
    cashflows = []
    # disbursement at t=0
    cashflows.append(-abs(float(principal)))
    if total_periods == 0:
        return pd.Series(cashflows, index=[dates[0]])

    if amortizing:
        # compute level payment per period
        r_period = (1 + annual_rate) ** (1 / payments_per_year) - 1
        if r_period == 0:
            payment = principal / total_periods
        else:
            payment = principal * r_period / (1 - (1 + r_period) ** (-total_periods))
        bal = principal
        for p in range(1, total_periods + 1):
            interest = bal * r_period
            principal_repay = payment - interest
            # guard rounding on last payment
            if p == total_periods:
                principal_repay = bal
                payment = interest + principal_repay
            bal = bal - principal_repay
            cashflows.append(payment)
    else:
        # interest-only: periodic interest payments then principal at maturity
        r_period = (1 + annual_rate) ** (1 / payments_per_year) - 1
        interest_payment = principal * r_period
        for p in range(1, total_periods + 1):
            if p == total_periods:
                cashflows.append(interest_payment + principal)
            else:
                cashflows.append(interest_payment)

    # Build series with dates from 0 (start) and then the payment dates
    idx = [pd.Timestamp(dates[0])] + [pd.Timestamp(d) for d in dates[1:]]
    return pd.Series(data=np.array(cashflows, dtype=float), index=idx)

if __name__ == "__main__":
    # Quick demonstration when run as script
    print("eirmodelling.py demo")
    s = generate_test_schedule(100000.0, 0.05, "2026-01-01", term_years=5, payments_per_year=1, amortizing=True)
    print("Schedule:\n", s)
    e = calculate_eir_for_loan(s)
    print(f"Calculated EIR: {e:.6%}")

    # create a simple reforecast: suppose after 1 year we expect a slightly higher rate and thus
    # slightly different receipts (e.g. bank reduces principal repayments by 10% of remaining)
    reforecast_date = pd.Timestamp("2027-01-01")
    # create a naive reforecast where remaining payments are reduced by 5%
    remaining = s[s.index >= reforecast_date]
    reforecast = remaining * 0.95
    adjustments = compute_carrying_value_adjustments(s, {reforecast_date: reforecast}, eir=None)
    print("Adjustments:\n", adjustments)