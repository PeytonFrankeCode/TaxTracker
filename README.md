# TaxTracker

A command-line tool to track income from any source — your SaaS, freelance
work, a W-2 day job — estimate the federal taxes you'll owe, record the
payments you've made, and keep you ahead of the IRS quarterly estimated-payment
deadlines.

Pure Python standard library. No dependencies to install. Requires Python 3.10+.

## Quick start

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
| `import-stripe payouts.csv --source "MySaaS"` | Import a Stripe payout CSV (`--type` defaults to saas) |

All data is stored in one human-readable JSON file, with each tax year kept
separately.

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

Not modeled: progressive state brackets, local taxes, QBI deduction, itemized
deductions, tax credits, capital gains rates, or holiday/weekend deadline
shifts. This is a planning tool to keep you from being surprised at filing
time — not tax advice or a substitute for filing software or a professional.
