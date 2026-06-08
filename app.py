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
    return render_template('index.html', user_name=session.get('user_name'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.form
        result = AuthenticationHandler.login_user(data['email'], data['password'])
        if result['status'] == 'success':
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
            display_name=data['name']
        )
        if result['status'] == 'success':
            return redirect(url_for('login_page', msg="Account created. Check email for verification link."))
        return render_template('auth.html', error=result['message'], mode='signup')
    return render_template('auth.html', mode='signup')

@app.route('/logout')
def logout():
    AuthenticationHandler.logout_user()
    return redirect(url_for('login_page'))

# Protect your data API
@app.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard_data():
    try:
        cleaner = DataCleaner('statement.csv')
        df = cleaner.clean_data()
        total_earnings = float(df['Amount (KES)'].sum())
        transaction_count = len(df)
        model_engine = Predictor()
        prediction = float(model_engine.forecast_next_period(df))
        
        return jsonify({
            "status": "success",
            "total_earnings": total_earnings,
            "transaction_count": transaction_count,
            "next_month_forecast": round(prediction, 2)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True)