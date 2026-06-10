import json
import tempfile
import unittest
from pathlib import Path

from taxtracker import storage
from taxtracker.cli import main
from taxtracker.models import Income, Ledger


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_file_gives_empty_ledger(self):
        ledger = storage.load(self.path, 2026)
        self.assertEqual(ledger.year, 2026)
        self.assertEqual(ledger.incomes, [])

    def test_save_and_reload_roundtrip(self):
        ledger = Ledger(year=2026, incomes=[
            Income(amount=500, source="MySaaS", type="saas", date="2026-01-05")
        ])
        storage.save(self.path, ledger)
        reloaded = storage.load(self.path, 2026)
        self.assertEqual(len(reloaded.incomes), 1)
        self.assertEqual(reloaded.incomes[0].source, "MySaaS")

    def test_multiple_years_coexist(self):
        storage.save(self.path, Ledger(year=2025))
        storage.save(self.path, Ledger(year=2026))
        data = json.loads(self.path.read_text())
        self.assertEqual(set(data.keys()), {"2025", "2026"})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        return main(["--data", self.path, "--year", "2026", *argv])

    def test_income_payment_status_flow(self):
        self.assertEqual(self.run_cli("income", "1000", "--source", "MySaaS",
                                      "--type", "saas", "--date", "2026-02-01"), 0)
        self.assertEqual(self.run_cli("payment", "100", "--date", "2026-04-01"), 0)
        self.assertEqual(self.run_cli("status"), 0)
        ledger = storage.load(Path(self.path), 2026)
        self.assertEqual(len(ledger.incomes), 1)
        self.assertEqual(len(ledger.payments), 1)

    def test_filing_status_persists(self):
        self.run_cli("status", "--filing-status", "married")
        ledger = storage.load(Path(self.path), 2026)
        self.assertEqual(ledger.filing_status, "married")


if __name__ == "__main__":
    unittest.main()
