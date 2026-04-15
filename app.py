from flask import Flask, jsonify, render_template
from cleaner import DataCleaner
from predictor import Predictor

app = Flask(__name__)

@app.route('/api/dashboard', methods=['GET'])
def home():
    return render_template('index.html')
def get_dashboard_data():
    try:
        # 1. Clean the data
        cleaner = DataCleaner('statement.csv')
        df = cleaner.clean_data()
        
        # 2. Get Analytics
        total_earnings = float(df['Amount (KES)'].sum())
        transaction_count = len(df)
        
        # 3. Get Prediction
        model_engine = Predictor()
        prediction = float(model_engine.forecast_next_period(df))
        
        # 4. Package it all up for the Frontend
        return jsonify({
            "status": "success",
            "total_earnings": total_earnings,
            "transaction_count": transaction_count,
            "next_month_forecast": round(prediction, 2)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    print("PesaTracka API is starting...")
    app.run(debug=True)