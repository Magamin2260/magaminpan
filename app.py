from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

app.secret_key = 'pancard_secret_2024'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT,
        mobile TEXT,
        role TEXT DEFAULT 'user',
        wallet REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        app_category TEXT,
        last_name TEXT,
        first_name TEXT,
        middle_name TEXT,
        full_name TEXT,
        father_last_name TEXT,
        father_first_name TEXT,
        father_middle_name TEXT,
        father_name TEXT,
        dob TEXT,
        gender TEXT,
        mobile TEXT,
        email TEXT,
        aadhaar TEXT,
        pan_type TEXT,
        address TEXT,
        city TEXT,
        state TEXT,
        pincode TEXT,
        photo TEXT,
        signature TEXT,
        aadhaar_doc TEXT,
        additional_doc TEXT,
        receipt TEXT,
        status TEXT DEFAULT 'Pending',
        correction_name TEXT DEFAULT 'No Change',
        correction_dob TEXT DEFAULT 'No Change',
        correction_father TEXT DEFAULT 'No Change',
        correction_gender TEXT DEFAULT 'No Change',
        correction_address TEXT DEFAULT 'No Change',
        correction_photo TEXT DEFAULT 'No Change',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS wallet_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    # Create default admin
    try:
        conn.execute("INSERT INTO users (username, password, role, wallet) VALUES (?, ?, ?, ?)",
                     ('admin', 'admin123', 'admin', 0))
    except:
        pass
    conn.commit()
    conn.close()

# Auto-migrate missing columns
def migrate_db():
    conn = get_db()
    existing = [row[1] for row in conn.execute("PRAGMA table_info(applications)").fetchall()]
    new_cols = {
        'receipt': 'TEXT',
        'correction_name': "TEXT DEFAULT 'No Change'",
        'correction_dob': "TEXT DEFAULT 'No Change'",
        'correction_father': "TEXT DEFAULT 'No Change'",
        'correction_gender': "TEXT DEFAULT 'No Change'",
        'correction_address': "TEXT DEFAULT 'No Change'",
        'correction_photo': "TEXT DEFAULT 'No Change'",
        'last_name': 'TEXT',
        'first_name': 'TEXT',
        'middle_name': 'TEXT',
        'father_last_name': 'TEXT',
        'father_first_name': 'TEXT',
        'father_middle_name': 'TEXT',
        'app_category': 'TEXT',
    }
    for col, coltype in new_cols.items():
        if col not in existing:
            try:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {coltype}")
            except:
                pass
    # wallet column for users
    user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if 'wallet' not in user_cols:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN wallet REAL DEFAULT 0.0")
        except:
            pass
    conn.commit()
    conn.close()

# Initialize on startup
init_db()
migrate_db()

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password=?', (u, p)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        e = request.form.get('email', '')
        m = request.form.get('mobile', '')
        try:
            conn = get_db()
            conn.execute('INSERT INTO users (username, password, email, mobile) VALUES (?,?,?,?)', (u, p, e, m))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Username already exists', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    apps = conn.execute('SELECT * FROM applications WHERE user_id=? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    user = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    transactions = conn.execute('SELECT * FROM wallet_transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 10', (session['user_id'],)).fetchall()
    conn.close()
    stats = {
        'total': len(apps),
        'pending': sum(1 for a in apps if a['status'] == 'Pending'),
        'processing': sum(1 for a in apps if a['status'] == 'Processing'),
        'approved': sum(1 for a in apps if a['status'] == 'Approved'),
        'rejected': sum(1 for a in apps if a['status'] == 'Rejected'),
    }
    return render_template('dashboard.html', apps=apps, stats=stats, user=user, transactions=transactions)

@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        if user['wallet'] < 150:
            flash('Insufficient wallet balance. Please contact admin to add funds.', 'error')
            conn.close()
            return redirect(url_for('apply'))

        def save_file(field):
            f = request.files.get(field)
            if f and f.filename and allowed_file(f.filename):
                fn = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                return fn
            return None

        last_name = request.form.get('last_name', '').upper()
        first_name = request.form.get('first_name', '').upper()
        middle_name = request.form.get('middle_name', '').upper()
        full_name = request.form.get('full_name', '').upper()
        father_last = request.form.get('father_last_name', '').upper()
        father_first = request.form.get('father_first_name', '').upper()
        father_middle = request.form.get('father_middle_name', '').upper()
        father_name = f"{father_first} {father_middle} {father_last}".strip()

        conn.execute('''INSERT INTO applications
            (user_id, app_category, last_name, first_name, middle_name, full_name,
             father_last_name, father_first_name, father_middle_name, father_name,
             dob, gender, mobile, email, aadhaar, pan_type,
             address, city, state, pincode, photo, signature, aadhaar_doc, additional_doc,
             correction_name, correction_dob, correction_father, correction_gender,
             correction_address, correction_photo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (session['user_id'],
             request.form.get('app_category', 'New PAN'),
             last_name, first_name, middle_name, full_name,
             father_last, father_first, father_middle, father_name,
             request.form.get('dob'), request.form.get('gender'),
             request.form.get('mobile'), request.form.get('email'),
             request.form.get('aadhaar'), request.form.get('pan_type'),
             request.form.get('address'), request.form.get('city'),
             request.form.get('state'), request.form.get('pincode'),
             save_file('photo'), save_file('signature'),
             save_file('aadhaar_doc'), save_file('additional_doc'),
             request.form.get('correction_name', 'No Change'),
             request.form.get('correction_dob', 'No Change'),
             request.form.get('correction_father', 'No Change'),
             request.form.get('correction_gender', 'No Change'),
             request.form.get('correction_address', 'No Change'),
             request.form.get('correction_photo', 'No Change')))

        # Deduct wallet
        conn.execute('UPDATE users SET wallet = wallet - 150 WHERE id=?', (session['user_id'],))
        conn.execute('INSERT INTO wallet_transactions (user_id, amount, type, description) VALUES (?,?,?,?)',
                     (session['user_id'], -150, 'debit', 'PAN Application Fee'))
        conn.commit()
        conn.close()
        flash('Application submitted successfully! ₹150 deducted from wallet.', 'success')
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('form.html', user=user)

@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    apps = conn.execute('''SELECT a.*, u.username FROM applications a
                           JOIN users u ON a.user_id = u.id
                           ORDER BY a.created_at DESC''').fetchall()
    users = conn.execute('''SELECT u.*, COUNT(a.id) as app_count
                            FROM users u LEFT JOIN applications a ON u.id = a.user_id
                            WHERE u.role != 'admin'
                            GROUP BY u.id ORDER BY u.created_at DESC''').fetchall()
    transactions = conn.execute('''SELECT t.*, u.username FROM wallet_transactions t
                                   JOIN users u ON t.user_id = u.id
                                   ORDER BY t.created_at DESC LIMIT 50''').fetchall()
    conn.close()
    stats = {
        'total': len(apps),
        'pending': sum(1 for a in apps if a['status'] == 'Pending'),
        'processing': sum(1 for a in apps if a['status'] == 'Processing'),
        'approved': sum(1 for a in apps if a['status'] == 'Approved'),
        'rejected': sum(1 for a in apps if a['status'] == 'Rejected'),
    }
    return render_template('admin.html', apps=apps, users=users, transactions=transactions, stats=stats)

@app.route('/update_status/<int:app_id>', methods=['POST'])
def update_status(app_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    status = request.form.get('status')
    conn = get_db()
    receipt_filename = None
    if status == 'Processing' and 'receipt' in request.files:
        f = request.files['receipt']
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            receipt_filename = fn
    if receipt_filename:
        conn.execute('UPDATE applications SET status=?, receipt=? WHERE id=?', (status, receipt_filename, app_id))
    else:
        conn.execute('UPDATE applications SET status=? WHERE id=?', (status, app_id))
    conn.commit()
    conn.close()
    flash(f'Application #{app_id} status updated to {status}', 'success')
    return redirect(url_for('admin'))

@app.route('/add_wallet/<int:user_id>', methods=['POST'])
def add_wallet(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    amount = float(request.form.get('amount', 0))
    if amount > 0:
        conn = get_db()
        conn.execute('UPDATE users SET wallet = wallet + ? WHERE id=?', (amount, user_id))
        conn.execute('INSERT INTO wallet_transactions (user_id, amount, type, description) VALUES (?,?,?,?)',
                     (user_id, amount, 'credit', f'Admin added ₹{amount}'))
        conn.commit()
        conn.close()
        flash(f'₹{amount} added to wallet successfully', 'success')
    return redirect(url_for('admin') + '#wallet')

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM wallet_transactions WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM applications WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully', 'success')
    return redirect(url_for('admin') + '#wallet')

@app.route('/download_receipt/<int:app_id>')
def download_receipt(app_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    app_row = conn.execute('SELECT * FROM applications WHERE id=?', (app_id,)).fetchone()
    conn.close()
    if app_row and app_row['receipt']:
        return send_from_directory(app.config['UPLOAD_FOLDER'], app_row['receipt'],
                                   as_attachment=True,
                                   download_name=f'PAN_Receipt_{app_id}.pdf')
    flash('Receipt not found', 'error')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
