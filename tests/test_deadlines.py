import unittest
from datetime import date

from taxtracker.deadlines import next_deadline, quarterly_deadlines, upcoming_deadlines


class DeadlineTests(unittest.TestCase):
    def test_four_deadlines_q4_in_next_year(self):
        deadlines = quarterly_deadlines(2026)
        self.assertEqual(len(deadlines), 4)
        self.assertEqual(deadlines[0], ("Q1", date(2026, 4, 15)))
        self.assertEqual(deadlines[3], ("Q4", date(2027, 1, 15)))

    def test_upcoming_filters_past(self):
        upcoming = upcoming_deadlines(2026, today=date(2026, 6, 10))
        self.assertEqual([q for q, _ in upcoming], ["Q2", "Q3", "Q4"])

    def test_next_deadline(self):
        self.assertEqual(next_deadline(2026, today=date(2026, 6, 10)),
                         ("Q2", date(2026, 6, 15)))
        self.assertIsNone(next_deadline(2026, today=date(2027, 2, 1)))


if __name__ == "__main__":
    unittest.main()
