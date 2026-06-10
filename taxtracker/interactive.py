"""Interactive menu mode: run `python -m taxtracker` with no command."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import storage
from .display import (money, print_deadlines, print_import_summary, print_nexus,
                      print_records, print_status)
from .importer import ImportError_, import_payouts
from .models import (Expense, FILING_STATUSES, Income, INCOME_TYPES, Payment,
                     Sale, SALES_MODES)
from .nexus import THRESHOLDS, warnings as nexus_warnings
from .tax import STATE_RATES

MENU = """
 1) Add income
 2) Add expense
 3) Record a tax payment
 4) Record a sale (for state nexus tracking)
 5) Import Stripe payouts (CSV)
 6) Show status (what you owe)
 7) Nexus report (state sales-tax thresholds)
 8) Show quarterly deadlines
 9) List everything recorded
 s) Settings (year / filing status / state / sales mode)
 q) Quit
"""


def ask(label: str, default: str | None = None) -> str:
    """Prompt until non-empty, unless a default is supplied."""
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  This one's required.")


def ask_amount(label: str) -> float:
    while True:
        raw = ask(label).replace("$", "").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            print("  Enter a number, e.g. 1250 or 1250.50")
            continue
        if value <= 0:
            print("  Must be greater than zero.")
            continue
        return value


def ask_date(label: str = "Date (YYYY-MM-DD)") -> str:
    while True:
        raw = ask(label, default=date.today().isoformat())
        try:
            date.fromisoformat(raw)
            return raw
        except ValueError:
            print("  Use YYYY-MM-DD, e.g. 2026-06-15")


def ask_choice(label: str, choices: list[str], default: str) -> str:
    while True:
        value = ask(f"{label} ({'/'.join(choices)})", default=default).lower()
        if value in choices:
            return value
        print(f"  Pick one of: {', '.join(choices)}")


def add_income(ledger) -> bool:
    print("\nIncome types: saas/freelance/business pay self-employment tax; w2/other don't.")
    income = Income(
        amount=ask_amount("Amount"),
        source=ask("Source (e.g. MySaaS, Acme Corp)"),
        type=ask_choice("Type", sorted(INCOME_TYPES), default="saas"),
        date=ask_date(),
        note=ask("Note (optional)", default=""),
    )
    ledger.incomes.append(income)
    print(f"Recorded {money(income.amount)} {income.type} income from {income.source}.")
    return True


def add_expense(ledger) -> bool:
    expense = Expense(
        amount=ask_amount("Amount"),
        description=ask("Description (e.g. AWS hosting)"),
        category=ask("Category", default="general"),
        date=ask_date(),
    )
    ledger.expenses.append(expense)
    print(f"Recorded {money(expense.amount)} expense: {expense.description}.")
    return True


def add_payment(ledger) -> bool:
    payment = Payment(
        amount=ask_amount("Amount"),
        kind=ask_choice("Kind", ["estimated", "withholding"], default="estimated"),
        jurisdiction=ask_choice("Jurisdiction", ["federal", "state"], default="federal"),
        date=ask_date("Date paid (YYYY-MM-DD)"),
        note=ask("Note (optional)", default=""),
    )
    ledger.payments.append(payment)
    print(f"Recorded {money(payment.amount)} {payment.kind} payment ({payment.jurisdiction}).")
    return True


def add_sale(ledger) -> bool:
    print(f"\nSales mode is '{ledger.sales_mode}' (changeable in Settings).")
    default_state = ledger.state if (ledger.sales_mode == "in-person" and ledger.state) else None
    while True:
        code = ask("Buyer's state (two-letter code)", default=default_state).upper()
        if code in THRESHOLDS:
            break
        print("  Use a two-letter US state code, e.g. TX or CA.")
    raw_txns = ask("Number of transactions in this entry", default="1")
    sale = Sale(
        amount=ask_amount("Total amount"),
        state=code,
        transactions=int(raw_txns) if raw_txns.isdigit() and int(raw_txns) > 0 else 1,
        date=ask_date(),
        note=ask("Note (optional)", default=""),
    )
    ledger.sales.append(sale)
    print(f"Recorded {money(sale.amount)} sale to {sale.state}.")
    for alert in nexus_warnings(ledger):
        if f" {sale.state}" in alert:
            print(f"⚠ {alert}")
    return True


def import_stripe(data_path: Path) -> None:
    csv_file = ask("Path to the Stripe payouts CSV")
    if not Path(csv_file).expanduser().exists():
        print(f"  Can't find {csv_file}")
        return
    try:
        result = import_payouts(data_path, Path(csv_file).expanduser())
    except ImportError_ as exc:
        print(f"  {exc}")
        return
    print_import_summary(result)


def settings(data_path: Path, ledger):
    """Edit per-year settings; returns the (possibly different) active ledger."""
    state = ledger.state or "none"
    print(f"\nCurrent: tax year {ledger.year}, filing status {ledger.filing_status}, "
          f"state {state}, sales mode {ledger.sales_mode}")
    print(" 1) Filing status   2) State   3) Custom state rate   4) Switch tax year")
    print(" 5) Sales mode (online / in-person)")
    choice = ask("Setting to change", default="1")
    if choice == "1":
        ledger.filing_status = ask_choice("Filing status", sorted(FILING_STATUSES),
                                          default=ledger.filing_status)
    elif choice == "2":
        while True:
            code = ask("Two-letter state code (or 'none' to clear)",
                       default=ledger.state or "none").upper()
            if code == "NONE":
                ledger.state = ""
                break
            if code in STATE_RATES:
                ledger.state = code
                break
            print(f"  Unknown state {code!r}.")
    elif choice == "3":
        while True:
            raw = ask("State rate as a decimal (e.g. 0.05 for 5%, or 'none' to clear)")
            if raw.lower() == "none":
                ledger.state_rate = None
                break
            try:
                ledger.state_rate = float(raw)
                break
            except ValueError:
                print("  Enter a decimal like 0.05")
    elif choice == "4":
        storage.save(data_path, ledger)
        while True:
            raw = ask("Tax year", default=str(ledger.year))
            if raw.isdigit() and len(raw) == 4:
                return storage.load(data_path, int(raw))
            print("  Enter a four-digit year, e.g. 2026")
    elif choice == "5":
        print("  online: you sell remotely; each sale records the buyer's state.")
        print("  in-person: sales default to your home state.")
        ledger.sales_mode = ask_choice("Sales mode", sorted(SALES_MODES),
                                       default=ledger.sales_mode)
    storage.save(data_path, ledger)
    return ledger


def run(data_path: Path, year: int) -> int:
    ledger = storage.load(data_path, year)
    print("TaxTracker — interactive mode (data file: "
          f"{data_path})")
    try:
        while True:
            state = f", state {ledger.state}" if ledger.state else ""
            print(f"\nTax year {ledger.year} ({ledger.filing_status}{state})")
            print(MENU)
            choice = ask("What would you like to do?", default="6").lower()
            if choice in ("q", "quit", "exit"):
                print("Bye — your data is saved.")
                return 0
            elif choice == "1":
                if add_income(ledger):
                    storage.save(data_path, ledger)
            elif choice == "2":
                if add_expense(ledger):
                    storage.save(data_path, ledger)
            elif choice == "3":
                if add_payment(ledger):
                    storage.save(data_path, ledger)
            elif choice == "4":
                if add_sale(ledger):
                    storage.save(data_path, ledger)
            elif choice == "5":
                import_stripe(data_path)
                ledger = storage.load(data_path, ledger.year)
            elif choice == "6":
                print()
                print_status(ledger)
            elif choice == "7":
                print()
                print_nexus(ledger)
            elif choice == "8":
                print()
                print_deadlines(ledger.year)
            elif choice == "9":
                print()
                print_records(ledger)
            elif choice == "s":
                ledger = settings(data_path, ledger)
            else:
                print("  Pick an option from the menu, or q to quit.")
    except (KeyboardInterrupt, EOFError):
        print("\nBye — your data is saved.")
        return 0
