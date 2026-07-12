import os
import uuid
import json
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from functools import wraps
import pandas as pd
from cleaner import DataCleaner
from predictor import Predictor
from auth_handler import AuthenticationHandler

app = Flask(__name__)
app.secret_key = 'pesatracka_super_secret_session_encryption_key'

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
            
            first_name = user.display_name.split()[0] if user.display_name else "User"
            session['user_name'] = first_name
            session['user_id'] = user.uid
            
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

UPLOAD_DIR = os.path.join(os.getcwd(), "saved_statements")
os.makedirs(UPLOAD_DIR, exist_ok=True)

HISTORY_DB_PATH = os.path.join(os.getcwd(), "user_histories.json")

def load_persistent_histories():
    if not os.path.exists(HISTORY_DB_PATH):
        return {}
    try:
        with open(HISTORY_DB_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_persistent_history(user_id, statement_list):
    db = load_persistent_histories()
    db[str(user_id)] = statement_list
    try:
        with open(HISTORY_DB_PATH, 'w') as f:
            json.dump(db, f, indent=4)
    except Exception as e:
        print(f"Failed to persist historical directory profile logs: {e}")

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_statement():
    user_id = session.get('user_id')
    if not user_id:
        user_id = session.get('user_name', 'default_user')

    all_histories = load_persistent_histories()
    user_history_log = all_histories.get(str(user_id), [])

    history_id = request.form.get('history_id')
    selected_date = request.form.get('selected_date')
    chart_period = request.form.get('chart_period', 'weekly')
    
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
        active_id = session.get('active_statement_id')
        matched = None
        if active_id:
            matched = next((item for item in user_history_log if item['id'] == active_id), None)
            
        if matched and os.path.exists(matched['file_path']):
            target_path = matched['file_path']
        else:
            return jsonify({
                "status": "success",
                "total_earnings": 0.0,
                "transaction_count": 0,
                "avg_daily": 0.0,
                "peak_day": "--",
                "next_month_forecast": 0.0,
                "years_summary": "No active data metrics loaded.",
                "anchor_date": "No statement processed yet",
                "history_log": user_history_log,
                "active_id": None,
                "available_dates": [],
                "daily_hourly_data": {"labels": [], "data": [], "selected_date": ""},
                "charts": {
                    "daily": { "labels": [], "data": [], "mean": 0, "selected_date": "" },
                    "weekly": { "labels": ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], "data": [0]*7, "mean": 0, "range": "No Data" },
                    "monthly": { "labels": ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], "data": [0]*12, "mean": 0, "range": "No Data" },
                    "yearly": { "labels": [], "data": [], "mean": 0 }
                }
            })

    try:
        cleaner = DataCleaner(target_path)
        df = cleaner.clean_data()
        
        if df.empty:
            return jsonify({"status": "error", "message": "No valid collection earnings records found."}), 400
            
        week_offset = int(request.form.get('week_offset', 0))
        year_offset = int(request.form.get('year_offset', 0))
        
        base_anchor = df['Date'].max()
        adjusted_week_anchor = base_anchor + timedelta(weeks=week_offset)
        adjusted_year_num = base_anchor.year + year_offset
        
        available_dates = sorted(df['Date'].dt.date.unique().tolist())
        available_dates_str = [d.strftime('%Y-%m-%d') for d in available_dates]
        
        # Get daily hourly data
        daily_hourly_data = {"labels": [], "data": [], "selected_date": ""}
        if chart_period == 'daily' and selected_date:
            try:
                target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
                df_day = df[df['Date'].dt.date == target_date]
            except ValueError:
                df_day = pd.DataFrame()
        else:
            # Default to most recent date for daily view
            if available_dates:
                target_date = available_dates[-1]
                df_day = df[df['Date'].dt.date == target_date]
                selected_date = target_date.strftime('%Y-%m-%d')
            else:
                df_day = pd.DataFrame()
        
        if not df_day.empty:
            df_day_copy = df_day.copy()
            # FIX: Pull directly from the Hour column generated by cleaner.py to avoid altering the forecast frequency
            if 'Hour' not in df_day_copy.columns:
                df_day_copy['Hour'] = df_day_copy['Date'].dt.hour
                
            hour_grouping = df_day_copy.groupby('Hour')['Amount (KES)'].sum()
            all_hours = list(range(24))
            hourly_data = [float(hour_grouping.get(h, 0)) for h in all_hours]
            hourly_labels = [f"{h:02d}:00" for h in all_hours]
            daily_hourly_data = {
                "labels": hourly_labels,
                "data": hourly_data,
                "selected_date": selected_date or ""
            }
        else:
            daily_hourly_data = {"labels": [f"{h:02d}:00" for h in range(24)], "data": [0]*24, "selected_date": ""}
        
        # Global metrics
        total_earnings = float(df['Amount (KES)'].sum())
        transaction_count = len(df)
        included_years = sorted(df['Date'].dt.year.unique().tolist())
        years_summary = f"Includes data from: {', '.join(map(str, included_years))}"
        
        unique_days = df['Date'].dt.date.nunique()
        avg_daily_income = float(total_earnings / unique_days) if unique_days > 0 else 0.0
        
        df['DayName'] = df['Date'].dt.day_name()
        peak_day = str(df.groupby('DayName')['Amount (KES)'].sum().idxmax())

        model_engine = Predictor()
        prediction = float(model_engine.forecast_next_period(df))
        
        # Weekly view
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

        # Monthly view
        df_year = df[df['Date'].dt.year == adjusted_year_num]
        df_year = df_year.copy()
        df_year['MonthNum'] = df_year['Date'].dt.month
        month_order = list(range(1, 13))
        month_grouping = df_year.groupby('MonthNum')['Amount (KES)'].sum().reindex(month_order, fill_value=0)
        
        monthly_data = [float(val) for val in month_grouping.values]
        monthly_mean = float(month_grouping.mean())
        monthly_year_str = f"Year: {adjusted_year_num}"

        # Yearly view
        year_grouping = df.groupby(df['Date'].dt.year)['Amount (KES)'].sum()
        yearly_labels = [str(y) for y2 in sorted(year_grouping.index) for y in [y2]]
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
            "available_dates": available_dates_str,
            "daily_hourly_data": daily_hourly_data,
            "charts": {
                "daily": { "labels": daily_hourly_data["labels"], "data": daily_hourly_data["data"], "mean": round(sum(daily_hourly_data["data"]) / 24 if daily_hourly_data["data"] else 0, 2), "selected_date": daily_hourly_data["selected_date"] },
                "weekly": { "labels": chart_labels, "data": chart_data, "mean": round(weekly_mean, 2), "range": week_range_str },
                "monthly": { "labels": ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], "data": monthly_data, "mean": round(monthly_mean, 2), "range": monthly_year_str },
                "yearly": { "labels": yearly_labels, "data": yearly_data, "mean": round(yearly_mean, 2) }
            }
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Processing runtime failure: {str(e)}"}), 500

@app.route('/api/rename/<string:history_id>', methods=['POST'])
@login_required
def rename_statement(history_id):
    user_id = session.get('user_id')
    if not user_id:
        user_id = session.get('user_name', 'default_user')

    new_name = request.form.get('new_filename', '').strip()
    if not new_name:
        return jsonify({"status": "error", "message": "Filename cannot be empty."}), 400
        
    # Ensure it keeps the .csv extension visually if the user drops it
    if not new_name.lower().endswith('.csv'):
        new_name += '.csv'

    all_histories = load_persistent_histories()
    user_history_log = all_histories.get(str(user_id), [])

    matched_item = next((item for item in user_history_log if item['id'] == history_id), None)
    
    if not matched_item:
        return jsonify({"status": "error", "message": "Statement not found in history archive."}), 404

    # Update the display name
    matched_item['filename'] = new_name
    save_persistent_history(user_id, user_history_log)

    return jsonify({
        "status": "success", 
        "message": "Statement renamed successfully.",
        "history_log": user_history_log,
        "active_id": session.get('active_statement_id')
    })

@app.route('/api/delete/<string:history_id>', methods=['POST'])
@login_required
def delete_statement(history_id):
    user_id = session.get('user_id')
    if not user_id:
        user_id = session.get('user_name', 'default_user')

    all_histories = load_persistent_histories()
    user_history_log = all_histories.get(str(user_id), [])

    matched_index = next((i for i, item in enumerate(user_history_log) if item['id'] == history_id), None)
    
    if matched_index is None:
        return jsonify({"status": "error", "message": "Statement not found in history archive."}), 404

    matched_item = user_history_log[matched_index]
    
    if os.path.exists(matched_item['file_path']):
        try:
            os.remove(matched_item['file_path'])
        except Exception as e:
            print(f"Failed to delete structural file asset: {e}")

    user_history_log.pop(matched_index)
    save_persistent_history(user_id, user_history_log)

    if session.get('active_statement_id') == history_id:
        session.pop('active_statement_id', None)

    return jsonify({"status": "success", "message": "Statement removed cleanly."})

if __name__ == '__main__':
    app.run(debug=True)