import tempfile
import unittest
from pathlib import Path

from taxtracker import storage
from taxtracker.cli import main
from taxtracker.models import Ledger, Sale
from taxtracker.nexus import report, warnings


def ledger_with_sales(*sales):
    return Ledger(year=2026, sales=list(sales))


class NexusReportTests(unittest.TestCase):
    def test_no_sales_empty_report(self):
        self.assertEqual(report(Ledger(year=2026)), [])

    def test_ok_below_threshold(self):
        ledger = ledger_with_sales(Sale(amount=10_000, state="TX", date="2026-01-15"))
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "ok")
        self.assertAlmostEqual(nexus.progress, 10_000 / 500_000)

    def test_approaching_at_80_percent(self):
        ledger = ledger_with_sales(Sale(amount=80_000, state="FL", date="2026-01-15"))
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "approaching")
        self.assertEqual(len(warnings(ledger)), 1)
        self.assertIn("Consult a tax advisor", warnings(ledger)[0])

    def test_reached_threshold(self):
        ledger = ledger_with_sales(Sale(amount=120_000, state="FL", date="2026-01-15"))
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "reached")
        self.assertIn("NEXUS THRESHOLD REACHED in FL", warnings(ledger)[0])

    def test_transaction_count_can_trip_or_states(self):
        # GA: $100k OR 200 transactions — 200 small sales should trip it.
        ledger = ledger_with_sales(
            Sale(amount=2_000, state="GA", date="2026-01-15", transactions=200)
        )
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "reached")

    def test_and_state_needs_both(self):
        # NY: $500k AND 100 transactions. Big dollars but few transactions = ok.
        ledger = ledger_with_sales(
            Sale(amount=600_000, state="NY", date="2026-01-15", transactions=5)
        )
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "ok")

    def test_no_sales_tax_state(self):
        ledger = ledger_with_sales(Sale(amount=1_000_000, state="OR", date="2026-01-15"))
        (nexus,) = report(ledger)
        self.assertEqual(nexus.status, "no_sales_tax")
        self.assertEqual(warnings(ledger), [])

    def test_sales_accumulate_per_state(self):
        ledger = ledger_with_sales(
            Sale(amount=50_000, state="FL", date="2026-01-15"),
            Sale(amount=40_000, state="FL", date="2026-03-15"),
        )
        (nexus,) = report(ledger)
        self.assertEqual(nexus.sales, 90_000)
        self.assertEqual(nexus.status, "approaching")


class SaleCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        return main(["--data", self.data, "--year", "2026", *argv])

    def test_online_mode_requires_to_state(self):
        self.assertEqual(self.run_cli("sale", "100"), 1)

    def test_sale_with_state(self):
        self.assertEqual(self.run_cli("sale", "100", "--to-state", "tx"), 0)
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(ledger.sales[0].state, "TX")

    def test_in_person_mode_defaults_to_home_state(self):
        self.run_cli("status", "--state", "CA", "--mode", "in-person")
        self.assertEqual(self.run_cli("sale", "250"), 0)
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(ledger.sales[0].state, "CA")
        self.assertEqual(ledger.sales_mode, "in-person")

    def test_nexus_command_runs(self):
        self.run_cli("sale", "90000", "--to-state", "FL")
        self.assertEqual(self.run_cli("nexus"), 0)


if __name__ == "__main__":
    unittest.main()
