import os
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from functools import wraps
from cleaner import DataCleaner
from predictor import Predictor
from auth_handler import AuthenticationHandler

app = Flask(__name__)
app.secret_key = 'pesatracka_super_secret_session_encryption_key'  # Required for sessions

# Decorator to protect backend routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def home():
    # Fetch the name stored during login, defaulting to "User" if it's missing
    first_name = session.get('user_name', 'User')
    return render_template('index.html', name=first_name)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.form
        result = AuthenticationHandler.login_user(data['email'], data['password'])
        if result['status'] == 'success':
            # After a clean validation check, grab user details to show the first name
            from firebase_admin import auth
            user = auth.get_user_by_email(data['email'])
            
            # Extract just the first word from full name string
            first_name = user.display_name.split()[0] if user.display_name else "User"
            session['user_name'] = first_name
            
            return redirect(url_for('home'))
        return render_template('auth.html', error=result['message'], mode='login')
    return render_template('auth.html', mode='login')

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        data = request.form
        result = AuthenticationHandler.register_user(
            email=data['email'],
            password=data['password'],
            phone_number=data['phone'],
            business_name=data['business_name'],
            first_name=data['first_name'],
            last_name=data['last_name']
        )
        if result['status'] == 'success':
            return redirect(url_for('login_page', msg="Account created successfully. Please log in."))
        return render_template('auth.html', error=result['message'], mode='signup')
    return render_template('auth.html', mode='signup')

@app.route('/logout')
def logout():
    AuthenticationHandler.logout_user()
    return redirect(url_for('login_page'))


# --- NEW DYNAMIC EXTRACT-TRANSFORM-LOAD (ETL) UPLOAD ROUTE ---
# This completely replaces the old hardcoded /api/dashboard endpoint
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_statement():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file chunk found in payload."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected."}), 400

    if file and file.filename.endswith('.csv'):
        temp_path = os.path.join(os.getcwd(), "temp_upload.csv")
        try:
            # Save the uploaded file temporarily to the server workspace
            file.save(temp_path)
            
            # 1. EXTRACT & TRANSFORM: Pipe file into your DataCleaner
            cleaner = DataCleaner(temp_path)
            df = cleaner.clean_data()
            
            if df.empty:
                return jsonify({"status": "error", "message": "No valid collection earnings records found in this statement layout."}), 400
                
            # 2. ANALYTICS: Calculate required metric boundaries
            total_earnings = float(df['Amount (KES)'].sum())
            transaction_count = len(df)
            
            # Calculate dynamic daily averages based on unique dates in the statement
            unique_days = df['Date'].dt.date.nunique()
            avg_daily_income = float(total_earnings / unique_days) if unique_days > 0 else 0.0
            
            # Identify the peak transaction day name
            df['DayName'] = df['Date'].dt.day_name()
            peak_day = str(df.groupby('DayName')['Amount (KES)'].sum().idxmax())

            # 3. PREDICT: Process time-series forecasting calculations
            model_engine = Predictor()
            prediction = float(model_engine.forecast_next_period(df))
            
            # 4. LOAD VISUALIZATION: Format weekday distributions for Chart.js
            weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_grouping = df.groupby('DayName')['Amount (KES)'].sum().reindex(weekday_order, fill_value=0)
            
            chart_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            chart_data = [float(val) for val in day_grouping.values]

            # Clean up the temporary workspace file immediately
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # Return structural payload response directly back to the frontend dashboard script
            return jsonify({
                "status": "success",
                "total_earnings": total_earnings,
                "transaction_count": transaction_count,
                "avg_daily": round(avg_daily_income, 2),
                "peak_day": peak_day,
                "next_month_forecast": round(prediction, 2),
                "chart_labels": chart_labels,
                "chart_data": chart_data
            })
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({"status": "error", "message": f"Processing runtime failure: {str(e)}"}), 500

    return jsonify({"status": "error", "message": "File format type must be extension .csv"}), 400


if __name__ == '__main__':
    app.run(debug=True)