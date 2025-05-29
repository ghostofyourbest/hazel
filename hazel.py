import pandas as pd
import pyarrow as pa

frequency_dict = {
    "monthly": 1,
    "quarterly": 4,
    "semi-annually": 5,
    "annually": 12
}

def fsolve(func, x0, xtol=1e-5, max_iter=100):
    x = x0
    for i in range(max_iter):
        f_val = func(x)
        h = 1e-5 
        f_prime = (func(x + h) - func(x)) / h
        if f_prime == 0:
            raise ValueError("fail")
        x_new = x - f_val / f_prime
        if abs(x_new - x) < xtol:
            return x_new
        x = x_new
    
class loanSchedule():
    def __init__(self, amount, rate, start_date, payments, residual=0.00, payment_date=None, frequency='monthly',start_fee=0.00, end_fee=0.00):
        
        self.amount = amount
        self.payments = payments
        self.residual = residual
        self.start_fee = start_fee
        self.end_fee = end_fee
        self.frequency = frequency_dict[frequency]
        # convert rate to effective rate based on frequency
        self.rate = rate
        self.start_date = pd.to_datetime(start_date)
        # if no payment_date is provided, default to the day of the month of start_date
        if payment_date == None:
            self.payment_date = self.start_date.day
        else:
            self.payment_date = min(28, payment_date)  # ensure payment_date is not greater than 28 to avoid invalid dates in February

        # generate the payment schedule    
        self.payment_schedule = self.generate_schedule()
        print(self.payment_schedule)
        # determine the monthly payment numerically
        self.monthly_payment = fsolve(self.calculate_payment, x0=self.amount / self.payments)
        # create the output dataframe
        self.df = pd.DataFrame({
            'payment_date': self.payment_schedule["date"],
            'days_in_period': self.payment_schedule["days_in_period"].shift(1),
            'payment_amount': self.total_payments,
            'interest_payment': self.interest_payments,
            'principal_payment': self.principal_payments,
            'opening_balance': self.opening_balance,
            'closing_balance': self.closing_balance,
            'fees_outstanding': self.fees_outstanding
        }).round(2)
    
    def generate_schedule(self):
        # Find the first payment date after start_date with the correct day
        if self.start_date.day > self.payment_date:
            # Move to next month
            self.first_payment_date = (self.start_date + pd.offsets.MonthBegin(1)).replace(day=self.payment_date)
        elif self.start_date.day < self.payment_date:
            # Set to this month, payment_date if valid
            try:
                self.first_payment_date = self.start_date.replace(day=self.payment_date)
            except ValueError:
                # If day is invalid (e.g., Feb 30), move to next month
                self.first_payment_date = (self.start_date + pd.offsets.MonthBegin(1)).replace(day=self.payment_date)
        # else: already on the correct day

        # Generate payment dates
        payment_dates = pd.date_range(
            start=self.first_payment_date,
            periods=self.payments,
            freq=pd.DateOffset(months=self.frequency)
        )

        # add a first row being the start date before the first payment date
        dates = pd.DataFrame(pd.concat([pd.Series(self.start_date), pd.Series(payment_dates)]),columns=["date"])
        dates.reset_index(drop=True, inplace=True)
        dates["days_in_period"] = (dates["date"].shift(-1)-dates["date"]).dt.days
        return dates
    
    def calculate_payment(self, payment):
        self.interest_payments = [0]
        self.principal_payments = [0]
        self.fees_outstanding = [self.start_fee+self.end_fee]
        self.total_payments = [0]
        self.opening_balance = [0]
        self.closing_balance = [self.amount]
        
        for date in self.payment_schedule.index:
            if date == 0:
                pass
            elif date == 1:
                self.opening_balance.append(self.closing_balance[date-1])
                interest = self.opening_balance[date] * ((1+self.rate)**(self.payment_schedule.at[date-1,"days_in_period"]/365.25)-1)
                principal = payment - interest
                self.interest_payments.append(interest)
                self.principal_payments.append(principal)
                self.total_payments.append(payment+self.start_fee)
                self.fees_outstanding.append(self.fees_outstanding[date-1] - self.start_fee)
                self.closing_balance.append(self.opening_balance[date] - principal)

            elif date == (len(self.payment_schedule)-1):
                self.opening_balance.append(self.closing_balance[date-1])
                interest = self.opening_balance[date] * ((1+self.rate)**(self.payment_schedule.at[date-1,"days_in_period"]/365.25)-1)
                principal = payment - interest
                self.interest_payments.append(interest)
                self.principal_payments.append(principal)
                self.total_payments.append(payment+self.end_fee)
                self.fees_outstanding.append(self.fees_outstanding[date-1] - self.end_fee)
                self.closing_balance.append(self.opening_balance[date] - principal)

            else:
                self.opening_balance.append(self.closing_balance[date-1])
                interest = self.opening_balance[date] * ((1+self.rate)**(self.payment_schedule.at[date-1,"days_in_period"]/365.25)-1)
                principal = payment - interest
                self.interest_payments.append(interest)
                self.principal_payments.append(principal)
                self.total_payments.append(payment)
                self.fees_outstanding.append(self.fees_outstanding[date-1])
                self.closing_balance.append(self.opening_balance[date] - principal)

        return (self.closing_balance[len(self.payment_schedule)-1]-self.residual)
    
if __name__ == "__main__":
    # Example usage
    test = loanSchedule(
        amount=1000,
        rate=0.05,
        start_date='2023-01-01',
        payments=12,
        payment_date=31,
        frequency='monthly',
        residual=0.00,
        start_fee=100.00,
        end_fee=200.00
        )
    
print(test.df)