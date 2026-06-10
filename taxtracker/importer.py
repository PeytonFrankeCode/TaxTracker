"""Import income records from Stripe payout CSV exports.

Stripe's payout export columns vary by report type, so column matching is
forgiving: headers are case-insensitive, the net amount is preferred over the
gross amount (fees are already a real cost), and only payouts with a "paid"
status are imported. Each payout's Stripe id is kept in the income note so
re-importing the same file never creates duplicates.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

# Candidate column names, in priority order, normalized to lowercase.
AMOUNT_COLUMNS = ["net", "amount"]
DATE_COLUMNS = ["arrival date (utc)", "arrival_date", "created (utc)", "created", "date"]
ID_COLUMNS = ["id", "payout id"]

DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y", "%m/%d/%y"]


class ImportError_(ValueError):
    """Raised when a CSV can't be interpreted as a payout export."""


def _pick_column(headers: dict[str, str], candidates: list[str]) -> str | None:
    """Return the original header name for the first matching candidate."""
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def _parse_amount(raw: str) -> float:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):  # accounting negatives
        cleaned = "-" + cleaned[1:-1]
    return float(cleaned)


def _parse_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    # ISO timestamps like 2026-03-01T00:00:00Z
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        raise ImportError_(f"Unrecognized date format: {raw!r}")


def parse_payout_csv(path: str | Path) -> tuple[list[dict], int]:
    """Parse a Stripe payout CSV into rows of {id, amount, date}.

    Returns (rows, skipped) where skipped counts unpaid/failed/zero-amount
    rows that were ignored.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ImportError_(f"{path} has no header row")
        headers = {h.strip().lower(): h for h in reader.fieldnames}

        amount_col = _pick_column(headers, AMOUNT_COLUMNS)
        date_col = _pick_column(headers, DATE_COLUMNS)
        id_col = _pick_column(headers, ID_COLUMNS)
        status_col = headers.get("status")
        if not amount_col or not date_col:
            raise ImportError_(
                f"{path} doesn't look like a Stripe payout export: need an "
                f"amount column ({'/'.join(AMOUNT_COLUMNS)}) and a date column "
                f"({'/'.join(DATE_COLUMNS)}); found {reader.fieldnames}"
            )

        rows = []
        skipped = 0
        for line in reader:
            if status_col and line[status_col].strip().lower() not in ("paid", ""):
                skipped += 1
                continue
            amount = _parse_amount(line[amount_col])
            if amount <= 0:
                skipped += 1
                continue
            rows.append({
                "id": line[id_col].strip() if id_col else "",
                "amount": amount,
                "date": _parse_date(line[date_col]),
            })
        return rows, skipped
