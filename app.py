import os
import uuid
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from functools import wraps
import pandas as pd
import io
from cleaner import DataCleaner
from predictor import Predictor
from auth_handler import AuthenticationHandler
from firebase_admin import firestore

app = Flask(__name__)
app.secret_key = 'pesatracka_super_secret_session_encryption_key'

db = firestore.client()

PARSED_DF_CACHE = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def load_user_history_from_firebase(user_id):
    try:
        user_doc_ref = db.collection('user_histories').document(str(user_id))
        doc = user_doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('statements', [])
    except Exception as e:
        print(f"Error fetching from Firestore: {e}")
    return []

def save_user_history_to_firebase(user_id, statement_list):
    try:
        lightweight_list = []
        for item in statement_list:
            entry = item.copy()
            entry.pop('raw_csv_content', None)
            lightweight_list.append(entry)

        user_doc_ref = db.collection('user_histories').document(str(user_id))
        user_doc_ref.set({
            'statements': lightweight_list,
            'last_updated': firestore.SERVER_TIMESTAMP
        }, merge=True)
    except Exception as e:
        print(f"Failed to persist historical directory logs: {e}")

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
            session['user_name'] = user.display_name.split()[0] if user.display_name else "User"
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
            email=data['email'], password=data['password'], phone_number=data['phone'],
            business_name=data['business_name'], first_name=data['first_name'], last_name=data['last_name']
        )
        if result['status'] == 'success':
            return redirect(url_for('login_page', msg="Account created successfully. Please log in."))
        return render_template('auth.html', error=result['message'], mode='signup')
    return render_template('auth.html', mode='signup')

@app.route('/logout')
def logout():
    AuthenticationHandler.logout_user()
    return redirect(url_for('login_page'))


@app.route('/api/upload', methods=['POST'])
@login_required
def upload_statement():
    user_id = session.get('user_id', 'default_user')
    user_history_log = load_user_history_from_firebase(user_id)

    history_id = request.form.get('history_id')
    selected_date = request.form.get('selected_date')
    chart_period = request.form.get('chart_period', 'weekly')
    
    df = None

    # CASE A: User clicked an old historical entry
    if history_id:
        if history_id in PARSED_DF_CACHE:
            df = PARSED_DF_CACHE[history_id]
            session['active_statement_id'] = history_id
        else:
            return jsonify({"status": "error", "message": "Statement session state expired. Please re-upload the statement."}), 404
            
    # CASE B: User is uploading a completely new file
    elif 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        if not file.filename.endswith('.csv'):
            return jsonify({"status": "error", "message": "File format type must be extension .csv"}), 400
            
        try:
            raw_text = file.read().decode('utf-8', errors='ignore')
            csv_data_stream = io.StringIO(raw_text)
            cleaner = DataCleaner(csv_data_stream)
            df = cleaner.clean_data()
        except Exception as e:
            return jsonify({"status": "error", "message": f"Failed to parse file text stream: {str(e)}"}), 400
            
        unique_id = str(uuid.uuid4())
        now = datetime.now()
        
        new_record = {
            "id": unique_id,
            "filename": file.filename,
            "date_uploaded": now.strftime('%d %b %Y'),
            "time_uploaded": now.strftime('%H:%M:%S')
        }
        
        PARSED_DF_CACHE[unique_id] = df
        user_history_log.append(new_record)
        save_user_history_to_firebase(user_id, user_history_log)
        session['active_statement_id'] = unique_id
        
    # CASE C: Re-fetching the active view on refresh / filter changes
    else:
        active_id = session.get('active_statement_id')
        if active_id and active_id in PARSED_DF_CACHE:
            df = PARSED_DF_CACHE[active_id]
        else:
            return jsonify({
                "status": "success", "total_earnings": 0.0, "transaction_count": 0, "avg_daily": 0.0, "peak_day": "--",
                "next_month_forecast": 0.0, "years_summary": "No active data metrics loaded.",
                "anchor_date": "No statement processed yet", "history_log": user_history_log, "active_id": None, "available_dates": [],
                "daily_hourly_data": {"labels": [], "data": [], "selected_date": ""},
                "charts": {
                    "daily": { "labels": [], "data": [], "mean": 0, "selected_date": "" },
                    "weekly": { "labels": ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'], "data": [0]*7, "mean": 0, "range": "No Data" },
                    "monthly": { "labels": ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], "data": [0]*12, "mean": 0, "range": "No Data" },
                    "yearly": { "labels": [], "data": [], "mean": 0 }
                }
            })

    try:
        if df is None or df.empty:
            return jsonify({"status": "error", "message": "No valid collection earnings records found."}), 400
            
        week_offset = int(request.form.get('week_offset', 0))
        year_offset = int(request.form.get('year_offset', 0))
        
        base_anchor = df['Date'].max()
        adjusted_week_anchor = base_anchor + timedelta(weeks=week_offset)
        adjusted_year_num = base_anchor.year + year_offset
        
        available_dates = df['DateOnly'].unique().tolist()
        
        daily_hourly_data = {"labels": [], "data": [], "selected_date": ""}
        if chart_period == 'daily' and selected_date:
            df_day = df[df['DateOnly'] == selected_date]
        else:
            if available_dates:
                selected_date = available_dates[-1]
                df_day = df[df['DateOnly'] == selected_date]
            else:
                df_day = pd.DataFrame()
        
        if not df_day.empty:
            hour_grouping = df_day.groupby('Hour')['Amount (KES)'].sum()
            all_hours = list(range(24))
            hourly_data = [float(hour_grouping.get(h, 0)) for h in all_hours]
            hourly_labels = [f"{h:02d}:00" for h in all_hours]
            daily_hourly_data = {
                "labels": hourly_labels, "data": hourly_data, "selected_date": selected_date or ""
            }
        else:
            daily_hourly_data = {"labels": [f"{h:02d}:00" for h in range(24)], "data": [0]*24, "selected_date": ""}
        
        total_earnings = float(df['Amount (KES)'].sum())
        transaction_count = len(df)
        included_years = sorted(df['Year'].unique().tolist())
        years_summary = f"Includes data from: {', '.join(map(str, included_years))}"
        
        unique_days = len(available_dates)
        avg_daily_income = float(total_earnings / unique_days) if unique_days > 0 else 0.0
        
        peak_day = str(df.groupby('DayName')['Amount (KES)'].sum().idxmax())

        model_engine = Predictor()
        prediction = float(model_engine.forecast_next_period(df))
        
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

        df_year = df[df['Year'] == adjusted_year_num]
        month_order = list(range(1, 13))
        month_grouping = df_year.groupby('MonthNum')['Amount (KES)'].sum().reindex(month_order, fill_value=0)
        
        monthly_data = [float(val) for val in month_grouping.values]
        monthly_mean = float(month_grouping.mean())
        monthly_year_str = f"Year: {adjusted_year_num}"

        year_grouping = df.groupby('Year')['Amount (KES)'].sum()
        yearly_labels = [str(y) for y in sorted(year_grouping.index)]
        yearly_data = [float(year_grouping[int(y)]) for y in yearly_labels]
        yearly_mean = float(year_grouping.mean()) if len(yearly_labels) > 0 else 0.0

        return jsonify({
            "status": "success", "total_earnings": total_earnings, "transaction_count": transaction_count,
            "avg_daily": round(avg_daily_income, 2), "peak_day": peak_day, "next_month_forecast": round(prediction, 2),
            "years_summary": years_summary, "anchor_date": base_anchor.strftime('%d %b %Y at %H:%M'),
            "history_log": user_history_log, "active_id": session.get('active_statement_id'), "available_dates": available_dates,
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
    user_id = session.get('user_id', 'default_user')
    new_name = request.form.get('new_filename', '').strip()
    if not new_name:
        return jsonify({"status": "error", "message": "Filename cannot be empty."}), 400
        
    if not new_name.lower().endswith('.csv'):
        new_name += '.csv'

    user_history_log = load_user_history_from_firebase(user_id)
    matched_item = next((item for item in user_history_log if item['id'] == history_id), None)
    
    if not matched_item:
        return jsonify({"status": "error", "message": "Statement not found in history archive."}), 404

    matched_item['filename'] = new_name
    save_user_history_to_firebase(user_id, user_history_log)

    return jsonify({
        "status": "success", "message": "Statement renamed successfully.",
        "history_log": user_history_log, "active_id": session.get('active_statement_id')
    })

@app.route('/api/delete/<string:history_id>', methods=['POST'])
@login_required
def delete_statement(history_id):
    user_id = session.get('user_id', 'default_user')
    user_history_log = load_user_history_from_firebase(user_id)
    
    matched_index = next((i for i, item in enumerate(user_history_log) if item['id'] == history_id), None)
    if matched_index is None:
        return jsonify({"status": "error", "message": "Statement not found in history archive."}), 404

    user_history_log.pop(matched_index)
    save_user_history_to_firebase(user_id, user_history_log)

    if session.get('active_statement_id') == history_id:
        session.pop('active_statement_id', None)
        PARSED_DF_CACHE.pop(history_id, None)

    return jsonify({"status": "success", "message": "Statement removed cleanly.", "history_log": user_history_log})

if __name__ == '__main__':
    app.run(debug=True)