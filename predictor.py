from sklearn.linear_model import LinearRegression
import numpy as np
import pandas as pd

class Predictor:
    def __init__(self):
        self.model = LinearRegression()

    def forecast_next_period(self, cleaned_data):
        # 1. Group transaction values by structured Date vector
        daily_revenue = cleaned_data.groupby('Date')['Amount (KES)'].sum().reset_index()
        
        # 2. Check if the statement spans multiple distinct dates
        if len(daily_revenue) < 2:
            # Fallback for a single day: extrapolate that daily value out to a 30-day month
            return float(daily_revenue['Amount (KES)'].sum() * 30)
            
        # 3. Construct chronological variable spaces for standard linear prediction
        X = np.array(range(len(daily_revenue))).reshape(-1, 1)
        y = daily_revenue['Amount (KES)'].values
        
        # 4. Train the regression model pipeline
        self.model.fit(X, y)
        
        # 5. Predict daily revenue trends for the next 30 sequential days
        next_day_indexes = np.array(range(len(daily_revenue), len(daily_revenue) + 30)).reshape(-1, 1)
        predicted_daily_values = self.model.predict(next_day_indexes)
        
        # 6. Sum up all 30 predicted days to get the true total for next month
        total_monthly_forecast = float(np.sum(predicted_daily_values))
        
        # Guard clause: ensure the model doesn't project a negative value during a downward trend
        return max(0.0, total_monthly_forecast) 