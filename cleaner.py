import pandas as pd

class DataCleaner:
    def __init__(self, file_path):
        self.file_path = file_path

    def clean_data(self):
        # 1. Load the data
        df = pd.read_csv(self.file_path)

        # 2. Convert Date to a format Python understands
        # We use dayfirst=True because your CSV is DD/MM/YYYY
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
        
        # 3. Filter for 'Earnings' only
        # In your file, deposits/received money are positive numbers.
        earnings_df = df[df['Amount (KES)'] > 0].copy()
        
        # 4. Sort by date just in case the statement is out of order
        earnings_df = earnings_df.sort_values(by='Date')
        
        return earnings_df

# Let's test it and calculate your total income
if __name__ == "__main__":
    cleaner = DataCleaner('statement.csv')
    data = cleaner.clean_data()
    
    total_income = data['Amount (KES)'].sum()
    
    print("--- PesaTracka Backend Test ---")
    print(f"Total Earnings Found: KES {total_income:,.2f}")
    print("\nRecent Transactions:")
    print(data[['Date', 'Transaction Details', 'Amount (KES)']].tail())