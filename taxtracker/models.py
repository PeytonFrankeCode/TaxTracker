"""Data models for TaxTracker records."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date

# Income types subject to self-employment tax.
SE_INCOME_TYPES = {"saas", "freelance", "business"}
# All recognized income types.
INCOME_TYPES = SE_INCOME_TYPES | {"w2", "other"}

FILING_STATUSES = {"single", "married"}

SALES_MODES = {"online", "in-person"}


@dataclass
class Sale:
    """A sale tracked for sales-tax economic-nexus purposes (separate from income)."""

    amount: float
    state: str  # two-letter destination state (where the buyer is)
    date: str  # ISO date YYYY-MM-DD
    transactions: int = 1
    note: str = ""

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("Sale amount must be positive")
        if self.transactions < 1:
            raise ValueError("Transactions must be at least 1")
        self.state = self.state.strip().upper()
        if len(self.state) != 2 or not self.state.isalpha():
            raise ValueError(f"State must be a two-letter code, got {self.state!r}")
        date.fromisoformat(self.date)

    def to_dict(self) -> dict:
        return asdict(self)


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
    state: str = ""  # two-letter code, e.g. "CA"; empty = no state tax estimated
    state_rate: float | None = None  # override the built-in flat rate (e.g. 0.05)
    sales_mode: str = "online"  # "online" or "in-person"; affects sale entry defaults
    incomes: list[Income] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    sales: list[Sale] = field(default_factory=list)

    def __post_init__(self):
        if self.filing_status not in FILING_STATUSES:
            raise ValueError(
                f"Unknown filing status {self.filing_status!r}; "
                f"expected one of {sorted(FILING_STATUSES)}"
            )
        if self.sales_mode not in SALES_MODES:
            raise ValueError(
                f"Unknown sales mode {self.sales_mode!r}; "
                f"expected one of {sorted(SALES_MODES)}"
            )

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "filing_status": self.filing_status,
            "state": self.state,
            "state_rate": self.state_rate,
            "sales_mode": self.sales_mode,
            "incomes": [i.to_dict() for i in self.incomes],
            "expenses": [e.to_dict() for e in self.expenses],
            "payments": [p.to_dict() for p in self.payments],
            "sales": [s.to_dict() for s in self.sales],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        return cls(
            year=data["year"],
            filing_status=data.get("filing_status", "single"),
            state=data.get("state", ""),
            state_rate=data.get("state_rate"),
            sales_mode=data.get("sales_mode", "online"),
            incomes=[Income(**i) for i in data.get("incomes", [])],
            expenses=[Expense(**e) for e in data.get("expenses", [])],
            payments=[Payment(**p) for p in data.get("payments", [])],
            sales=[Sale(**s) for s in data.get("sales", [])],
        )
