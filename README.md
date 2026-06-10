# TaxTracker

Track income from any source — your SaaS, freelance work, a W-2 day job —
estimate the federal and state taxes you'll owe, record the payments you've
made, stay ahead of IRS quarterly deadlines, and get warned **before** your
sales cross a state's sales-tax economic nexus threshold.

Comes in two flavors that share the same data format:

- a **CLI / interactive terminal app** (pure Python stdlib, Python 3.10+,
  nothing to install), and
- a **static web app** in [`docs/`](docs/) with a clickable US nexus map —
  deployable free on GitHub Pages or Cloudflare Pages.

> **Disclaimer:** TaxTracker provides estimates only and accepts no
> responsibility for incorrect tax documents, filings, or penalties. Always
> consult a licensed tax professional. See [DISCLAIMER.md](DISCLAIMER.md).

## Quick start

The easiest way to use TaxTracker is interactive mode — just run it with no
arguments and answer the prompts:

```bash
python -m taxtracker
```

```
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
```

Every option walks you through with questions (amount? source? date?) and
sensible defaults — press Enter to accept the suggestion in brackets.

Everything is also available as direct commands for scripting or quick
one-liners:

```bash
# Record income (saas/freelance/business types are subject to self-employment tax)
python -m taxtracker income 8500 --source "MySaaS" --type saas
python -m taxtracker income 1200 --source "Consulting gig" --type freelance
python -m taxtracker income 4000 --source "Day job" --type w2

# Record deductible business expenses
python -m taxtracker expense 240 --description "AWS hosting" --category hosting

# Import your Stripe payouts directly (uses net amounts, skips unpaid,
# never double-imports the same payout)
python -m taxtracker import-stripe payouts.csv

# Record tax payments you've made (estimated payments or W-2 withholding)
python -m taxtracker payment 2000 --kind estimated
python -m taxtracker payment 600 --kind withholding --note "from paycheck"
python -m taxtracker payment 500 --jurisdiction state

# Include your state's income tax in the estimate (persisted per year)
python -m taxtracker status --state CA

# Track sales for economic nexus warnings. Online mode records the buyer's
# state; in-person mode defaults sales to your home state. Switch any time.
python -m taxtracker status --mode online
python -m taxtracker sale 4500 --to-state TX --transactions 12
python -m taxtracker nexus

# See where you stand
python -m taxtracker status
python -m taxtracker deadlines
python -m taxtracker list
```

`status` shows the full picture: net self-employment profit, estimated federal
income tax and self-employment tax, what you've paid so far, your balance due,
the next quarterly deadline, and a suggested payment to spread the remaining
balance across the remaining quarters.

```
Tax year 2026 (filing status: single)
----------------------------------------------------
  Self-employment income       $9,700.00
  ...
  Total estimated tax          $1,210.69
  Payments made                $2,600.00
  Overpaid                     $1,389.31
```

## Options

| Flag | Meaning |
| --- | --- |
| `--year 2025` | Work with a different tax year (default: current year) |
| `--data path.json` | Use a specific data file (default: `~/.taxtracker/data.json`, or `TAXTRACKER_DATA` env var) |
| `status --filing-status married` | Set your filing status (single/married) for the year |
| `status --state CA` | Include state income tax (two-letter code; persisted) |
| `status --state-rate 0.05` | Override the built-in state rate with your own |
| `status --mode in-person` | Sales mode: `online` or `in-person` (changeable any time) |
| `sale 4500 --to-state TX` | Record a sale toward that state's nexus threshold |
| `nexus` | Per-state sales vs nexus thresholds, with warnings |
| `import-stripe payouts.csv --source "MySaaS"` | Import a Stripe payout CSV (`--type` defaults to saas) |

All data is stored in one human-readable JSON file, with each tax year kept
separately.

## Sales-tax nexus warnings

Since *South Dakota v. Wayfair* (2018), most states require remote sellers to
register and collect sales tax once sales into the state pass an "economic
nexus" threshold — typically $100,000 and/or 200 transactions per year
(CA/TX/NY are $500,000). Record your sales with the `sale` command (or the
web UI) and TaxTracker warns you at **80%** of any state's threshold — and
again when you cross it — with a reminder to **consult a tax advisor before
continuing to sell into that state**. Warnings appear in `status`, in
`nexus`, when recording the sale itself, and as banners in the web app.

## The web app

[`docs/`](docs/) is a zero-dependency static site: dashboard, entry forms,
records, settings, and a **US tile map** that colors each state by how much
of its nexus threshold you've used (click a state for its threshold). Data
stays in your browser's localStorage; Export/Import JSON round-trips with the
CLI's data file.

**Host it on GitHub Pages:** repo Settings → Pages → Source: *Deploy from a
branch* → Branch: `main`, folder `/docs`. Your site appears at
`https://<user>.github.io/TaxTracker/`.

**Move to Cloudflare later:** the site is plain HTML/CSS/JS, so Cloudflare
Pages serves it unchanged — create a Pages project from the repo and set the
output directory to `docs`.

## Running the tests

```bash
python -m unittest discover -s tests -v
```

## What it models (and what it doesn't)

Estimates are based on 2025 federal rules: tax brackets, standard deduction,
self-employment tax (15.3% with the Social Security wage-base cap and the
half-of-SE-tax deduction). Quarterly deadlines are the nominal IRS dates
(Apr 15, Jun 15, Sep 15, Jan 15).

State tax uses a flat rate per state (all 50 states + DC built in). For
flat-tax and no-tax states this is accurate; for progressive states (CA, NY,
OR, ...) it's a rough effective-rate approximation — set your own with
`--state-rate` if you know better. Payments recorded with
`--jurisdiction state` are netted against the state side, everything else
against federal.

Stripe import accepts the payout CSV you download from the Stripe dashboard
(Balance → Payouts → Export). It uses the **net** amount (after Stripe fees),
only imports payouts with `paid` status, files each payout under the tax year
it arrived in, and remembers payout IDs so re-importing the same file is safe.

Nexus thresholds are approximations of each state's published rules and
change often; states also differ on what counts (gross vs. retail vs. taxable
sales) and over what period. Treat the warnings as a prompt to talk to a
professional, not as a registration decision.

Not modeled: progressive state brackets, local taxes, QBI deduction, itemized
deductions, tax credits, capital gains rates, or holiday/weekend deadline
shifts. This is a planning tool to keep you from being surprised at filing
time — not tax advice or a substitute for filing software or a professional.
See [DISCLAIMER.md](DISCLAIMER.md).
