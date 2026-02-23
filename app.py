from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, url_for, redirect, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///habits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-password-secret-key'  

db = SQLAlchemy(app)


class Habit(db.Model):
    __tablename__ = 'habit'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    color = db.Column(db.String(9), default="#3b82f6")
    goal_type = db.Column(db.String(20), default='daily')
    target_per_day = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Checking(db.Model):
    __tablename__ = 'checking'
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    __table_args__ = (UniqueConstraint('habit_id', 'date', name='uix_habit_date'),)


Habit.checking = db.relationship('Checking', backref='habit', cascade='all, delete-orphan', lazy='selectin')

with app.app_context():
    db.create_all()


def get_streak_from_dates(dates_set, today):
    """Given a set of datetime.date objects when habit was checked, compute current streak."""
    s = 0
    d = today
    while d in dates_set:
        s += 1
        d -= timedelta(days=1)
    return s

def get_weekly_data_for_habit(habit_id, days_window=7):
    """Get weekly check-in data for a specific habit."""
    today = date.today()
    days = [today - timedelta(days=i) for i in reversed(range(days_window))]
    
    
    checkings = Checking.query.filter(
        Checking.habit_id == habit_id,
        Checking.date >= days[0]
    ).all()
    
    checking_dates = {c.date for c in checkings}
    
    
    data = [1 if day in checking_dates else 0 for day in days]
    labels = [day.strftime('%a') for day in days]
    
    return labels, data

def get_weekly_data_all_habits(days_window=7):
    """Get weekly check-in data for all habits combined."""
    today = date.today()
    days = [today - timedelta(days=i) for i in reversed(range(days_window))]
    
    
    checkings = Checking.query.filter(Checking.date >= days[0]).all()
    
    
    daily_counts = {}
    for checking in checkings:
        daily_counts[checking.date] = daily_counts.get(checking.date, 0) + 1
    
    data = [daily_counts.get(day, 0) for day in days]
    labels = [day.strftime('%a') for day in days]
    
    return labels, data


@app.route('/')
def index():
    today = date.today()
    
    days = [today - timedelta(days=i) for i in reversed(range(7))]

    
    habits = Habit.query.order_by(Habit.created_at.desc()).options(joinedload(Habit.checking)).all()

    
    check_map = {(c.habit_id, c.date) for h in habits for c in h.checking if c.date >= days[0]}
    habit_dates = {h.id: {c.date for c in h.checking} for h in habits}

    
    streaks = {h.id: get_streak_from_dates(habit_dates.get(h.id, set()), today) for h in habits}

    return render_template('index.html', habits=habits, days=days, Check_map=check_map, today=today, streaks=streaks)

@app.route('/habits')
def habits_page():
    habits = Habit.query.order_by(Habit.created_at.desc()).all()
    return render_template('habits.html', habits=habits)

@app.route('/habits/create', methods=['POST'])
def create_habit():
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#3b82f6').strip()
    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('habits_page'))

    try:
        habit = Habit(name=name, color=color)
        db.session.add(habit)
        db.session.commit()
        flash('Habit created', 'success')
       
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": True, "id": habit.id, "name": habit.name, "color": habit.color})
    except IntegrityError:
        db.session.rollback()
        flash('Habit name must be unique', 'error')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False, "error": "unique"}), 400
    except Exception as e:
        db.session.rollback()
        flash('An error occurred', 'error')
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False, "error": "server"}), 500

    return redirect(url_for('habits_page'))

@app.route('/habits/<int:habit_id>/edit', methods=['POST'])
def edit_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#3b82f6').strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    habit.name = name
    habit.color = color
    try:
        db.session.commit()
        flash('Habit updated', 'success')
        return jsonify({"ok": True, "id": habit.id, "name": habit.name, "color": habit.color})
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "error": "unique"}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "server"}), 500

@app.route('/habits/<int:habit_id>/delete', methods=['POST'])
def delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    try:
        db.session.delete(habit)
        db.session.commit()
        flash("Habit deleted", "success")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": True})
    except Exception:
        db.session.rollback()
        flash("Failed to delete habit", "error")
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"ok": False}), 500

    return redirect(url_for('habits_page'))

@app.route('/toggle', methods=['POST'])
def toggle():
    
    data = request.get_json(silent=True) or request.form
    try:
        hid = int(data.get('habit_id'))
        d = date.fromisoformat(data.get('date'))
    except Exception:
        return jsonify({"ok": False, "error": "invalid_payload"}), 400

    existing = Checking.query.filter_by(habit_id=hid, date=d).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        status = False
    else:
        check = Checking(habit_id=hid, date=d)
        db.session.add(check)
        db.session.commit()
        status = True

    
    dates = {c.date for c in Checking.query.filter_by(habit_id=hid).all()}
    streak = get_streak_from_dates(dates, date.today())

    return jsonify({"ok": True, "checked": status, "streak": streak})

@app.route('/analytics.json')
def analytics_json():
    """Returns analytics data for all habits combined"""
    labels, data = get_weekly_data_all_habits()
    
    
    habits = Habit.query.all()
    if habits:
        colors = [h.color for h in habits]
       
        palette = (colors * 7)[:7]
    else:
        palette = ["#3b82f6"] * 7

    return jsonify({"labels": labels, "data": data, "colors": palette})

@app.route('/analytics/habit/<int:habit_id>.json')
def habit_analytics_json(habit_id):
    """Returns analytics data for a specific habit"""
    habit = Habit.query.get_or_404(habit_id)
    labels, data = get_weekly_data_for_habit(habit_id)
    
    return jsonify({
        "labels": labels, 
        "data": data, 
        "color": habit.color,
        "name": habit.name
    })

@app.route('/analytics')
def analytics_page():
    habits = Habit.query.order_by(Habit.created_at.desc()).all()
    return render_template('analytics.html', habits=habits)


@app.route('/ping')
def ping():
    return "pong"

if __name__ == '__main__':
    app.run(debug=True, port=1002)