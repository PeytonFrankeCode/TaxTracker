"""Sales-tax economic nexus tracking.

After South Dakota v. Wayfair (2018), most states require remote sellers to
register and collect sales tax once their sales into the state cross an
"economic nexus" threshold — typically $100,000 in gross sales and/or 200
transactions per year. This module tracks your sales by destination state
and warns you when you're approaching or have crossed a threshold.

Thresholds change and have state-specific fine print (gross vs. retail vs.
taxable sales, measurement periods, marketplace rules). Treat the warnings
as a prompt to talk to a tax advisor, not as a registration decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Ledger

# Warn when sales reach this fraction of a state's threshold.
APPROACHING = 0.8

# (sales threshold $, transaction threshold or None, both_required)
# both_required=True means the state requires BOTH dollar and transaction
# thresholds to be met (CT, NY); otherwise crossing either one triggers nexus.
# None entry = the state has no statewide sales tax.
THRESHOLDS: dict[str, tuple[int, int | None, bool] | None] = {
    "AL": (250_000, None, False), "AK": (100_000, None, False),
    "AZ": (100_000, None, False), "AR": (100_000, 200, False),
    "CA": (500_000, None, False), "CO": (100_000, None, False),
    "CT": (100_000, 200, True),   "DE": None,
    "DC": (100_000, 200, False),  "FL": (100_000, None, False),
    "GA": (100_000, 200, False),  "HI": (100_000, 200, False),
    "ID": (100_000, None, False), "IL": (100_000, 200, False),
    "IN": (100_000, None, False), "IA": (100_000, None, False),
    "KS": (100_000, None, False), "KY": (100_000, 200, False),
    "LA": (100_000, None, False), "ME": (100_000, None, False),
    "MD": (100_000, 200, False),  "MA": (100_000, None, False),
    "MI": (100_000, 200, False),  "MN": (100_000, 200, False),
    "MS": (250_000, None, False), "MO": (100_000, None, False),
    "MT": None,                   "NE": (100_000, 200, False),
    "NV": (100_000, 200, False),  "NH": None,
    "NJ": (100_000, 200, False),  "NM": (100_000, None, False),
    "NY": (500_000, 100, True),   "NC": (100_000, None, False),
    "ND": (100_000, None, False), "OH": (100_000, 200, False),
    "OK": (100_000, None, False), "OR": None,
    "PA": (100_000, None, False), "RI": (100_000, 200, False),
    "SC": (100_000, None, False), "SD": (100_000, None, False),
    "TN": (100_000, None, False), "TX": (500_000, None, False),
    "UT": (100_000, 200, False),  "VT": (100_000, 200, False),
    "VA": (100_000, 200, False),  "WA": (100_000, None, False),
    "WV": (100_000, 200, False),  "WI": (100_000, None, False),
    "WY": (100_000, None, False),
}


@dataclass
class StateNexus:
    state: str
    sales: float
    transactions: int
    threshold_sales: int | None  # None = no statewide sales tax
    threshold_transactions: int | None
    both_required: bool
    progress: float  # 0.0–1.0+, fraction of the threshold reached
    status: str  # "no_sales_tax", "ok", "approaching", "reached"


def _progress(sales: float, txns: int, threshold) -> float:
    amount_limit, txn_limit, both = threshold
    fractions = [sales / amount_limit]
    if txn_limit:
        fractions.append(txns / txn_limit)
    # "either trips it" -> nearest limit governs; "both required" -> furthest.
    return min(fractions) if both else max(fractions)


def report(ledger: Ledger) -> list[StateNexus]:
    """Per-state nexus standing for every state you've sold into."""
    totals: dict[str, list] = {}
    for sale in ledger.sales:
        entry = totals.setdefault(sale.state, [0.0, 0])
        entry[0] += sale.amount
        entry[1] += sale.transactions

    results = []
    for state in sorted(totals):
        sales, txns = totals[state]
        threshold = THRESHOLDS.get(state)
        if threshold is None:
            status = "no_sales_tax" if state in THRESHOLDS else "ok"
            results.append(StateNexus(state, sales, txns, None, None, False,
                                      0.0, status))
            continue
        progress = _progress(sales, txns, threshold)
        if progress >= 1.0:
            status = "reached"
        elif progress >= APPROACHING:
            status = "approaching"
        else:
            status = "ok"
        results.append(StateNexus(state, sales, txns, threshold[0], threshold[1],
                                  threshold[2], progress, status))
    return results


def warnings(ledger: Ledger) -> list[str]:
    """Human-readable nexus warnings for approaching/reached states."""
    messages = []
    for nexus in report(ledger):
        if nexus.status == "approaching":
            messages.append(
                f"APPROACHING NEXUS in {nexus.state}: ${nexus.sales:,.0f} of "
                f"${nexus.threshold_sales:,} ({nexus.progress:.0%} of the "
                f"threshold). Consult a tax advisor before continuing to sell "
                f"into {nexus.state}."
            )
        elif nexus.status == "reached":
            messages.append(
                f"NEXUS THRESHOLD REACHED in {nexus.state}: ${nexus.sales:,.0f} "
                f"of ${nexus.threshold_sales:,}. You may be required to register "
                f"and collect sales tax there — consult a tax advisor now."
            )
    return messages
