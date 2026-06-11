"""Command-line interface for TaxTracker."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import storage
from .display import (money, print_deadlines, print_explain, print_import_summary,
                      print_nexus, print_records, print_status)
from .importer import import_payouts
from .models import (Expense, Income, INCOME_TYPES, Payment, FILING_STATUSES,
                     PRODUCT_TYPES, Sale, SALES_MODES)


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

    p = sub.add_parser("sale", help="record a sale for sales-tax nexus tracking")
    p.add_argument("amount", type=float)
    p.add_argument("--to-state", help="buyer's two-letter state; defaults to your home "
                                      "state when sales mode is in-person")
    p.add_argument("--transactions", type=int, default=1,
                   help="number of transactions this entry represents (default 1)")
    p.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    p.add_argument("--note", default="")

    sub.add_parser("nexus", help="per-state sales totals vs economic nexus thresholds")

    sub.add_parser("explain", help="plain-English guide: what you owe and what to file")

    p = sub.add_parser("status", help="estimated tax picture: liability, payments, balance due")
    p.add_argument("--filing-status", choices=sorted(FILING_STATUSES),
                   help="set/override filing status for this year")
    p.add_argument("--state", help='two-letter state code (e.g. CA) to include state tax')
    p.add_argument("--state-rate", type=float,
                   help="override the built-in flat state rate, e.g. 0.05 for 5%%")
    p.add_argument("--mode", choices=sorted(SALES_MODES), dest="sales_mode",
                   help="how you sell: online (track buyer states) or in-person "
                        "(sales default to your home state); changeable any time")
    p.add_argument("--product", choices=sorted(t for t in PRODUCT_TYPES if t),
                   dest="product_type",
                   help="what you sell (drives sales-tax guidance in 'explain')")

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

    elif args.command == "sale":
        to_state = args.to_state
        if not to_state:
            if ledger.sales_mode == "in-person" and ledger.state:
                to_state = ledger.state
            else:
                print("Error: --to-state is required in online mode (or set your "
                      "home state and switch to in-person mode with "
                      "'status --mode in-person').", file=sys.stderr)
                return 1
        sale = Sale(amount=args.amount, state=to_state, date=args.date,
                    transactions=args.transactions, note=args.note)
        ledger.sales.append(sale)
        storage.save(path, ledger)
        print(f"Recorded {money(sale.amount)} sale to {sale.state} "
              f"({sale.transactions} txn) on {sale.date}.")
        from .nexus import warnings as nexus_warnings
        for alert in nexus_warnings(ledger):
            if f" {sale.state}" in alert:
                print(f"⚠ {alert}")

    elif args.command == "nexus":
        print_nexus(ledger)

    elif args.command == "explain":
        print_explain(ledger)

    elif args.command == "status":
        changed = bool(filing_status)
        if args.state is not None:
            ledger.state = args.state.upper()
            changed = True
        if args.state_rate is not None:
            ledger.state_rate = args.state_rate
            changed = True
        if args.sales_mode is not None:
            ledger.sales_mode = args.sales_mode
            changed = True
        if args.product_type is not None:
            ledger.product_type = args.product_type
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
