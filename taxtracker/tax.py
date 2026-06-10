"""Federal tax estimation.

Uses 2025 federal brackets, standard deductions, and the Social Security wage
base as the basis for estimates. These are ESTIMATES for planning quarterly
payments, not a substitute for a tax professional or filing software: QBI
deductions, credits, state taxes, and many other factors are not modeled.
"""

from __future__ import annotations

from .models import Ledger, SE_INCOME_TYPES

# 2025 federal income tax brackets: (upper bound of bracket, marginal rate).
BRACKETS = {
    "single": [
        (11_925, 0.10),
        (48_475, 0.12),
        (103_350, 0.22),
        (197_300, 0.24),
        (250_525, 0.32),
        (626_350, 0.35),
        (float("inf"), 0.37),
    ],
    "married": [
        (23_850, 0.10),
        (96_950, 0.12),
        (206_700, 0.22),
        (394_600, 0.24),
        (501_050, 0.32),
        (751_600, 0.35),
        (float("inf"), 0.37),
    ],
}

STANDARD_DEDUCTION = {"single": 15_000, "married": 30_000}

# Self-employment tax constants (2025).
SE_NET_EARNINGS_FACTOR = 0.9235
SS_RATE = 0.124
MEDICARE_RATE = 0.029
SS_WAGE_BASE = 176_100

# Approximate flat state income tax rates (2025). For progressive states this
# is a rough effective marginal rate, not a bracket calculation — override
# with `status --state-rate` if you know your actual effective rate.
STATE_RATES = {
    "AL": 0.050, "AK": 0.0, "AZ": 0.025, "AR": 0.039, "CA": 0.093,
    "CO": 0.044, "CT": 0.055, "DE": 0.066, "DC": 0.085, "FL": 0.0,
    "GA": 0.0539, "HI": 0.0825, "ID": 0.05695, "IL": 0.0495, "IN": 0.030,
    "IA": 0.038, "KS": 0.0558, "KY": 0.040, "LA": 0.030, "ME": 0.0715,
    "MD": 0.0575, "MA": 0.050, "MI": 0.0425, "MN": 0.0785, "MS": 0.044,
    "MO": 0.047, "MT": 0.059, "NE": 0.052, "NV": 0.0, "NH": 0.0,
    "NJ": 0.0637, "NM": 0.059, "NY": 0.0685, "NC": 0.0425, "ND": 0.025,
    "OH": 0.035, "OK": 0.0475, "OR": 0.099, "PA": 0.0307, "RI": 0.0599,
    "SC": 0.062, "SD": 0.0, "TN": 0.0, "TX": 0.0, "UT": 0.0455,
    "VT": 0.076, "VA": 0.0575, "WA": 0.0, "WV": 0.0482, "WI": 0.0627,
    "WY": 0.0,
}


def income_tax(taxable_income: float, filing_status: str) -> float:
    """Progressive federal income tax on taxable income."""
    tax = 0.0
    lower = 0.0
    for upper, rate in BRACKETS[filing_status]:
        if taxable_income <= lower:
            break
        tax += (min(taxable_income, upper) - lower) * rate
        lower = upper
    return tax


def self_employment_tax(se_profit: float) -> float:
    """Self-employment tax (Social Security + Medicare) on net SE profit."""
    if se_profit <= 0:
        return 0.0
    net_earnings = se_profit * SE_NET_EARNINGS_FACTOR
    ss = min(net_earnings, SS_WAGE_BASE) * SS_RATE
    medicare = net_earnings * MEDICARE_RATE
    return ss + medicare


def state_rate_for(ledger: Ledger) -> float:
    """The flat state rate to apply: explicit override wins, else the table."""
    if ledger.state_rate is not None:
        return ledger.state_rate
    if not ledger.state:
        return 0.0
    code = ledger.state.upper()
    if code not in STATE_RATES:
        raise ValueError(f"Unknown state code {code!r}; set a rate with --state-rate")
    return STATE_RATES[code]


def estimate(ledger: Ledger) -> dict:
    """Estimate the full-year tax picture (federal + optional state) from a ledger.

    Returns a dict of intermediate figures plus the bottom line, so the CLI
    can show its work.
    """
    se_gross = sum(i.amount for i in ledger.incomes if i.type in SE_INCOME_TYPES)
    other_income = sum(i.amount for i in ledger.incomes if i.type not in SE_INCOME_TYPES)
    business_expenses = sum(e.amount for e in ledger.expenses)
    se_profit = max(0.0, se_gross - business_expenses)

    se_tax = self_employment_tax(se_profit)
    agi = se_profit + other_income - se_tax / 2  # half of SE tax is deductible
    taxable = max(0.0, agi - STANDARD_DEDUCTION[ledger.filing_status])
    fed_income_tax = income_tax(taxable, ledger.filing_status)

    state_rate = state_rate_for(ledger)
    st_tax = taxable * state_rate

    total_tax = fed_income_tax + se_tax + st_tax
    federal_payments = sum(
        p.amount for p in ledger.payments if p.jurisdiction == "federal"
    )
    state_payments = sum(
        p.amount for p in ledger.payments if p.jurisdiction != "federal"
    )
    payments = federal_payments + state_payments
    balance_due = total_tax - payments

    return {
        "se_gross": se_gross,
        "business_expenses": business_expenses,
        "se_profit": se_profit,
        "other_income": other_income,
        "agi": agi,
        "standard_deduction": STANDARD_DEDUCTION[ledger.filing_status],
        "taxable_income": taxable,
        "income_tax": fed_income_tax,
        "se_tax": se_tax,
        "state": ledger.state.upper() if ledger.state else "",
        "state_rate": state_rate,
        "state_tax": st_tax,
        "federal_tax": fed_income_tax + se_tax,
        "total_tax": total_tax,
        "federal_payments": federal_payments,
        "state_payments": state_payments,
        "payments": payments,
        "federal_balance": fed_income_tax + se_tax - federal_payments,
        "state_balance": st_tax - state_payments,
        "balance_due": balance_due,
    }
