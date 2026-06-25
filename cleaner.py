import pandas as pd

class DataCleaner:
    def __init__(self, file_path):
        self.file_path = file_path

    def clean_data(self):
        # 1. Load the data, skipping the first 4 rows of bank metadata
        df = pd.read_csv(self.file_path, skiprows=4)

        # 2. Strip any accidental whitespace from column headers
        df.columns = [c.strip() for c in df.columns]

        # 3. Rename columns to match what the rest of the application expects
        df = df.rename(columns={
            'TRANSACTION DATE': 'Date',
            'TRANS AMOUNT': 'Amount (KES)',
            'PAYER NAME': 'Transaction Details'
        })

        # 4. Remove empty structural filler rows that contain no date or amount
        df = df.dropna(subset=['Date', 'Amount (KES)'])
        
        # 5. Tell the parser to expect mixed date formats, prioritizing day-first layouts
        df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True)
        
        # 6. Filter for collections/earnings only (positive amounts)
        earnings_df = df[df['Amount (KES)'] > 0].copy()
        
        # 7. Sort by date chronologically
        earnings_df = earnings_df.sort_values(by='Date')
        
        return earnings_df

if __name__ == "__main__":
    cleaner = DataCleaner('statement_extended.csv')
    data = cleaner.clean_data()
    
    total_income = data['Amount (KES)'].sum()
    
    print("--- PesaTracka Backend Test ---")
    print(f"Total Earnings Found: KES {total_income:,.2f}")
    print("\nRecent Transactions:")
    print(data[['Date', 'Transaction Details', 'Amount (KES)']].tail())