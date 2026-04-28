from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, csv, io, json
from datetime import datetime, timedelta
from calendar import monthrange
from functools import wraps

app = Flask(__name__)
app.secret_key = 'expense_tracker_secret_key_2024'
DATABASE = 'expense_tracker.db'
CATEGORIES = ['Food', 'Transport', 'Rent', 'Shopping', 'Entertainment', 'Health', 'Others']

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_categories(user_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM custom_categories WHERE user_id=? ORDER BY category",
            (user_id,)).fetchall()
    custom = [r['category'] for r in rows]
    return CATEGORIES + [c for c in custom if c not in CATEGORIES]

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                monthly_budget REAL DEFAULT 0,
                monthly_income REAL DEFAULT 0,
                savings_goal_name TEXT DEFAULT 'Emergency Fund',
                savings_goal_target REAL DEFAULT 0,
                savings_goal_current REAL DEFAULT 0,
                theme TEXT DEFAULT 'dark',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                is_recurring INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS category_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                budget REAL DEFAULT 0,
                UNIQUE(user_id, category),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS custom_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                UNIQUE(user_id, category),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        ''')
        for col in ['is_recurring INTEGER DEFAULT 0']:
            try: conn.execute(f'ALTER TABLE transactions ADD COLUMN {col}')
            except: pass
        for col in ['savings_goal_name TEXT DEFAULT "Emergency Fund"',
                    'savings_goal_target REAL DEFAULT 0',
                    'savings_goal_current REAL DEFAULT 0',
                    'theme TEXT DEFAULT "dark"']:
            try: conn.execute(f'ALTER TABLE users ADD COLUMN {col}')
            except: pass

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    error = None
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        e = request.form.get('email','').strip()
        p = request.form.get('password','')
        c = request.form.get('confirm_password','')
        if not u or not e or not p: error = 'All fields are required.'
        elif p != c: error = 'Passwords do not match.'
        elif len(p) < 6: error = 'Password must be at least 6 characters.'
        else:
            try:
                with get_db() as conn:
                    conn.execute('INSERT INTO users (username,email,password) VALUES (?,?,?)',
                        (u, e, generate_password_hash(p)))
                return redirect(url_for('login', success='Account created!'))
            except sqlite3.IntegrityError:
                error = 'Username or email already exists.'
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    success = request.args.get('success')
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','')
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone()
        if user and check_password_hash(user['password'], p):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password.'
    return render_template('login.html', error=error, success=success)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/toggle_theme')
@login_required
def toggle_theme():
    with get_db() as conn:
        user = conn.execute('SELECT theme FROM users WHERE id=?',(session['user_id'],)).fetchone()
        new_theme = 'light' if (user['theme'] or 'dark') == 'dark' else 'dark'
        conn.execute('UPDATE users SET theme=? WHERE id=?',(new_theme, session['user_id']))
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    today = datetime.now()
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        txs = conn.execute(
            "SELECT * FROM transactions WHERE user_id=? AND date LIKE ? ORDER BY date DESC",
            (uid, f"{month}%")).fetchall()
        cat_budgets = {r['category']:r['budget'] for r in
            conn.execute("SELECT category,budget FROM category_budgets WHERE user_id=?",(uid,)).fetchall()}
        trend_data = []
        for i in range(5,-1,-1):
            d = today.replace(day=1) - timedelta(days=i*28)
            m_str = d.strftime('%Y-%m')
            s = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND date LIKE ?",
                (uid,f"{m_str}%")).fetchone()['s']
            trend_data.append({'month': d.strftime('%b %y'), 'amount': round(s,2)})
        daily_map = {}
        for r in conn.execute(
            "SELECT date,SUM(amount) as t FROM transactions WHERE user_id=? AND date>=? GROUP BY date",
            (uid,(today-timedelta(days=29)).strftime('%Y-%m-%d'))).fetchall():
            daily_map[r['date']] = round(r['t'],2)

    daily_labels, daily_values = [], []
    for i in range(29,-1,-1):
        d = today - timedelta(days=i)
        daily_labels.append(d.strftime('%d %b'))
        daily_values.append(daily_map.get(d.strftime('%Y-%m-%d'),0))

    total_spent = sum(t['amount'] for t in txs)
    balance = float(user['monthly_income']) - total_spent
    cat_data = {}
    for t in txs:
        cat_data[t['category']] = round(cat_data.get(t['category'],0) + t['amount'],2)

    top_cat = max(cat_data, key=cat_data.get) if cat_data else None
    year,mon = map(int,month.split('-'))
    days_in_month = monthrange(year,mon)[1]
    days_left = max(1, days_in_month - today.day + 1) if today.year==year and today.month==mon else 1
    remaining = max(0, float(user['monthly_budget']) - total_spent)
    daily_budget = round(remaining/days_left, 2)
    budget_pct = round(total_spent/float(user['monthly_budget'])*100,1) if user['monthly_budget'] else 0
    goal_pct = 0
    if user['savings_goal_target'] and float(user['savings_goal_target']) > 0:
        goal_pct = min(100, round(float(user['savings_goal_current'])/float(user['savings_goal_target'])*100,1))

    recent_txs = list(txs)[:5]
    all_categories = get_all_categories(uid)

    return render_template('dashboard.html',
        user=user, transactions=txs, recent_txs=recent_txs,
        total_spent=total_spent, balance=balance, cat_data=cat_data,
        cat_budgets=cat_budgets, current_month=month,
        top_cat=top_cat, top_amount=cat_data.get(top_cat,0) if top_cat else 0,
        daily_budget=daily_budget, days_left=days_left,
        budget_pct=budget_pct, goal_pct=goal_pct,
        trend_data=json.dumps(trend_data),
        daily_labels=json.dumps(daily_labels),
        daily_values=json.dumps(daily_values),
        categories=all_categories)

@app.route('/history')
@login_required
def history():
    uid = session['user_id']
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        txs = conn.execute(
            "SELECT * FROM transactions WHERE user_id=? AND date LIKE ? ORDER BY date DESC",
            (uid, f"{month}%")).fetchall()
        cat_budgets = {r['category']:r['budget'] for r in
            conn.execute("SELECT category,budget FROM category_budgets WHERE user_id=?",(uid,)).fetchall()}
    total_spent = sum(t['amount'] for t in txs)
    cat_data = {}
    for t in txs:
        cat_data[t['category']] = round(cat_data.get(t['category'],0)+t['amount'],2)
    return render_template('history.html',
        user=user, transactions=txs, total_spent=total_spent,
        cat_data=cat_data, cat_budgets=cat_budgets,
        current_month=month, categories=get_all_categories(uid))

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    uid = session['user_id']
    d = request.form.get('date')
    a = request.form.get('amount')
    c = request.form.get('category')
    desc = request.form.get('description','')
    rec = 1 if request.form.get('is_recurring') else 0
    if d and a and c:
        with get_db() as conn:
            conn.execute('INSERT INTO transactions (user_id,date,amount,category,description,is_recurring) VALUES (?,?,?,?,?,?)',
                (uid,d,float(a),c,desc,rec))
    ref = request.form.get('redirect_to','dashboard')
    return redirect(url_for(ref))

@app.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete():
    uid = session['user_id']
    ids = request.form.getlist('selected_ids')
    if ids:
        with get_db() as conn:
            for tid in ids:
                conn.execute('DELETE FROM transactions WHERE id=? AND user_id=?',(tid,uid))
    return redirect(url_for('history'))

@app.route('/edit_transaction/<int:tid>', methods=['GET','POST'])
@login_required
def edit_transaction(tid):
    uid = session['user_id']
    with get_db() as conn:
        t = conn.execute('SELECT * FROM transactions WHERE id=? AND user_id=?',(tid,uid)).fetchone()
        if not t: return redirect(url_for('history'))
        if request.method == 'POST':
            conn.execute('UPDATE transactions SET date=?,amount=?,category=?,description=?,is_recurring=? WHERE id=? AND user_id=?',
                (request.form.get('date'), float(request.form.get('amount')),
                 request.form.get('category'), request.form.get('description',''),
                 1 if request.form.get('is_recurring') else 0, tid, uid))
            return redirect(url_for('history'))
    user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    return render_template('edit_transaction.html', t=t, categories=get_all_categories(uid), user=user)

@app.route('/delete_transaction/<int:tid>')
@login_required
def delete_transaction(tid):
    uid = session['user_id']
    with get_db() as conn:
        conn.execute('DELETE FROM transactions WHERE id=? AND user_id=?',(tid,uid))
    return redirect(url_for('history'))

@app.route('/set_income', methods=['GET','POST'])
@login_required
def set_income():
    uid = session['user_id']
    msg = None
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        cat_budgets = conn.execute('SELECT category,budget FROM category_budgets WHERE user_id=?',(uid,)).fetchall()
        if request.method == 'POST':
            conn.execute('UPDATE users SET monthly_income=?,monthly_budget=?,savings_goal_name=?,savings_goal_target=?,savings_goal_current=? WHERE id=?',
                (float(request.form.get('income',0)), float(request.form.get('budget',0)),
                 request.form.get('goal_name','Emergency Fund'),
                 float(request.form.get('goal_target',0)), float(request.form.get('goal_current',0)), uid))
            for cat in get_all_categories(uid):
                conn.execute('INSERT OR REPLACE INTO category_budgets (user_id,category,budget) VALUES (?,?,?)',
                    (uid,cat,float(request.form.get(f'cat_budget_{cat}',0))))
            msg = 'Settings updated!'
            user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            cat_budgets = conn.execute('SELECT category,budget FROM category_budgets WHERE user_id=?',(uid,)).fetchall()
    return render_template('set_income.html', user=user, msg=msg, categories=get_all_categories(uid),
        cat_budget_dict={r['category']:r['budget'] for r in cat_budgets})

# ── API: Add funds to savings goal (AJAX, no page reload) ──
@app.route('/api/add_funds', methods=['POST'])
@login_required
def api_add_funds():
    uid = session['user_id']
    try:
        amount = float(request.json.get('amount', 0))
        if amount <= 0:
            return jsonify({'ok': False, 'error': 'Amount must be positive'}), 400
        with get_db() as conn:
            conn.execute(
                'UPDATE users SET savings_goal_current = savings_goal_current + ? WHERE id=?',
                (amount, uid))
            user = conn.execute('SELECT savings_goal_current, savings_goal_target FROM users WHERE id=?', (uid,)).fetchone()
        current = float(user['savings_goal_current'])
        target  = float(user['savings_goal_target']) if user['savings_goal_target'] else 0
        pct = round(min(100, current / target * 100), 1) if target > 0 else 0
        return jsonify({'ok': True, 'current': current, 'target': target, 'pct': pct})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── API: Save a new custom category ──
@app.route('/api/add_custom_category', methods=['POST'])
@login_required
def api_add_custom_category():
    uid = session['user_id']
    try:
        name = request.json.get('name', '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'Name required'}), 400
        if name in CATEGORIES:
            return jsonify({'ok': True, 'existed': True})
        with get_db() as conn:
            conn.execute('INSERT OR IGNORE INTO custom_categories (user_id, category) VALUES (?,?)', (uid, name))
        return jsonify({'ok': True, 'existed': False, 'name': name})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/export_csv')
@login_required
def export_csv():
    uid = session['user_id']
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    with get_db() as conn:
        txs = conn.execute(
            "SELECT date,amount,category,description,is_recurring FROM transactions WHERE user_id=? AND date LIKE ? ORDER BY date DESC",
            (uid,f"{month}%")).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Date','Amount (Rs)','Category','Description','Recurring'])
    for t in txs:
        w.writerow([t['date'],t['amount'],t['category'],t['description'],'Yes' if t['is_recurring'] else 'No'])
    resp = make_response(out.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=expenses_{month}.csv'
    resp.headers['Content-type'] = 'text/csv'
    return resp

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
