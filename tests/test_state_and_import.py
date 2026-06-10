import tempfile
import unittest
from pathlib import Path

from taxtracker import storage
from taxtracker.cli import main
from taxtracker.importer import parse_payout_csv, ImportError_
from taxtracker.models import Income, Ledger, Payment
from taxtracker.tax import estimate, state_rate_for

STRIPE_CSV = """\
id,Type,Source,Amount,Fee,Net,Currency,Created (UTC),Arrival Date (UTC),Status,Description
po_001,payout,card,"1,050.00",30.45,"1,019.55",usd,2026-02-27 10:00,2026-03-01,paid,STRIPE PAYOUT
po_002,payout,card,500.00,14.80,485.20,usd,2026-05-29 10:00,2026-06-01,paid,STRIPE PAYOUT
po_003,payout,card,200.00,6.10,193.90,usd,2026-06-04 10:00,2026-06-08,in_transit,STRIPE PAYOUT
po_004,payout,card,900.00,26.40,873.60,usd,2025-12-28 10:00,2025-12-31,paid,STRIPE PAYOUT
"""


class StateTaxTests(unittest.TestCase):
    def test_no_state_means_no_state_tax(self):
        ledger = Ledger(year=2026)
        self.assertEqual(state_rate_for(ledger), 0.0)
        self.assertEqual(estimate(ledger)["state_tax"], 0.0)

    def test_no_income_tax_state(self):
        ledger = Ledger(year=2026, state="TX")
        self.assertEqual(state_rate_for(ledger), 0.0)

    def test_flat_rate_state_applied_to_taxable_income(self):
        ledger = Ledger(
            year=2026, state="PA",
            incomes=[Income(amount=100_000, source="MySaaS", type="saas", date="2026-01-01")],
        )
        est = estimate(ledger)
        self.assertAlmostEqual(est["state_tax"], est["taxable_income"] * 0.0307)
        self.assertAlmostEqual(
            est["total_tax"], est["income_tax"] + est["se_tax"] + est["state_tax"]
        )

    def test_rate_override_beats_table(self):
        ledger = Ledger(year=2026, state="CA", state_rate=0.05)
        self.assertEqual(state_rate_for(ledger), 0.05)

    def test_unknown_state_raises(self):
        with self.assertRaises(ValueError):
            state_rate_for(Ledger(year=2026, state="ZZ"))

    def test_payments_split_by_jurisdiction(self):
        ledger = Ledger(
            year=2026, state="CA",
            incomes=[Income(amount=50_000, source="MySaaS", type="saas", date="2026-01-01")],
            payments=[
                Payment(amount=3_000, date="2026-04-10", jurisdiction="federal"),
                Payment(amount=800, date="2026-04-10", jurisdiction="state"),
            ],
        )
        est = estimate(ledger)
        self.assertEqual(est["federal_payments"], 3_000)
        self.assertEqual(est["state_payments"], 800)
        self.assertAlmostEqual(est["federal_balance"], est["federal_tax"] - 3_000)
        self.assertAlmostEqual(est["state_balance"], est["state_tax"] - 800)


class StripeImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")
        self.csv_path = Path(self.tmp.name) / "payouts.csv"
        self.csv_path.write_text(STRIPE_CSV)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_uses_net_amount_and_skips_unpaid(self):
        rows, skipped = parse_payout_csv(self.csv_path)
        self.assertEqual(len(rows), 3)  # po_003 is in_transit
        self.assertEqual(skipped, 1)
        self.assertEqual(rows[0]["amount"], 1019.55)
        self.assertEqual(rows[0]["date"], "2026-03-01")  # arrival date, ISO

    def test_import_routes_payouts_to_their_tax_year(self):
        main(["--data", self.data, "import-stripe", str(self.csv_path)])
        ledger_2026 = storage.load(Path(self.data), 2026)
        ledger_2025 = storage.load(Path(self.data), 2025)
        self.assertEqual(len(ledger_2026.incomes), 2)
        self.assertEqual(len(ledger_2025.incomes), 1)
        self.assertEqual(ledger_2025.incomes[0].amount, 873.60)
        self.assertEqual(ledger_2026.incomes[0].note, "stripe:po_001")
        self.assertEqual(ledger_2026.incomes[0].type, "saas")

    def test_reimport_is_idempotent(self):
        main(["--data", self.data, "import-stripe", str(self.csv_path)])
        main(["--data", self.data, "import-stripe", str(self.csv_path)])
        ledger_2026 = storage.load(Path(self.data), 2026)
        self.assertEqual(len(ledger_2026.incomes), 2)

    def test_unrecognizable_csv_raises(self):
        bad = Path(self.tmp.name) / "bad.csv"
        bad.write_text("foo,bar\n1,2\n")
        with self.assertRaises(ImportError_):
            parse_payout_csv(bad)


class StateCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_persists_across_runs(self):
        main(["--data", self.data, "--year", "2026", "status", "--state", "ca"])
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(ledger.state, "CA")
        # subsequent plain status keeps it
        main(["--data", self.data, "--year", "2026", "status"])
        self.assertEqual(storage.load(Path(self.data), 2026).state, "CA")


if __name__ == "__main__":
    unittest.main()
