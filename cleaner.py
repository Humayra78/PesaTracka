import pandas as pd

class DataCleaner:
    def __init__(self, file_path):
        self.file_path = file_path

    def clean_data(self):
        # 1. Load the data, skipping the first 4 rows of bank metadata
        df = pd.read_csv(self.file_path, skiprows=4)

        # 2. Rename columns to match what the rest of the app expects
        df = df.rename(columns={
            'TRANSACTION DATE': 'Date',
            'TRANS AMOUNT': 'Amount (KES)',
            'PAYER NAME': 'Transaction Details'
        })

        # 3. Strip any accidental whitespace from column names
        df.columns = [c.strip() for c in df.columns] 
        
        # 4. Convert Date to a format Python understands (YYYY-MM-DD)
        df['Date'] = pd.to_datetime(df['Date'])
        
        # 5. Filter for collections/earnings only (positive amounts)
        earnings_df = df[df['Amount (KES)'] > 0].copy()
        
        # 6. Sort by date chronologically
        earnings_df = earnings_df.sort_values(by='Date')
        
        return earnings_df

# Test engine execution
if __name__ == "__main__":
    cleaner = DataCleaner('statement.csv')
    data = cleaner.clean_data()
    
    total_income = data['Amount (KES)'].sum()
    
    print("--- PesaTracka Backend Test ---")
    print(f"Total Earnings Found: KES {total_income:,.2f}")
    print("\nRecent Transactions:")
    print(data[['Date', 'Transaction Details', 'Amount (KES)']].tail())