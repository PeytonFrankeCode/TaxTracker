"""Command-line interface for TaxTracker."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import storage
from .display import money, print_deadlines, print_import_summary, print_records, print_status
from .importer import import_payouts
from .models import Expense, Income, INCOME_TYPES, Payment, FILING_STATUSES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taxtracker",
        description="Track income, estimate federal taxes due, and stay on top of quarterly deadlines. "
                    "Run with no command for interactive mode.",
    )
    parser.add_argument("--data", help="path to the data file (default: ~/.taxtracker/data.json)")
    parser.add_argument("--year", type=int, default=date.today().year, help="tax year (default: current year)")
    sub = parser.add_subparsers(dest="command")

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

    if args.command is None:
        from .interactive import run
        return run(path, args.year)

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
        print_import_summary(import_payouts(path, args.csv_file,
                                            source=args.source, income_type=args.type))

    elif args.command == "deadlines":
        print_deadlines(args.year)

    elif args.command == "list":
        print_records(ledger)

    return 0


if __name__ == "__main__":
    sys.exit(main())
