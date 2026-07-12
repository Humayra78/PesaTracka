import pandas as pd
from datetime import datetime

class DataCleaner:
    def __init__(self, file_stream):
        # Now handles an in-memory stream directly
        self.file_stream = file_stream

    def clean_data(self):
        # 1. Load the data from the memory stream
        df = pd.read_csv(self.file_stream, skiprows=4)

        # 2. Strip any accidental whitespace from column headers
        df.columns = [c.strip() for c in df.columns]

        # 3. Rename columns
        df = df.rename(columns={
            'TRANSACTION DATE': 'Date',
            'TRANSACTION TIME': 'Time',
            'TRANS AMOUNT': 'Amount (KES)',
            'PAYER NAME': 'Transaction Details'
        })

        # 4. Remove empty structural filler rows
        df = df.dropna(subset=['Date', 'Amount (KES)'])
        
        # 5. Extract the explicit hour data
        if 'Time' in df.columns:
            df['Time'] = df['Time'].fillna('00:00:00').astype(str).str.strip()
            df['Hour'] = pd.to_datetime(df['Time'], format='%H:%M:%S', errors='coerce').dt.hour.fillna(0).astype(int)
        else:
            df['Hour'] = 0

        # 6. Parse the primary Date column safely handling the mixed formats explicitly
        df['Date'] = df['Date'].astype(str).str.strip()
        day_first_parsed = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
        fallback_parsed = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
        df['Date'] = day_first_parsed.fillna(fallback_parsed)
        
        # 7. Filter for collections/earnings only
        earnings_df = df[df['Amount (KES)'] > 0].copy()
        
        # 8. Sort chronologically
        earnings_df = earnings_df.sort_values(by='Date')
        
        return earnings_df