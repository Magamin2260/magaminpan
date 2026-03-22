from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os
from datetime import datetime
from werkzeug.utils import secure_filename

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
PAN_COST    = 150  # Rs. per application

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = 'pan_card_secret_2024'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def allowed_file(f):
    return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file, prefix):
    if file and file.filename and allowed_file(file.filename):
        ext = file.filename.rsplit('.',1)[1].lower()
        fname = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(os.path.join(UPLOAD_FOLDER, fname))
        return fname
    return ''

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_wallet(user_id):
    conn = get_db()
    row = conn.execute('SELECT balance FROM wallets WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    return float(row['balance']) if row else 0.0

def init_db():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS wallets (
        user_id  INTEGER PRIMARY KEY,
        balance  REAL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS wallet_txns (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        amount      REAL,
        txn_type    TEXT,   -- 'credit' or 'debit'
        description TEXT,
        created_at  TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        last_name TEXT, first_name TEXT, middle_name TEXT,
        full_name TEXT, dob TEXT, gender TEXT, father_name TEXT,
        aadhaar TEXT, mobile TEXT, email TEXT, address TEXT,
        city TEXT, state TEXT, pincode TEXT, pan_type TEXT,
        app_category TEXT DEFAULT 'New PAN',
        correction_fields TEXT DEFAULT '',
        photo TEXT, signature TEXT, aadhaar_doc TEXT, additional_doc TEXT,
        status TEXT DEFAULT 'Pending', submitted_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    cur.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES (?,?,?)",
                ('admin','admin123','admin'))

    # Migrations
    for col_def in [
        "ALTER TABLE applications ADD COLUMN correction_fields TEXT DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN last_name TEXT DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN first_name TEXT DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN middle_name TEXT DEFAULT ''",
        "ALTER TABLE applications ADD COLUMN app_category TEXT DEFAULT 'New PAN'",
        "ALTER TABLE applications ADD COLUMN receipt TEXT DEFAULT ''",
    ]:
        try: cur.execute(col_def)
        except: pass

    conn.commit(); conn.close()

# ── Auth ─────────────────────────────────────────────────────
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password=?',(u,p)).fetchone()
        conn.close()
        if user:
            session.update({'user_id':user['id'],'username':user['username'],'role':user['role']})
            return redirect(url_for('admin') if user['role']=='admin' else url_for('dashboard'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        try:
            conn = get_db()
            conn.execute('INSERT INTO users (username,password) VALUES (?,?)',
                         (request.form['username'], request.form['password']))
            # Create wallet for new user
            conn.execute('INSERT INTO wallets (user_id,balance) SELECT id,0 FROM users WHERE username=?',
                         (request.form['username'],))
            conn.commit(); conn.close()
            flash('Account created! Please login.')
            return redirect(url_for('login'))
        except: flash('Username already exists.')
    return render_template('login.html', register=True)

# ── User Dashboard ────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid  = session['user_id']
    conn = get_db()
    apps    = conn.execute('SELECT * FROM applications WHERE user_id=? ORDER BY submitted_at DESC',(uid,)).fetchall()
    txns    = conn.execute('SELECT * FROM wallet_txns WHERE user_id=? ORDER BY created_at DESC LIMIT 10',(uid,)).fetchall()
    conn.close()
    balance = get_wallet(uid)
    return render_template('dashboard.html', applications=apps, balance=balance,
                           txns=txns, pan_cost=PAN_COST)

# ── Apply ─────────────────────────────────────────────────────
@app.route('/apply', methods=['GET','POST'])
def apply():
    if 'user_id' not in session: return redirect(url_for('login'))
    uid     = session['user_id']
    balance = get_wallet(uid)

    if request.method == 'POST':
        # Wallet check
        if balance < PAN_COST:
            flash(f'Insufficient wallet balance! You need ₹{PAN_COST}. Current balance: ₹{balance:.2f}')
            return redirect(url_for('apply'))

        f = request.form
        cf_map = {
            'Name':             f.get('cf_name','No Change'),
            'Date of Birth':    f.get('cf_dob','No Change'),
            "Father's Name":    f.get('cf_father','No Change'),
            'Gender':           f.get('cf_gender','No Change'),
            'Address':          f.get('cf_address','No Change'),
            'Photo / Signature':f.get('cf_photo','No Change'),
        }
        correction_fields = ', '.join(k for k,v in cf_map.items() if v=='Correction')
        photo       = save_file(request.files.get('photo'),          f'photo_{uid}')
        signature   = save_file(request.files.get('signature'),      f'sign_{uid}')
        aadhaar_doc = save_file(request.files.get('aadhaar_doc'),    f'aadhaar_{uid}')
        add_doc     = save_file(request.files.get('additional_doc'), f'adddoc_{uid}')

        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        conn = get_db()

        # Deduct wallet
        conn.execute('UPDATE wallets SET balance=balance-? WHERE user_id=?', (PAN_COST, uid))
        conn.execute('''INSERT INTO wallet_txns (user_id,amount,txn_type,description,created_at)
                        VALUES (?,?,?,?,?)''',
                     (uid, PAN_COST, 'debit', f"PAN Application — {f['full_name']}", now))

        conn.execute('''INSERT INTO applications
            (user_id,last_name,first_name,middle_name,full_name,dob,gender,father_name,
             aadhaar,mobile,email,address,city,state,pincode,pan_type,app_category,
             correction_fields,photo,signature,aadhaar_doc,additional_doc,status,submitted_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (uid,f['last_name'],f['first_name'],f.get('middle_name',''),
             f['full_name'],f['dob'],f['gender'],f['father_name'],
             f['aadhaar'],f['mobile'],f['email'],f['address'],f['city'],
             f['state'],f['pincode'],f['pan_type'],f['app_category'],correction_fields,
             photo,signature,aadhaar_doc,add_doc,'Pending',now))

        conn.commit(); conn.close()
        flash(f'Application submitted! ₹{PAN_COST} deducted from wallet.')
        return redirect(url_for('dashboard'))

    return render_template('form.html', balance=balance, pan_cost=PAN_COST)

# ── Admin ─────────────────────────────────────────────────────
@app.route('/admin')
def admin():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn  = get_db()
    apps  = conn.execute('''SELECT a.*,u.username FROM applications a
                            JOIN users u ON a.user_id=u.id
                            ORDER BY a.submitted_at DESC''').fetchall()
    users = conn.execute('''SELECT u.id, u.username, u.role,
                                   COALESCE(w.balance,0) as balance,
                                   COUNT(a.id) as app_count
                            FROM users u
                            LEFT JOIN wallets w ON u.id=w.user_id
                            LEFT JOIN applications a ON u.id=a.user_id
                            WHERE u.role != 'admin'
                            GROUP BY u.id
                            ORDER BY u.username''').fetchall()
    txns  = conn.execute('''SELECT t.*, u.username FROM wallet_txns t
                            JOIN users u ON t.user_id=u.id
                            ORDER BY t.created_at DESC LIMIT 50''').fetchall()
    conn.close()
    return render_template('admin.html', applications=apps, users=users,
                           wallet_txns=txns, pan_cost=PAN_COST)

@app.route('/admin/detail/<int:app_id>')
def app_detail(app_id):
    if session.get('role') != 'admin': return jsonify({}), 403
    conn = get_db()
    d    = conn.execute('SELECT a.*,u.username FROM applications a JOIN users u ON a.user_id=u.id WHERE a.id=?',(app_id,)).fetchone()
    conn.close()
    if not d: return jsonify({}), 404
    return jsonify(dict(d))

@app.route('/admin/update/<int:app_id>', methods=['POST'])
def update_status(app_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    status  = request.form['status']
    conn    = get_db()
    receipt = save_file(request.files.get('receipt'), f'receipt_{app_id}')
    if receipt:
        conn.execute('UPDATE applications SET status=?, receipt=? WHERE id=?', (status, receipt, app_id))
    else:
        conn.execute('UPDATE applications SET status=? WHERE id=?', (status, app_id))
    conn.commit(); conn.close()
    flash(f'Application #{app_id} updated to {status}.' + (' Receipt uploaded.' if receipt else ''))
    return redirect(url_for('admin'))

@app.route('/receipt/<int:app_id>')
def download_receipt(app_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    # Users can only download their own receipt; admins can download any
    if session.get('role') == 'admin':
        app_data = conn.execute('SELECT receipt FROM applications WHERE id=?',(app_id,)).fetchone()
    else:
        app_data = conn.execute('SELECT receipt FROM applications WHERE id=? AND user_id=?',(app_id, session['user_id'])).fetchone()
    conn.close()
    if not app_data or not app_data['receipt']:
        flash('Receipt not available yet.')
        return redirect(url_for('dashboard'))
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, app_data['receipt'], as_attachment=True,
                               download_name=f'PAN_Receipt_{app_id}.pdf')

# ── Admin: Add wallet balance ─────────────────────────────────
@app.route('/admin/user/delete/<int:uid>', methods=['POST'])
def admin_delete_user(uid):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db()
    uname = conn.execute('SELECT username FROM users WHERE id=?',(uid,)).fetchone()
    conn.execute('DELETE FROM applications WHERE user_id=?',(uid,))
    conn.execute('DELETE FROM wallet_txns WHERE user_id=?',(uid,))
    conn.execute('DELETE FROM wallets WHERE user_id=?',(uid,))
    conn.execute('DELETE FROM users WHERE id=?',(uid,))
    conn.commit(); conn.close()
    flash(f'User "{uname["username"] if uname else uid}" deleted successfully.')
    return redirect(url_for('admin'))

@app.route('/admin/wallet/add', methods=['POST'])
def admin_wallet_add():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    user_id = int(request.form['user_id'])
    amount  = float(request.form['amount'])
    note    = request.form.get('note','Admin top-up').strip() or 'Admin top-up'
    now     = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = get_db()
    # Ensure wallet row exists
    conn.execute('INSERT OR IGNORE INTO wallets (user_id,balance) VALUES (?,0)', (user_id,))
    conn.execute('UPDATE wallets SET balance=balance+? WHERE user_id=?', (amount, user_id))
    conn.execute('''INSERT INTO wallet_txns (user_id,amount,txn_type,description,created_at)
                    VALUES (?,?,?,?,?)''', (user_id, amount, 'credit', note, now))
    conn.commit(); conn.close()
    flash(f'₹{amount:.0f} added to wallet successfully.')
    return redirect(url_for('admin'))

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM applications WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM wallet_txns WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM wallets WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit(); conn.close()
    flash('User deleted successfully.')
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
