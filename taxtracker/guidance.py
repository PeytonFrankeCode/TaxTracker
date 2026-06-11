"""Personalized plain-English guidance: what you'll owe and what to file.

Built from the user's setup answers (home state, product type, sales mode,
filing status) and their recorded numbers. Everything here is general
guidance for a sole proprietor / single-member LLC — not advice. Taxability
tables are coarse approximations: states constantly change whether SaaS,
digital goods, and services are taxable.
"""

from __future__ import annotations

from .deadlines import next_deadline, quarterly_deadlines, upcoming_deadlines
from .models import Ledger, SE_INCOME_TYPES
from .nexus import THRESHOLDS, report as nexus_report
from .tax import estimate

# States with no statewide sales tax at all.
NO_SALES_TAX = {state for state, t in THRESHOLDS.items() if t is None}
SALES_TAX_STATES = set(THRESHOLDS) - NO_SALES_TAX

# Where each product type is *generally* subject to sales tax. Coarse!
TAXABILITY: dict[str, set[str]] = {
    # SaaS / cloud software accessed remotely.
    "saas": {"AZ", "CT", "DC", "HI", "IA", "KY", "LA", "MA", "MS", "NM", "NY",
             "OH", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "WA", "WV"},
    # Downloaded digital goods (software, media, e-books).
    "digital": {"AL", "AR", "AZ", "CO", "CT", "DC", "GA", "HI", "IA", "ID",
                "IN", "KS", "KY", "LA", "ME", "MD", "MN", "MS", "NC", "NE",
                "NJ", "NM", "NY", "OH", "PA", "RI", "SD", "TN", "TX", "UT",
                "VT", "WA", "WI", "WV", "WY"},
    # Physical goods: taxable essentially everywhere that has a sales tax.
    "physical": SALES_TAX_STATES,
    # Most professional/personal services are exempt outside the broad
    # gross-receipts states.
    "services": {"HI", "NM", "SD", "WV"},
    # Mixed: be conservative and treat like physical goods.
    "mixed": SALES_TAX_STATES,
}

PRODUCT_LABELS = {
    "saas": "SaaS / cloud software",
    "digital": "downloadable digital products",
    "physical": "physical goods",
    "services": "services",
    "mixed": "a mix of products",
}


def product_taxable_in(product_type: str, state: str) -> bool | None:
    """True/False if we have a guess for this product/state; None if unknown."""
    if not product_type or not state:
        return None
    if state in NO_SALES_TAX:
        return False
    return state in TAXABILITY[product_type]


def explain(ledger: Ledger) -> list[tuple[str, list[str]]]:
    """Personalized guidance as (section title, lines) pairs."""
    est = estimate(ledger)
    sections: list[tuple[str, list[str]]] = []
    has_se = any(i.type in SE_INCOME_TYPES for i in ledger.incomes)
    has_w2 = any(i.type == "w2" for i in ledger.incomes)
    next_year = ledger.year + 1

    # --- What you owe, from their recorded numbers -----------------------
    lines = []
    if est["se_gross"] or est["other_income"]:
        lines.append(
            f"Based on the {_money(est['se_gross'] + est['other_income'])} of income "
            f"you've recorded for {ledger.year}, your estimated total tax is "
            f"{_money(est['total_tax'])}:"
        )
        lines.append(f"  • Federal income tax: {_money(est['income_tax'])}")
        if est["se_tax"]:
            lines.append(
                f"  • Self-employment tax (Social Security + Medicare on your "
                f"business profit): {_money(est['se_tax'])}"
            )
        if ledger.state:
            lines.append(f"  • {ledger.state} state income tax: {_money(est['state_tax'])}")
        lines.append(
            f"You've recorded {_money(est['payments'])} in payments, leaving "
            f"{_money(abs(est['balance_due']))} "
            + ("still to pay." if est["balance_due"] >= 0 else "overpaid.")
        )
        nd = next_deadline(ledger.year)
        if nd and est["balance_due"] > 0:
            quarter, due = nd
            remaining = len(upcoming_deadlines(ledger.year))
            lines.append(
                f"To stay on track, pay about {_money(est['balance_due'] / remaining)} "
                f"by {due.isoformat()} ({quarter} deadline)."
            )
    else:
        lines.append(
            "No income recorded yet. Add income (or import Stripe payouts) and "
            "this section will show exactly what you owe and when."
        )
    sections.append(("What you owe right now", lines))

    # --- Federal filings --------------------------------------------------
    lines = []
    if has_se or not ledger.incomes:
        lines.append(
            f"Form 1040 (your personal return) with Schedule C (business profit "
            f"and loss) and Schedule SE (self-employment tax) — due April 15, "
            f"{next_year}."
        )
        lines.append(
            "Form 1040-ES quarterly estimated payments — due "
            + ", ".join(d.isoformat() for _, d in quarterly_deadlines(ledger.year))
            + ". The IRS expects you to pay as you earn; underpaying can mean penalties."
        )
        lines.append(
            "Pay online at IRS Direct Pay (no voucher needed) and record each "
            "payment here so your balance stays accurate."
        )
    if has_w2 and not has_se:
        lines.append(
            f"Form 1040 — due April 15, {next_year}. With W-2 income only, your "
            "employer's withholding usually covers you; check that withholding "
            "roughly matches the estimate above."
        )
    sections.append(("What to file: federal", lines))

    # --- State income tax --------------------------------------------------
    lines = []
    if not ledger.state:
        lines.append(
            "Set your home state (Settings) and this section will tell you "
            "whether you owe a state return."
        )
    elif est["state_rate"] == 0 and ledger.state_rate is None:
        lines.append(
            f"{ledger.state} has no state income tax — no state income tax "
            "return to file. Lucky you."
        )
    else:
        lines.append(
            f"{ledger.state} state income tax return — also due around April 15, "
            f"{next_year}. Most states piggyback on your federal numbers."
        )
        lines.append(
            f"Many states also expect quarterly estimated payments; record them "
            f"here with jurisdiction 'state'."
        )
    sections.append(("What to file: state income tax", lines))

    # --- Sales tax ----------------------------------------------------------
    lines = []
    product = ledger.product_type
    if not product:
        lines.append(
            "Tell us what you sell (run Setup or set it in Settings) and this "
            "section will explain where sales tax applies to you."
        )
    else:
        label = PRODUCT_LABELS[product]
        home = ledger.state
        if home:
            taxable_home = product_taxable_in(product, home)
            if home in NO_SALES_TAX:
                lines.append(f"{home} has no statewide sales tax, so in-state sales "
                             f"of {label} aren't taxed.")
            elif taxable_home:
                lines.append(
                    f"{home} generally DOES tax {label}. Selling to {home} "
                    f"customers usually means registering for a {home} sales tax "
                    f"permit, collecting tax, and filing returns (monthly or "
                    f"quarterly, the state assigns the schedule)."
                )
            else:
                lines.append(
                    f"{home} generally does NOT tax {label}, so in-state sales "
                    f"are likely exempt — but verify, exemptions have fine print."
                )
        if ledger.sales_mode == "online":
            hot = [n for n in nexus_report(ledger) if n.status in ("approaching", "reached")]
            if hot:
                for n in hot:
                    taxable = product_taxable_in(product, n.state)
                    if n.status == "reached":
                        prefix = (f"You've crossed {n.state}'s economic nexus "
                                  f"threshold ({_money(n.sales)} in sales).")
                    else:
                        prefix = (f"You're at {n.progress:.0%} of {n.state}'s "
                                  f"economic nexus threshold.")
                    if taxable:
                        lines.append(
                            f"{prefix} {n.state} generally taxes {label} — you may "
                            f"need to register and collect there. Talk to a tax "
                            f"advisor before your next sale into {n.state}."
                        )
                    else:
                        lines.append(
                            f"{prefix} The good news: {n.state} generally does not "
                            f"tax {label}, so you may have no collection duty even "
                            f"with nexus — confirm with a tax advisor."
                        )
            else:
                lines.append(
                    "You sell online: each state's sales-tax duty only kicks in "
                    "after you cross its economic nexus threshold (usually "
                    "$100k/200 transactions per year). Keep recording sales and "
                    "watch the Nexus Map — we'll warn you at 80%."
                )
        else:
            lines.append(
                "You sell in person, so sales tax is generally just your home "
                "state's rules above — no multi-state tracking needed unless you "
                "start selling remotely (switch the mode in Settings if that changes)."
            )
        lines.append(
            "Note: sales tax is collected from the buyer and passed through — "
            "it's not included in the income-tax numbers above."
        )
    sections.append(("Sales tax: where it applies to you", lines))

    sections.append(("The fine print", [
        "This guidance assumes a sole proprietor or single-member LLC. "
        "Corporations, partnerships, and employees-of-your-own-S-corp have "
        "different filings.",
        "Taxability rules and nexus thresholds are approximations and change "
        "constantly. Before registering anywhere or filing anything, confirm "
        "with a licensed tax professional.",
    ]))
    return sections


def _money(value: float) -> str:
    return f"${value:,.2f}"
