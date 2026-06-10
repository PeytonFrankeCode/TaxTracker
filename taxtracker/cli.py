"""Command-line interface for TaxTracker."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import storage
from .deadlines import next_deadline, upcoming_deadlines
from .importer import parse_payout_csv
from .models import Expense, Income, INCOME_TYPES, Payment, FILING_STATUSES
from .tax import estimate


def money(value: float) -> str:
    return f"${value:,.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taxtracker",
        description="Track income, estimate federal taxes due, and stay on top of quarterly deadlines.",
    )
    parser.add_argument("--data", help="path to the data file (default: ~/.taxtracker/data.json)")
    parser.add_argument("--year", type=int, default=date.today().year, help="tax year (default: current year)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("income", help="record income")
    p.add_argument("amount", type=float)
    p.add_argument("--source", required=True, help='where it came from, e.g. "MySaaS" or "Acme Corp"')
    p.add_argument("--type", required=True, choices=sorted(INCOME_TYPES),
                   help="saas/freelance/business are subject to self-employment tax")
    p.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    p.add_argument("--note", default="")

    p = sub.add_parser("expense", help="record a deductible business expense")
    p.add_argument("amount", type=float)
    p.add_argument("--description", required=True)
    p.add_argument("--category", default="general")
    p.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")

    p = sub.add_parser("payment", help="record a tax payment (estimated payment or withholding)")
    p.add_argument("amount", type=float)
    p.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    p.add_argument("--kind", default="estimated", choices=["estimated", "withholding"])
    p.add_argument("--jurisdiction", default="federal")
    p.add_argument("--note", default="")

    p = sub.add_parser("status", help="estimated tax picture: liability, payments, balance due")
    p.add_argument("--filing-status", choices=sorted(FILING_STATUSES),
                   help="set/override filing status for this year")
    p.add_argument("--state", help='two-letter state code (e.g. CA) to include state tax')
    p.add_argument("--state-rate", type=float,
                   help="override the built-in flat state rate, e.g. 0.05 for 5%%")

    p = sub.add_parser("import-stripe", help="import income from a Stripe payout CSV export")
    p.add_argument("csv_file", help="path to the payouts CSV downloaded from Stripe")
    p.add_argument("--source", default="Stripe", help='income source label (default: "Stripe")')
    p.add_argument("--type", default="saas", choices=sorted(INCOME_TYPES),
                   help="income type for imported payouts (default: saas)")

    sub.add_parser("deadlines", help="upcoming quarterly estimated-payment deadlines")
    sub.add_parser("list", help="list all recorded income, expenses, and payments")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = storage.data_path(args.data)
    filing_status = getattr(args, "filing_status", None)
    ledger = storage.load(path, args.year, filing_status)

    if args.command == "income":
        income = Income(amount=args.amount, source=args.source, type=args.type,
                        date=args.date, note=args.note)
        ledger.incomes.append(income)
        storage.save(path, ledger)
        print(f"Recorded {money(income.amount)} {income.type} income from {income.source} on {income.date}.")

    elif args.command == "expense":
        expense = Expense(amount=args.amount, description=args.description,
                          category=args.category, date=args.date)
        ledger.expenses.append(expense)
        storage.save(path, ledger)
        print(f"Recorded {money(expense.amount)} expense: {expense.description} ({expense.date}).")

    elif args.command == "payment":
        payment = Payment(amount=args.amount, date=args.date, kind=args.kind,
                          jurisdiction=args.jurisdiction, note=args.note)
        ledger.payments.append(payment)
        storage.save(path, ledger)
        print(f"Recorded {money(payment.amount)} {payment.kind} payment ({payment.jurisdiction}) on {payment.date}.")

    elif args.command == "status":
        changed = bool(filing_status)
        if args.state is not None:
            ledger.state = args.state.upper()
            changed = True
        if args.state_rate is not None:
            ledger.state_rate = args.state_rate
            changed = True
        if changed:
            storage.save(path, ledger)
        print_status(ledger)

    elif args.command == "import-stripe":
        import_stripe(path, args)

    elif args.command == "deadlines":
        print_deadlines(args.year)

    elif args.command == "list":
        print_records(ledger)

    return 0


def import_stripe(path, args) -> None:
    rows, skipped = parse_payout_csv(args.csv_file)
    # Route each payout to the ledger for its own tax year.
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(int(row["date"][:4]), []).append(row)

    imported = 0
    duplicates = 0
    total = 0.0
    for year, year_rows in sorted(by_year.items()):
        ledger = storage.load(path, year)
        existing_ids = {i.note for i in ledger.incomes if i.note.startswith("stripe:")}
        for row in year_rows:
            note = f"stripe:{row['id']}" if row["id"] else ""
            if note and note in existing_ids:
                duplicates += 1
                continue
            ledger.incomes.append(Income(
                amount=row["amount"], source=args.source, type=args.type,
                date=row["date"], note=note,
            ))
            existing_ids.add(note)
            imported += 1
            total += row["amount"]
        storage.save(path, ledger)

    years = ", ".join(str(y) for y in sorted(by_year)) or "none"
    print(f"Imported {imported} payouts totaling {money(total)} (tax years: {years}).")
    if duplicates:
        print(f"Skipped {duplicates} already-imported payouts.")
    if skipped:
        print(f"Skipped {skipped} unpaid/zero-amount rows.")


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
    print(f"Quarterly estimated-payment deadlines for tax year {year}:")
    for quarter, due in upcoming_deadlines(year):
        days = (due - today).days
        print(f"  {quarter}  {due.isoformat()}  (in {days} days)")
    if not upcoming_deadlines(year):
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


if __name__ == "__main__":
    sys.exit(main())
