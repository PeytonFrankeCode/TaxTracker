"""JSON persistence for ledgers, one file holding all tax years."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Ledger

DEFAULT_PATH = Path.home() / ".taxtracker" / "data.json"


def data_path(override: str | None = None) -> Path:
    """Resolve the data file path: CLI flag > TAXTRACKER_DATA env var > default."""
    if override:
        return Path(override)
    env = os.environ.get("TAXTRACKER_DATA")
    if env:
        return Path(env)
    return DEFAULT_PATH


def load(path: Path, year: int, filing_status: str | None = None) -> Ledger:
    """Load the ledger for a tax year, creating an empty one if absent."""
    ledgers = _load_all(path)
    raw = ledgers.get(str(year))
    if raw is None:
        return Ledger(year=year, filing_status=filing_status or "single")
    ledger = Ledger.from_dict(raw)
    if filing_status:
        ledger.filing_status = filing_status
    return ledger


def save(path: Path, ledger: Ledger) -> None:
    ledgers = _load_all(path)
    ledgers[str(ledger.year)] = ledger.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledgers, indent=2) + "\n")
    tmp.replace(path)


def _load_all(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())
