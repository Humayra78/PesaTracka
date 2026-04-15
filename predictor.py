from sklearn.linear_model import LinearRegression
import numpy as np
import pandas as pd

class Predictor:
    def __init__(self):
        self.model = LinearRegression()

    def forecast_next_period(self, cleaned_data):
        # 1. Group earnings by date to get a daily time-series
        daily_revenue = cleaned_data.groupby('Date')['Amount (KES)'].sum().reset_index()
        
        # 2. Prepare the numbers for the AI model
        # X is the day number (0, 1, 2...), y is the money earned
        X = np.array(range(len(daily_revenue))).reshape(-1, 1)
        y = daily_revenue['Amount (KES)'].values
        
        # 3. Train the model (Linear Regression)
        self.model.fit(X, y)
        
        # 4. Predict the "Next" day
        next_day_index = np.array([[len(daily_revenue)]])
        prediction = self.model.predict(next_day_index)
        
        return prediction[0]

# --- Let's test it by connecting the Cleaner to the Predictor ---
if __name__ == "__main__":
    from cleaner import DataCleaner
    
    # Get the cleaned data
    cleaner = DataCleaner('statement.csv')
    cleaned_df = cleaner.clean_data()
    
    # Run the prediction
    model_engine = Predictor()
    result = model_engine.forecast_next_period(cleaned_df)
    
    print("--- PesaTracka Prediction Test ---")
    print(f"Based on historical trends, your next projected daily earning is: KES {result:.2f}")