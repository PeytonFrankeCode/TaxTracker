import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from taxtracker import storage
from taxtracker.cli import main


def run_session(data_path: str, inputs: list[str]) -> str:
    """Run interactive mode (no subcommand) feeding scripted answers."""
    out = io.StringIO()
    with patch("builtins.input", side_effect=inputs), contextlib.redirect_stdout(out):
        code = main(["--data", data_path, "--year", "2026"])
    assert code == 0
    return out.getvalue()


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_income_then_quit(self):
        # menu choice, amount, source, type(default), date(default), note(default), quit
        output = run_session(self.data, ["1", "1000", "MySaaS", "", "", "", "q"])
        self.assertIn("Recorded $1,000.00 saas income from MySaaS", output)
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(len(ledger.incomes), 1)
        self.assertEqual(ledger.incomes[0].source, "MySaaS")

    def test_invalid_amount_reprompts(self):
        output = run_session(self.data, ["1", "abc", "50", "MySaaS", "", "", "", "q"])
        self.assertIn("Enter a number", output)
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(ledger.incomes[0].amount, 50.0)

    def test_status_view_and_quit(self):
        output = run_session(self.data, ["5", "q"])
        self.assertIn("Total estimated tax", output)

    def test_payment_flow(self):
        # choice, amount, kind(default), jurisdiction -> state, date(default), note(default)
        output = run_session(self.data, ["3", "750", "", "state", "", "", "q"])
        self.assertIn("Recorded $750.00 estimated payment (state)", output)
        ledger = storage.load(Path(self.data), 2026)
        self.assertEqual(ledger.payments[0].jurisdiction, "state")

    def test_settings_change_state(self):
        # settings, option 2 (state), code, then quit
        output = run_session(self.data, ["8", "2", "ca", "q"])
        self.assertIn("state CA", output)
        self.assertEqual(storage.load(Path(self.data), 2026).state, "CA")

    def test_settings_switch_year(self):
        output = run_session(self.data, ["8", "4", "2025", "q"])
        self.assertIn("Tax year 2025", output)

    def test_eof_exits_cleanly(self):
        out = io.StringIO()
        with patch("builtins.input", side_effect=EOFError), contextlib.redirect_stdout(out):
            code = main(["--data", self.data, "--year", "2026"])
        self.assertEqual(code, 0)
        self.assertIn("Bye", out.getvalue())


if __name__ == "__main__":
    unittest.main()
