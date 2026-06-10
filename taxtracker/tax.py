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


def estimate(ledger: Ledger) -> dict:
    """Estimate the full-year federal tax picture from a ledger.

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

    total_tax = fed_income_tax + se_tax
    payments = sum(p.amount for p in ledger.payments)
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
        "total_tax": total_tax,
        "payments": payments,
        "balance_due": balance_due,
    }
