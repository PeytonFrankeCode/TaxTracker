"""Sync paid payouts directly from the Stripe API.

Uses only the Python standard library. Authenticate with a RESTRICTED Stripe
API key that has read-only access to Payouts (Stripe dashboard → Developers
→ API keys → Create restricted key). Never use your full secret key here —
TaxTracker only needs to read payouts.

The key is resolved in this order:
  1. --api-key flag
  2. STRIPE_API_KEY environment variable
  3. a `stripe_key` file next to your data file (created by --save-key)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.stripe.com/v1/payouts"
PAGE_SIZE = 100
MAX_PAGES = 50  # safety valve: 5,000 payouts per sync


class StripeError(RuntimeError):
    """A sync problem the user can act on (bad key, network, API error)."""


def resolve_key(flag_value: str | None, data_path: Path) -> str | None:
    if flag_value:
        return flag_value
    env = os.environ.get("STRIPE_API_KEY")
    if env:
        return env
    key_file = data_path.parent / "stripe_key"
    if key_file.exists():
        return key_file.read_text().strip()
    return None


def save_key(data_path: Path, key: str) -> Path:
    """Store the key beside the data file, readable only by the owner."""
    key_file = data_path.parent / "stripe_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key.strip() + "\n")
    os.chmod(key_file, 0o600)
    return key_file


def fetch_payouts(api_key: str) -> list[dict]:
    """All paid payouts as {id, amount, date} rows (amounts in dollars)."""
    rows: list[dict] = []
    starting_after: str | None = None
    for _ in range(MAX_PAGES):
        params = {"limit": str(PAGE_SIZE), "status": "paid"}
        if starting_after:
            params["starting_after"] = starting_after
        request = urllib.request.Request(
            API_URL + "?" + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise StripeError(
                    "Stripe rejected the API key. Create a restricted key with "
                    "read access to Payouts (Dashboard → Developers → API keys)."
                ) from exc
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise StripeError(f"Stripe API error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise StripeError(f"Couldn't reach Stripe: {exc.reason}") from exc

        page = payload.get("data", [])
        for payout in page:
            arrival = datetime.fromtimestamp(payout["arrival_date"], tz=timezone.utc)
            rows.append({
                "id": payout["id"],
                "amount": payout["amount"] / 100,
                "date": arrival.date().isoformat(),
            })
        if not payload.get("has_more") or not page:
            return rows
        starting_after = page[-1]["id"]
    raise StripeError(
        f"Stopped after {MAX_PAGES * PAGE_SIZE} payouts; something looks wrong."
    )
