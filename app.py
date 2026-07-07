import os
import uuid
import json
from datetime import datetime, timedelta
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
            from firebase_admin import auth
            user = auth.get_user_by_email(data['email'])
            
            # Extract names and secure key tags
            first_name = user.display_name.split()[0] if user.display_name else "User"
            session['user_name'] = first_name
            session['user_id'] = user.uid  # Capture unique identifier securely here
            
            # Clear previous active workspace targets cleanly to load fresh on login window
            session.pop('active_statement_id', None)
            
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

# Ensure an uploads directory exists to store statement history securely
UPLOAD_DIR = os.path.join(os.getcwd(), "saved_statements")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Persistent JSON storage file path configuration
HISTORY_DB_PATH = os.path.join(os.getcwd(), "user_histories.json")

def load_persistent_histories():
    """Helper to read database records from disk safely."""
    if not os.path.exists(HISTORY_DB_PATH):
        return {}
    try:
        with open(HISTORY_DB_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_persistent_history(user_id, statement_list):
    """Helper to write database records back onto the file system."""
    db = load_persistent_histories()
    db[str(user_id)] = statement_list
    try:
        with open(HISTORY_DB_PATH, 'w') as f:
            json.dump(db, f, indent=4)
    except Exception as e:
        print(f"Failed to persist historical directory profile logs: {e}")

# --- UPDATED API UPLOAD ROUTE WITH ZERO-SLATE ON FRESH LOGIN ---
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_statement():
    user_id = session.get('user_id')
    if not user_id:
        user_id = session.get('user_name', 'default_user')

    all_histories = load_persistent_histories()
    user_history_log = all_histories.get(str(user_id), [])

    history_id = request.form.get('history_id')
    
    if history_id:
        matched = next((item for item in user_history_log if item['id'] == history_id), None)
        if matched and os.path.exists(matched['file_path']):
            target_path = matched['file_path']
            session['active_statement_id'] = history_id
        else:
            return jsonify({"status": "error", "message": "Selected statement file could not be found."}), 404
            
    elif 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        if not file.filename.endswith('.csv'):
            return jsonify({"status": "error", "message": "File format type must be extension .csv"}), 400
            
        unique_id = str(uuid.uuid4())
        safe_filename = f"{unique_id}_{file.filename}"
        target_path = os.path.join(UPLOAD_DIR, safe_filename)
        file.save(target_path)
        
        now = datetime.now()
        new_record = {
            "id": unique_id,
            "filename": file.filename,
            "date_uploaded": now.strftime('%d %b %Y'),
            "time_uploaded": now.strftime('%H:%M:%S'),
            "file_path": target_path
        }
        
        user_history_log.append(new_record)
        save_persistent_history(user_id, user_history_log)
        session['active_statement_id'] = unique_id
        
    else:
        # Check if there is an active statement in the current session
        active_id = session.get('active_statement_id')
        matched = None
        if active_id:
            matched = next((item for item in user_history_log if item['id'] == active_id), None)
            
        if matched and os.path.exists(matched['file_path']):
            target_path = matched['file_path']
        else:
            # MODIFIED: When logging in freshly, active_id is empty. 
            # Return a blank zero slate for the dashboard, but keep sending the user's history log!
            return jsonify({
                "status": "success",
                "total_earnings": 0.0,
                "transaction_count": 0,
                "avg_daily": 0.0,
                "peak_day": "--",
                "next_month_forecast": 0.0,
                "years_summary": "No active data metrics loaded.",
                "anchor_date": "No statement processed yet",
                "history_log": user_history_log,  # Keeps history visible
                "active_id": None,
                "charts": {
                    "weekly": { "labels": ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], "data": [0]*7, "mean": 0, "range": "No Data" },
                    "monthly": { "labels": ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], "data": [0]*12, "mean": 0, "range": "No Data" },
                    "yearly": { "labels": [], "data": [], "mean": 0 }
                }
            })

    try:
        # 1. EXTRACT & TRANSFORM
        cleaner = DataCleaner(target_path)
        df = cleaner.clean_data()
        
        if df.empty:
            return jsonify({"status": "error", "message": "No valid collection earnings records found."}), 400
            
        # Navigation Offsets from Frontend
        week_offset = int(request.form.get('week_offset', 0))
        year_offset = int(request.form.get('year_offset', 0))
        
        base_anchor = df['Date'].max()
        adjusted_week_anchor = base_anchor + timedelta(weeks=week_offset)
        adjusted_year_num = base_anchor.year + year_offset
        
        # 2. GLOBAL METRICS
        total_earnings = float(df['Amount (KES)'].sum())
        transaction_count = len(df)
        included_years = sorted(df['Date'].dt.year.unique().tolist())
        years_summary = f"Includes data from: {', '.join(map(str, included_years))}"
        
        unique_days = df['Date'].dt.date.nunique()
        avg_daily_income = float(total_earnings / unique_days) if unique_days > 0 else 0.0
        
        df['DayName'] = df['Date'].dt.day_name()
        peak_day = str(df.groupby('DayName')['Amount (KES)'].sum().idxmax())

        # 3. PREDICT
        model_engine = Predictor()
        prediction = float(model_engine.forecast_next_period(df))
        
        # 4. LOAD VISUALIZATION AGGREGATIONS
        # A. WEEKLY VIEW
        start_of_week = adjusted_week_anchor - timedelta(days=adjusted_week_anchor.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        df_week = df[(df['Date'] >= start_of_week) & (df['Date'] <= end_of_week)]
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        week_grouping = df_week.groupby('DayName')['Amount (KES)'].sum().reindex(weekday_order, fill_value=0)
        
        chart_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        chart_data = [float(val) for val in week_grouping.values]
        weekly_mean = float(week_grouping.mean())
        week_range_str = f"{start_of_week.strftime('%d %b')} - {end_of_week.strftime('%d %b %Y')}"

        # B. MONTHLY VIEW
        df_year = df[df['Date'].dt.year == adjusted_year_num]
        df_year = df_year.copy()
        df_year['MonthNum'] = df_year['Date'].dt.month
        month_order = list(range(1, 13))
        month_grouping = df_year.groupby('MonthNum')['Amount (KES)'].sum().reindex(month_order, fill_value=0)
        
        monthly_data = [float(val) for val in month_grouping.values]
        monthly_mean = float(month_grouping.mean())
        monthly_year_str = f"Year: {adjusted_year_num}"

        # C. YEARLY VIEW
        year_grouping = df.groupby(df['Date'].dt.year)['Amount (KES)'].sum()
        yearly_labels = [str(y) for y in sorted(year_grouping.index)]
        yearly_data = [float(year_grouping[int(y)]) for y in yearly_labels]
        yearly_mean = float(year_grouping.mean()) if len(yearly_labels) > 0 else 0.0

        return jsonify({
            "status": "success",
            "total_earnings": total_earnings,
            "transaction_count": transaction_count,
            "avg_daily": round(avg_daily_income, 2),
            "peak_day": peak_day,
            "next_month_forecast": round(prediction, 2),
            "years_summary": years_summary,
            "anchor_date": base_anchor.strftime('%d %b %Y at %H:%M'),
            "history_log": user_history_log,
            "active_id": session.get('active_statement_id'),
            "charts": {
                "weekly": { "labels": chart_labels, "data": chart_data, "mean": round(weekly_mean, 2), "range": week_range_str },
                "monthly": { "labels": ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct – Dec'], "data": monthly_data, "mean": round(monthly_mean, 2), "range": monthly_year_str },
                "yearly": { "labels": yearly_labels, "data": yearly_data, "mean": round(yearly_mean, 2) }
            }
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Processing runtime failure: {str(e)}"}), 500

    return jsonify({"status": "error", "message": "File format type must be extension .csv"}), 400

@app.route('/api/delete/<string:history_id>', methods=['POST'])
@login_required
def delete_statement(history_id):
    user_id = session.get('user_id')
    if not user_id:
        user_id = session.get('user_name', 'default_user')

    all_histories = load_persistent_histories()
    user_history_log = all_histories.get(str(user_id), [])

    # Find the targeted statement record
    matched_index = next((i for i, item in enumerate(user_history_log) if item['id'] == history_id), None)
    
    if matched_index is None:
        return jsonify({"status": "error", "message": "Statement not found in history archive."}), 404

    matched_item = user_history_log[matched_index]
    
    # 1. Delete physical file from the storage directory safely if it exists
    if os.path.exists(matched_item['file_path']):
        try:
            os.remove(matched_item['file_path'])
        except Exception as e:
            print(f"Failed to delete structural file asset: {e}")

    # 2. Drop the element from the tracking array log registry
    user_history_log.pop(matched_index)
    save_persistent_history(user_id, user_history_log)

    # 3. If the deleted item was currently active in this session, clear the active key template
    if session.get('active_statement_id') == history_id:
        session.pop('active_statement_id', None)

    return jsonify({"status": "success", "message": "Statement removed cleanly."})

if __name__ == '__main__':
    app.run(debug=True)