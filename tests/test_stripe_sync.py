import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from taxtracker import storage
from taxtracker.cli import main
from taxtracker.stripe_sync import (StripeError, fetch_payouts, resolve_key,
                                    save_key)

# 2026-03-01 and 2026-06-01 in unix time (UTC).
TS_MAR = 1772323200
TS_JUN = 1780272000


def fake_response(payload):
    body = io.BytesIO(json.dumps(payload).encode())
    body.__enter__ = lambda *a: body
    body.__exit__ = lambda *a: False
    return body


class FetchPayoutsTests(unittest.TestCase):
    @patch("taxtracker.stripe_sync.urllib.request.urlopen")
    def test_single_page(self, urlopen):
        urlopen.return_value = fake_response({
            "data": [{"id": "po_1", "amount": 101955, "arrival_date": TS_MAR}],
            "has_more": False,
        })
        rows = fetch_payouts("rk_test")
        self.assertEqual(rows, [{"id": "po_1", "amount": 1019.55, "date": "2026-03-01"}])
        request = urlopen.call_args[0][0]
        self.assertIn("Bearer rk_test", request.headers["Authorization"])
        self.assertIn("status=paid", request.full_url)

    @patch("taxtracker.stripe_sync.urllib.request.urlopen")
    def test_pagination_follows_has_more(self, urlopen):
        urlopen.side_effect = [
            fake_response({"data": [{"id": "po_1", "amount": 1000, "arrival_date": TS_MAR}],
                           "has_more": True}),
            fake_response({"data": [{"id": "po_2", "amount": 2000, "arrival_date": TS_JUN}],
                           "has_more": False}),
        ]
        rows = fetch_payouts("rk_test")
        self.assertEqual([r["id"] for r in rows], ["po_1", "po_2"])
        second_url = urlopen.call_args_list[1][0][0].full_url
        self.assertIn("starting_after=po_1", second_url)

    @patch("taxtracker.stripe_sync.urllib.request.urlopen")
    def test_bad_key_gives_actionable_error(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.stripe.com", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        with self.assertRaises(StripeError) as ctx:
            fetch_payouts("bad_key")
        self.assertIn("restricted key", str(ctx.exception))

    @patch("taxtracker.stripe_sync.urllib.request.urlopen")
    def test_network_error_wrapped(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("dns down")
        with self.assertRaises(StripeError) as ctx:
            fetch_payouts("rk_test")
        self.assertIn("Couldn't reach Stripe", str(ctx.exception))


class KeyResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data.json"

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("STRIPE_API_KEY", None)

    def test_flag_beats_env_and_file(self):
        os.environ["STRIPE_API_KEY"] = "rk_env"
        save_key(self.data, "rk_file")
        self.assertEqual(resolve_key("rk_flag", self.data), "rk_flag")

    def test_env_beats_file(self):
        os.environ["STRIPE_API_KEY"] = "rk_env"
        save_key(self.data, "rk_file")
        self.assertEqual(resolve_key(None, self.data), "rk_env")

    def test_saved_file_used_last_and_owner_only(self):
        key_file = save_key(self.data, "rk_file")
        self.assertEqual(resolve_key(None, self.data), "rk_file")
        mode = stat.S_IMODE(os.stat(key_file).st_mode)
        self.assertEqual(mode, 0o600)

    def test_no_key_returns_none(self):
        self.assertIsNone(resolve_key(None, self.data))


class SyncCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("STRIPE_API_KEY", None)

    @patch("taxtracker.stripe_sync.fetch_payouts")
    def test_sync_imports_and_dedupes(self, fetch):
        fetch.return_value = [
            {"id": "po_1", "amount": 1019.55, "date": "2026-03-01"},
            {"id": "po_2", "amount": 485.20, "date": "2025-12-31"},
        ]
        code = main(["--data", self.data, "sync-stripe", "--api-key", "rk_test"])
        self.assertEqual(code, 0)
        self.assertEqual(len(storage.load(Path(self.data), 2026).incomes), 1)
        self.assertEqual(len(storage.load(Path(self.data), 2025).incomes), 1)
        # Second sync of the same payouts adds nothing.
        main(["--data", self.data, "sync-stripe", "--api-key", "rk_test"])
        self.assertEqual(len(storage.load(Path(self.data), 2026).incomes), 1)

    def test_missing_key_fails_with_guidance(self):
        code = main(["--data", self.data, "sync-stripe"])
        self.assertEqual(code, 1)

    @patch("taxtracker.stripe_sync.fetch_payouts")
    def test_save_key_persists_for_next_run(self, fetch):
        fetch.return_value = []
        main(["--data", self.data, "sync-stripe", "--api-key", "rk_test", "--save-key"])
        self.assertEqual(resolve_key(None, Path(self.data)), "rk_test")
        # Next run needs no flag.
        code = main(["--data", self.data, "sync-stripe"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
