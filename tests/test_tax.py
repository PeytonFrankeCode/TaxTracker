import unittest

from taxtracker.models import Income, Expense, Payment, Ledger
from taxtracker.tax import estimate, income_tax, self_employment_tax


class IncomeTaxTests(unittest.TestCase):
    def test_zero_income(self):
        self.assertEqual(income_tax(0, "single"), 0.0)

    def test_first_bracket_single(self):
        self.assertAlmostEqual(income_tax(10_000, "single"), 1_000.0)

    def test_crosses_brackets_single(self):
        # 11,925 @ 10% + (50,000 - 11,925) @ 12%... only up to 48,475,
        # then (50,000 - 48,475) @ 22%
        expected = 11_925 * 0.10 + (48_475 - 11_925) * 0.12 + (50_000 - 48_475) * 0.22
        self.assertAlmostEqual(income_tax(50_000, "single"), expected)

    def test_married_brackets_wider(self):
        self.assertLess(income_tax(100_000, "married"), income_tax(100_000, "single"))


class SETaxTests(unittest.TestCase):
    def test_no_profit_no_tax(self):
        self.assertEqual(self_employment_tax(0), 0.0)
        self.assertEqual(self_employment_tax(-5_000), 0.0)

    def test_basic_se_tax(self):
        # 100k profit -> 92,350 net earnings -> 15.3%
        self.assertAlmostEqual(self_employment_tax(100_000), 92_350 * 0.153)

    def test_ss_cap_applies(self):
        # Above the wage base, only Medicare keeps accruing.
        profit = 300_000
        net = profit * 0.9235
        expected = 176_100 * 0.124 + net * 0.029
        self.assertAlmostEqual(self_employment_tax(profit), expected)


class EstimateTests(unittest.TestCase):
    def make_ledger(self):
        return Ledger(
            year=2026,
            filing_status="single",
            incomes=[
                Income(amount=80_000, source="MySaaS", type="saas", date="2026-03-01"),
                Income(amount=20_000, source="DayJob", type="w2", date="2026-02-01"),
            ],
            expenses=[Expense(amount=10_000, description="hosting", date="2026-03-15")],
            payments=[Payment(amount=5_000, date="2026-04-10")],
        )

    def test_estimate_pipeline(self):
        est = estimate(self.make_ledger())
        self.assertEqual(est["se_gross"], 80_000)
        self.assertEqual(est["se_profit"], 70_000)
        self.assertEqual(est["other_income"], 20_000)
        se_tax = self_employment_tax(70_000)
        self.assertAlmostEqual(est["se_tax"], se_tax)
        agi = 70_000 + 20_000 - se_tax / 2
        self.assertAlmostEqual(est["agi"], agi)
        self.assertAlmostEqual(est["taxable_income"], agi - 15_000)
        self.assertAlmostEqual(
            est["total_tax"], est["income_tax"] + est["se_tax"]
        )
        self.assertAlmostEqual(est["balance_due"], est["total_tax"] - 5_000)

    def test_expenses_cannot_create_negative_profit(self):
        ledger = Ledger(
            year=2026,
            incomes=[Income(amount=1_000, source="MySaaS", type="saas", date="2026-01-01")],
            expenses=[Expense(amount=9_999, description="big spend", date="2026-01-02")],
        )
        est = estimate(ledger)
        self.assertEqual(est["se_profit"], 0.0)
        self.assertEqual(est["se_tax"], 0.0)


if __name__ == "__main__":
    unittest.main()
