import pandas as pd
from datetime import datetime

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
            'TRANSACTION TIME': 'Time',
            'TRANS AMOUNT': 'Amount (KES)',
            'PAYER NAME': 'Transaction Details'
        })

        # 4. Remove empty structural filler rows that contain no date or amount
        df = df.dropna(subset=['Date', 'Amount (KES)'])
        
        # 5. Extract the explicit hour data for hourly charts before normalizing the primary Date index
        if 'Time' in df.columns:
            df['Time'] = df['Time'].fillna('00:00:00').astype(str).str.strip()
            df['Hour'] = pd.to_datetime(df['Time'], format='%H:%M:%S', errors='coerce').dt.hour.fillna(0).astype(int)
        else:
            df['Hour'] = 0

        # 6. Parse the primary Date column safely handling the mixed formats explicitly
        # First, try parsing with explicit day-first formatting (%d/%m/%Y)
        df['Date'] = df['Date'].astype(str).str.strip()
        day_first_parsed = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
        
        # Second, use fallback 'mixed' layout for the rows that are formatted like YYYY-MM-DD
        fallback_parsed = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
        
        # Combine them, prioritizing the strict day-first format
        df['Date'] = day_first_parsed.fillna(fallback_parsed)
        
        # 7. Filter for collections/earnings only (positive amounts)
        earnings_df = df[df['Amount (KES)'] > 0].copy()
        
        # 8. Sort by date chronologically
        earnings_df = earnings_df.sort_values(by='Date')
        
        return earnings_df