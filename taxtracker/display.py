"""Shared output formatting for the CLI and interactive mode."""

from __future__ import annotations

from datetime import date

from .deadlines import next_deadline, upcoming_deadlines
from .tax import estimate


def money(value: float) -> str:
    return f"${value:,.2f}"


def print_status(ledger) -> None:
    est = estimate(ledger)
    print(f"Tax year {ledger.year} (filing status: {ledger.filing_status})")
    print("-" * 52)
    print(f"  Self-employment income   {money(est['se_gross']):>14}")
    print(f"  Business expenses        {money(est['business_expenses']):>14}")
    print(f"  Net SE profit            {money(est['se_profit']):>14}")
    print(f"  W-2 / other income       {money(est['other_income']):>14}")
    print(f"  Standard deduction       {money(est['standard_deduction']):>14}")
    print(f"  Taxable income           {money(est['taxable_income']):>14}")
    print("-" * 52)
    print(f"  Federal income tax       {money(est['income_tax']):>14}")
    print(f"  Self-employment tax      {money(est['se_tax']):>14}")
    if est["state"]:
        label = f"{est['state']} state tax ({est['state_rate'] * 100:.2f}%)"
        print(f"  {label:<24} {money(est['state_tax']):>14}")
    print(f"  Total estimated tax      {money(est['total_tax']):>14}")
    print(f"  Payments made            {money(est['payments']):>14}")
    if est["state"]:
        print(f"    federal               {money(est['federal_payments']):>14}")
        print(f"    state                 {money(est['state_payments']):>14}")
    label = "Balance due" if est["balance_due"] >= 0 else "Overpaid"
    print(f"  {label:<24} {money(abs(est['balance_due'])):>14}")
    if est["state"]:
        for name, balance in (("federal", est["federal_balance"]),
                              ("state", est["state_balance"])):
            suffix = "due" if balance >= 0 else "overpaid"
            print(f"    {name:<22} {money(abs(balance)):>14}  {suffix}")

    nd = next_deadline(ledger.year)
    if nd and est["balance_due"] > 0:
        quarter, due = nd
        remaining = len(upcoming_deadlines(ledger.year))
        suggested = est["balance_due"] / remaining
        print("-" * 52)
        print(f"  Next deadline: {quarter} estimated payment due {due.isoformat()}")
        print(f"  Suggested payment to spread the balance: {money(suggested)}")
    print()
    print("Estimates only (2025 federal rules; state tax is a flat-rate "
          "approximation; no credits or QBI).")


def print_deadlines(year: int) -> None:
    today = date.today()
    upcoming = upcoming_deadlines(year)
    print(f"Quarterly estimated-payment deadlines for tax year {year}:")
    for quarter, due in upcoming:
        days = (due - today).days
        print(f"  {quarter}  {due.isoformat()}  (in {days} days)")
    if not upcoming:
        print("  All deadlines for this tax year have passed.")


def print_records(ledger) -> None:
    print(f"Tax year {ledger.year}")
    print("Income:")
    for i in ledger.incomes:
        note = f" — {i.note}" if i.note else ""
        print(f"  {i.date}  {money(i.amount):>12}  {i.type:<10} {i.source}{note}")
    if not ledger.incomes:
        print("  (none)")
    print("Expenses:")
    for e in ledger.expenses:
        print(f"  {e.date}  {money(e.amount):>12}  {e.category:<10} {e.description}")
    if not ledger.expenses:
        print("  (none)")
    print("Payments:")
    for p in ledger.payments:
        note = f" — {p.note}" if p.note else ""
        print(f"  {p.date}  {money(p.amount):>12}  {p.kind:<12} {p.jurisdiction}{note}")
    if not ledger.payments:
        print("  (none)")


def print_import_summary(result: dict) -> None:
    years = ", ".join(str(y) for y in result["years"]) or "none"
    print(f"Imported {result['imported']} payouts totaling "
          f"{money(result['total'])} (tax years: {years}).")
    if result["duplicates"]:
        print(f"Skipped {result['duplicates']} already-imported payouts.")
    if result["skipped"]:
        print(f"Skipped {result['skipped']} unpaid/zero-amount rows.")
