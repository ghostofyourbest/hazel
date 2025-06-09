import unittest
from hazel import loanSchedule

# functional_tets.py

class TestLoanScheduleFunctional(unittest.TestCase):
    def test_calculate_payment_valid(self):
        sched = loanSchedule(
            amount=1000,
            rate=0.05,
            start_date='2023-01-01',
            payments=12,
            payment_date=15,
            frequency='monthly',
            residual=0.0,
            start_fee=0.0,
            end_fee=0.0
        )
        # Should be close to zero if payment is correct
        result = sched.calculate_payment(sched.monthly_payment)
        self.assertAlmostEqual(result, 0, places=2)

    def test_calculate_payment_negative_amount(self):
        with self.assertRaises(Exception):
            loanSchedule(
                amount=-1000,
                rate=0.05,
                start_date='2023-01-01',
                payments=12,
                payment_date=15,
                frequency='monthly'
            )

    def test_calculate_payment_negative_rate(self):
        with self.assertRaises(Exception):
            loanSchedule(
                amount=1000,
                rate=-0.05,
                start_date='2023-01-01',
                payments=12,
                payment_date=15,
                frequency='monthly'
            )

    def test_calculate_payment_zero_payments(self):
        with self.assertRaises(Exception):
            loanSchedule(
                amount=1000,
                rate=0.05,
                start_date='2023-01-01',
                payments=0,
                payment_date=15,
                frequency='monthly'
            )

    def test_calculate_payment_large_residual(self):
        sched = loanSchedule(
            amount=1000,
            rate=0.05,
            start_date='2023-01-01',
            payments=12,
            payment_date=15,
            frequency='monthly',
            residual=2000.0
        )
        result = sched.calculate_payment(sched.monthly_payment)
        self.assertLess(result, 0)

if __name__ == "__main__":
    unittest.main()