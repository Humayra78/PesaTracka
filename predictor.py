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
            # For small statement windows, fallback to a flat projection of the current sum
            return float(daily_revenue['Amount (KES)'].sum())
            
        # 3. Construct chronological variable spaces for standard linear prediction
        X = np.array(range(len(daily_revenue))).reshape(-1, 1)
        y = daily_revenue['Amount (KES)'].values
        
        # 4. Train the regression model pipeline
        self.model.fit(X, y)
        
        # 5. Output the projected estimate vector for the following sequential day index
        next_day_index = np.array([[len(daily_revenue)]])
        prediction = self.model.predict(next_day_index)
        
        return float(prediction[0])