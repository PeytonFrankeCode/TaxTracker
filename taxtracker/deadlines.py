"""IRS quarterly estimated-tax deadlines."""

from __future__ import annotations

from datetime import date


def quarterly_deadlines(tax_year: int) -> list[tuple[str, date]]:
    """The four estimated-payment deadlines for a tax year.

    Note Q4 falls in January of the following year. Actual IRS dates shift
    when the 15th lands on a weekend or holiday; these are the nominal dates.
    """
    return [
        ("Q1", date(tax_year, 4, 15)),
        ("Q2", date(tax_year, 6, 15)),
        ("Q3", date(tax_year, 9, 15)),
        ("Q4", date(tax_year + 1, 1, 15)),
    ]


def upcoming_deadlines(tax_year: int, today: date | None = None) -> list[tuple[str, date]]:
    """Deadlines for the tax year that haven't passed yet."""
    today = today or date.today()
    return [(q, d) for q, d in quarterly_deadlines(tax_year) if d >= today]


def next_deadline(tax_year: int, today: date | None = None) -> tuple[str, date] | None:
    """The next upcoming deadline, or None if all have passed."""
    upcoming = upcoming_deadlines(tax_year, today)
    return upcoming[0] if upcoming else None
