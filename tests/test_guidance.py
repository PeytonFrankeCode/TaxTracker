import unittest

from taxtracker.guidance import explain, product_taxable_in
from taxtracker.models import Income, Ledger, Sale


def section(sections, title):
    return "\n".join(dict(sections)[title])


class TaxabilityTests(unittest.TestCase):
    def test_saas_split_by_state(self):
        self.assertTrue(product_taxable_in("saas", "TX"))
        self.assertFalse(product_taxable_in("saas", "CA"))

    def test_no_sales_tax_state_never_taxable(self):
        self.assertFalse(product_taxable_in("physical", "OR"))

    def test_physical_taxable_in_sales_tax_states(self):
        self.assertTrue(product_taxable_in("physical", "CA"))

    def test_unknown_without_setup(self):
        self.assertIsNone(product_taxable_in("", "CA"))
        self.assertIsNone(product_taxable_in("saas", ""))


class ExplainTests(unittest.TestCase):
    def make_ledger(self, **kwargs):
        defaults = dict(
            year=2026, state="CA", product_type="saas", sales_mode="online",
            incomes=[Income(amount=45_000, source="MySaaS", type="saas",
                            date="2026-03-01")],
        )
        defaults.update(kwargs)
        return Ledger(**defaults)

    def test_owe_section_uses_recorded_numbers(self):
        text = section(explain(self.make_ledger()), "What you owe right now")
        self.assertIn("$45,000.00 of income", text)
        self.assertIn("Self-employment tax", text)
        self.assertIn("CA state income tax", text)

    def test_empty_ledger_prompts_for_income(self):
        ledger = self.make_ledger(incomes=[])
        text = section(explain(ledger), "What you owe right now")
        self.assertIn("No income recorded yet", text)

    def test_federal_filings_for_self_employed(self):
        text = section(explain(self.make_ledger()), "What to file: federal")
        self.assertIn("Schedule C", text)
        self.assertIn("Schedule SE", text)
        self.assertIn("1040-ES", text)
        self.assertIn("April 15, 2027", text)

    def test_w2_only_skips_schedule_c(self):
        ledger = self.make_ledger(incomes=[
            Income(amount=60_000, source="DayJob", type="w2", date="2026-02-01")])
        text = section(explain(ledger), "What to file: federal")
        self.assertNotIn("Schedule C", text)
        self.assertIn("withholding", text)

    def test_no_income_tax_state(self):
        ledger = self.make_ledger(state="TX")
        text = section(explain(ledger), "What to file: state income tax")
        self.assertIn("no state income tax", text)

    def test_sales_tax_home_state_saas_exempt_in_ca(self):
        text = section(explain(self.make_ledger()),
                       "Sales tax: where it applies to you")
        self.assertIn("does NOT tax SaaS", text)

    def test_nexus_state_that_taxes_product_warns(self):
        ledger = self.make_ledger(sales=[
            Sale(amount=95_000, state="PA", date="2026-04-01")])
        text = section(explain(ledger), "Sales tax: where it applies to you")
        self.assertIn("PA", text)
        self.assertIn("Talk to a tax advisor", text)

    def test_nexus_state_that_does_not_tax_product(self):
        # CA taxes physical but not SaaS; crossing CA nexus with SaaS = relief note.
        ledger = self.make_ledger(sales=[
            Sale(amount=600_000, state="CA", date="2026-04-01")])
        text = section(explain(ledger), "Sales tax: where it applies to you")
        self.assertIn("does not tax", text)

    def test_in_person_mode_keeps_it_local(self):
        ledger = self.make_ledger(sales_mode="in-person")
        text = section(explain(ledger), "Sales tax: where it applies to you")
        self.assertIn("in person", text)

    def test_unset_product_prompts_setup(self):
        ledger = self.make_ledger(product_type="")
        text = section(explain(ledger), "Sales tax: where it applies to you")
        self.assertIn("Setup", text)


if __name__ == "__main__":
    unittest.main()
