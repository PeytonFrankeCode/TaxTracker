"""Data models for TaxTracker records."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date

# Income types subject to self-employment tax.
SE_INCOME_TYPES = {"saas", "freelance", "business"}
# All recognized income types.
INCOME_TYPES = SE_INCOME_TYPES | {"w2", "other"}

FILING_STATUSES = {"single", "married"}


@dataclass
class Income:
    amount: float
    source: str
    type: str  # one of INCOME_TYPES
    date: str  # ISO date YYYY-MM-DD
    note: str = ""

    def __post_init__(self):
        if self.type not in INCOME_TYPES:
            raise ValueError(
                f"Unknown income type {self.type!r}; expected one of {sorted(INCOME_TYPES)}"
            )
        if self.amount <= 0:
            raise ValueError("Income amount must be positive")
        date.fromisoformat(self.date)  # validates format

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Expense:
    amount: float
    description: str
    date: str  # ISO date YYYY-MM-DD
    category: str = "general"

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("Expense amount must be positive")
        date.fromisoformat(self.date)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Payment:
    """A tax payment already made (estimated payment or W-2 withholding)."""

    amount: float
    date: str  # ISO date YYYY-MM-DD
    jurisdiction: str = "federal"
    kind: str = "estimated"  # "estimated" or "withholding"
    note: str = ""

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("Payment amount must be positive")
        date.fromisoformat(self.date)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ledger:
    """All records for one tax year."""

    year: int
    filing_status: str = "single"
    incomes: list[Income] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)

    def __post_init__(self):
        if self.filing_status not in FILING_STATUSES:
            raise ValueError(
                f"Unknown filing status {self.filing_status!r}; "
                f"expected one of {sorted(FILING_STATUSES)}"
            )

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "filing_status": self.filing_status,
            "incomes": [i.to_dict() for i in self.incomes],
            "expenses": [e.to_dict() for e in self.expenses],
            "payments": [p.to_dict() for p in self.payments],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        return cls(
            year=data["year"],
            filing_status=data.get("filing_status", "single"),
            incomes=[Income(**i) for i in data.get("incomes", [])],
            expenses=[Expense(**e) for e in data.get("expenses", [])],
            payments=[Payment(**p) for p in data.get("payments", [])],
        )
