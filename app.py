from flask import Flask, render_template, request, redirect, url_for, session, g, send_from_directory
from datetime import datetime
import uuid
import os
import secrets
import sqlite3
import ast
import base64
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO

# PDF generation (reportlab)
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. PDF attachments will not be generated.")

app = Flask(__name__)
app.secret_key = "construction-secret-key"

# ─────────────────────────────────────────────
# DATABASE SETUP (SQLite)
# ─────────────────────────────────────────────
DATABASE = 'construction.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def ensure_columns(cursor, table_name, columns):
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column_name, column_type in columns.items():
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

def seed_user(cursor, user_id, username, email, password, role, employee_type=None, employee_number=None, pm_code=None):
    existing = cursor.execute(
        "SELECT * FROM users WHERE id = ? OR username = ? OR email = ?",
        (user_id, username, email)
    ).fetchone()
    if existing:
        cursor.execute('''
            UPDATE users
            SET username = ?, email = ?, password = ?, role = ?, employee_type = ?,
                employee_number = ?, pm_code = ?, assigned_tasks = COALESCE(assigned_tasks, '[]')
            WHERE id = ?
        ''', (username, email, password, role, employee_type, employee_number, pm_code, existing["id"]))
    else:
        cursor.execute('''
            INSERT INTO users (id, username, email, password, role, employee_type, employee_number, pm_code, assigned_tasks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, email, password, role, employee_type, employee_number, pm_code, "[]"))

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                employee_type TEXT,
                employee_number TEXT,
                pm_code TEXT,
                assigned_tasks TEXT
            )
        ''')
        
        # Project inquiries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_inquiries (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT,
                project_scope TEXT,
                location TEXT,
                budget REAL,
                deadline TEXT,
                client_name TEXT,
                client_email TEXT,
                project_details TEXT,
                sketches TEXT,
                site_photos TEXT,
                status TEXT
            )
        ''')

        ensure_columns(cursor, "project_inquiries", {
            "client_phone": "TEXT",
            "project_type": "TEXT",
            "floors": "INTEGER",
            "area_sqm": "REAL",
            "soil_type": "TEXT",
            "ai_estimated_area": "REAL",
            "payment_milestone": "TEXT",
            "env_impact": "INTEGER DEFAULT 0"
        })
        
        # Agreements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agreements (
                id TEXT PRIMARY KEY,
                inquiry_id TEXT,
                client_name TEXT,
                client_email TEXT,
                project_scope TEXT,
                budget REAL,
                deadline TEXT,
                status TEXT,
                signature_token TEXT,
                signed_at TEXT,
                created_at TEXT,
                client_signature TEXT,
                contract_title TEXT,
                contract_number TEXT,
                contract_date TEXT,
                milestones TEXT,
                payment_terms TEXT,
                warranties TEXT,
                legal_clauses TEXT,
                legal_documents TEXT,
                pm_name TEXT,
                pm_signature_method TEXT,
                pm_signature_date TEXT,
                pm_confirmed INTEGER,
                pm_signed_file TEXT,
                client_message TEXT
            )
        ''')
        
        # Payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                milestone TEXT,
                amount REAL,
                payment_method TEXT,
                account_number TEXT,
                expiry TEXT,
                cvv TEXT,
                mobile_number TEXT,
                pin_reference TEXT,
                bank_name TEXT,
                eft_account TEXT,
                status TEXT,
                account_number_masked TEXT
            )
        ''')
        
        # BOQ submissions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS boq_submissions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT,
                terrain_inspection TEXT,
                infrastructure_eval TEXT,
                soil_condition TEXT,
                utility_access TEXT,
                technical_risks TEXT,
                risk_mitigation TEXT,
                survey_report TEXT,
                survey_photos TEXT,
                materials TEXT,
                labour_rate TEXT,
                machinery_rate TEXT,
                other_resources TEXT,
                overhead_percent TEXT,
                contingency_percent TEXT,
                cost TEXT,
                quote_ref TEXT,
                quote_notes TEXT,
                status TEXT
            )
        ''')
        
        # Team allocations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_allocations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT,
                start_date TEXT,
                end_date TEXT,
                managers TEXT,
                crews TEXT,
                availability_notes TEXT,
                machinery_list TEXT,
                machinery_date TEXT,
                machinery_duration TEXT,
                machinery_conflicts TEXT,
                role TEXT,
                skill_rating TEXT,
                location TEXT,
                assigned_workers TEXT,
                reserve_managers INTEGER,
                reserve_crews INTEGER,
                reserve_machinery INTEGER,
                reserve_vehicles INTEGER,
                calendar_start TEXT,
                calendar_end TEXT,
                event_name TEXT,
                calendar_notes TEXT,
                status TEXT
            )
        ''')
        
        # Purchase orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                supplier TEXT,
                materials_list TEXT,
                unit_prices TEXT,
                po_reference TEXT,
                boq_reference TEXT,
                total_quantity_summary TEXT,
                amount REAL,
                high_value INTEGER,
                auth_manager TEXT,
                auth_code TEXT,
                auth_date TEXT,
                po_delivery_method TEXT,
                supplier_email TEXT,
                expected_delivery TEXT,
                delivery_site TEXT,
                tracking_email INTEGER,
                tracking_sms INTEGER,
                tracking_dashboard INTEGER,
                procurement_notes TEXT,
                status TEXT,
                boq_filename TEXT,
                auth_filename TEXT
            )
        ''')
        
        # Dispatches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dispatches (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                machinery_list TEXT,
                transport_date TEXT,
                transport_arrival_time TEXT,
                transport_provider TEXT,
                vehicle_reg TEXT,
                office_type TEXT,
                power_source TEXT,
                power_kva TEXT,
                office_setup_date TEXT,
                crew_name TEXT,
                date TEXT,
                shift TEXT,
                accommodation TEXT,
                crew_transport TEXT,
                site_status TEXT,
                check_machinery INTEGER,
                check_office INTEGER,
                check_crews INTEGER,
                check_safety INTEGER,
                confirmed_by TEXT,
                confirmation_datetime TEXT,
                completion_remarks TEXT,
                status TEXT,
                office_photo_filename TEXT
            )
        ''')
        
        # Progress reports table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress_reports (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT,
                project_phase TEXT,
                completed_tasks TEXT,
                percentage INTEGER,
                completion_date TEXT,
                progress_update TEXT,
                photo_descriptions TEXT,
                latitude TEXT,
                longitude TEXT,
                has_delay TEXT,
                delay_description TEXT,
                recovery_plan TEXT,
                change_requirements TEXT,
                change_ref TEXT,
                milestone TEXT,
                client_email TEXT,
                notify_client INTEGER,
                client_message TEXT,
                attach_photos INTEGER,
                internal_notes TEXT,
                status TEXT,
                photos TEXT
            )
        ''')
        
        # Site surveys table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS site_surveys (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                assigned_to TEXT,
                created_at TEXT,
                location TEXT,
                terrain_description TEXT,
                infrastructure_assessment TEXT,
                soil_conditions TEXT,
                utility_access TEXT,
                survey_notes TEXT,
                technical_risks TEXT,
                risk_impact TEXT,
                risk_mitigation TEXT,
                flag_qs INTEGER,
                status TEXT,
                report_filename TEXT,
                site_photos TEXT,
                aerial_photos TEXT
            )
        ''')
        
        # Safety audits table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS safety_audits (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                audit_date TEXT,
                auditor TEXT,
                site_location TEXT,
                weather TEXT,
                audit_scope TEXT,
                ppe_hard_hat INTEGER,
                ppe_vest INTEGER,
                ppe_gloves INTEGER,
                ppe_safety_glasses INTEGER,
                ppe_harness INTEGER,
                housekeeping_clear INTEGER,
                housekeeping_signage INTEGER,
                housekeeping_lighting INTEGER,
                housekeeping_fire INTEGER,
                equipment_guards INTEGER,
                equipment_certified INTEGER,
                equipment_emergency_stops INTEGER,
                checklist_notes TEXT,
                hazards TEXT,
                overall_risk TEXT,
                corrective_actions TEXT,
                action_owner TEXT,
                audit_conclusion TEXT,
                auditor_signature TEXT,
                audit TEXT,
                audit_finalized INTEGER,
                status TEXT,
                hazard_photos TEXT
            )
        ''')
        
        db.commit()
        
        seed_user(cursor, "admin1", "admin", "admin@system.com", "admin123", "admin")
        seed_user(cursor, "client1", "client", "client@muhle.co.za", "client123", "client")
        seed_user(cursor, "pm1", "projectmanager", "pm@muhle.co.za", "pm123", "project_manager", pm_code="PM-001")
        seed_user(cursor, "eng1", "engineer", "engineer@muhle.co.za", "eng123", "employee", "engineer", "ENG-001")
        seed_user(cursor, "qs1", "quantitysurveyor", "qs@muhle.co.za", "qs123", "employee", "quantity_surveyor", "QS-001")
        seed_user(cursor, "res1", "resourcemanager", "resource@muhle.co.za", "res123", "employee", "resource_manager", "RES-001")
        seed_user(cursor, "proc1", "procurement", "procurement@muhle.co.za", "proc123", "employee", "procurement_officer", "PROC-001")
        seed_user(cursor, "log1", "logistics", "logistics@muhle.co.za", "log123", "employee", "logistics_coordinator", "LOG-001")
        seed_user(cursor, "sm1", "sitemanager", "sitemanager@muhle.co.za", "sm123", "employee", "site_manager", "SM-001")
        seed_user(cursor, "fin1", "finance", "finance@muhle.co.za", "fin123", "employee", "finance_officer", "FIN-001")
        seed_user(cursor, "emp1", "surveyor", "surveyor@test.com", "survey123", "employee", "survey_operator", "E-1001")
        seed_user(cursor, "emp2", "safety", "safety@test.com", "safety123", "employee", "safety_officer", "E-1002")
        db.commit()

init_db()

# ─────────────────────────────────────────────
# EMAIL / SMS CONFIGURATION
# ─────────────────────────────────────────────
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = 'muhle.construction.za@gmail.com'
SMTP_PASSWORD = 'suzc jave mpgf lrou'
FROM_EMAIL = 'muhle.construction.za@gmail.com'

TWILIO_ACCOUNT_SID = ''
TWILIO_AUTH_TOKEN = ''
TWILIO_PHONE_NUMBER = ''

def send_email_with_attachment(to_email, subject, body, attachment_bytes=None, attachment_filename="agreement.pdf"):
    """Send email with optional PDF attachment."""
    if not to_email:
        print(f"Email not sent: no recipient for subject {subject}")
        return False
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"\n✉️ [DEMO EMAIL] From: {FROM_EMAIL} To: {to_email}\nSubject: {subject}\nBody: {body}\n")
        if attachment_bytes:
            print(f"📎 [ATTACHMENT] {attachment_filename} (size: {len(attachment_bytes)} bytes)")
        return True
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if attachment_bytes:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{attachment_filename}"')
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {to_email} from {FROM_EMAIL}")
        return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

def send_sms(to_phone_number, message):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        print(f"\n📱 [DEMO SMS] To: {to_phone_number}\nMessage: {message}\n")
        return True
    try:
        # from twilio.rest import Client
        # client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # client.messages.create(body=message, from_=TWILIO_PHONE_NUMBER, to=to_phone_number)
        print(f"SMS sent to {to_phone_number}")
        return True
    except Exception as e:
        print(f"SMS sending failed: {e}")
        return False

# ─────────────────────────────────────────────
# PDF GENERATION
# ─────────────────────────────────────────────
def generate_agreement_pdf(agreement_data):
    """Generate a PDF contract from agreement data and return BytesIO object."""
    if not REPORTLAB_AVAILABLE:
        return None
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "SERVICE AGREEMENT")
    y -= 30

    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Contract Title: {agreement_data.get('contract_title', 'N/A')}")
    y -= 20
    c.drawString(50, y, f"Contract Number: {agreement_data.get('contract_number', 'N/A')}")
    y -= 20
    c.drawString(50, y, f"Date: {agreement_data.get('contract_date', datetime.now().strftime('%Y-%m-%d'))}")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Parties")
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Client: {agreement_data.get('client_name', 'N/A')}")
    y -= 20
    c.drawString(50, y, f"Client Email: {agreement_data.get('client_email', 'N/A')}")
    y -= 20
    c.drawString(50, y, f"Project Manager: {agreement_data.get('pm_name', 'N/A')}")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Project Scope")
    y -= 20
    c.setFont("Helvetica", 10)
    scope_text = agreement_data.get('project_scope', 'N/A')
    lines = simpleSplit(scope_text, "Helvetica", 10, width - 100)
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)
        c.drawString(50, y, line)
        y -= 15
    y -= 15

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Financials")
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Total Budget: ZAR {float(agreement_data.get('budget', 0)):,.2f}")
    y -= 20
    c.drawString(50, y, f"Milestones: {agreement_data.get('milestones', 'N/A')}")
    y -= 20
    c.drawString(50, y, f"Payment Terms: {agreement_data.get('payment_terms', 'N/A')}")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Additional Clauses")
    y -= 20
    c.setFont("Helvetica", 10)
    warranties = agreement_data.get('warranties', 'N/A')
    lines = simpleSplit(warranties, "Helvetica", 10, width - 100)
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)
        c.drawString(50, y, line)
        y -= 15
    y -= 10

    legal = agreement_data.get('legal_clauses', 'N/A')
    lines = simpleSplit(legal, "Helvetica", 10, width - 100)
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)
        c.drawString(50, y, line)
        y -= 15

    # Signature block
    c.showPage()
    y = height - 50
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Signatures")
    y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(50, y, "Project Manager:")
    c.line(200, y+5, 400, y+5)
    c.drawString(200, y-10, agreement_data.get('pm_name', '_____________'))
    y -= 40
    c.drawString(50, y, "Client Signature:")
    c.line(200, y+5, 400, y+5)
    c.drawString(200, y-10, "(To be signed electronically)")

    c.save()
    buffer.seek(0)
    return buffer

# ─────────────────────────────────────────────
# FILE UPLOADS
# ─────────────────────────────────────────────
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_files(files, field_name):
    saved_files = []
    for file in files.getlist(field_name):
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved_files.append(filename)
    return saved_files

def save_base64_image(data_url, prefix):
    if not data_url or "," not in data_url:
        return None
    header, encoded = data_url.split(",", 1)
    if "image/" not in header:
        return None
    ext = header.split("image/", 1)[1].split(";", 1)[0].lower()
    if ext == "jpeg":
        ext = "jpg"
    if ext not in {"png", "jpg", "gif"}:
        return None
    filename = secure_filename(f"{prefix}_{uuid.uuid4().hex}.{ext}")
    with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), "wb") as image_file:
        image_file.write(base64.b64decode(encoded))
    return filename

def parse_file_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return []

def inquiry_to_dict(inquiry):
    data = dict(inquiry)
    data["sketches"] = parse_file_list(data.get("sketches"))
    data["site_photos"] = parse_file_list(data.get("site_photos"))
    return data

def get_inquiries(status=None):
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM project_inquiries WHERE status = ? ORDER BY timestamp DESC",
            (status,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM project_inquiries ORDER BY timestamp DESC").fetchall()
    return [inquiry_to_dict(row) for row in rows]

def update_inquiry_from_form(inquiry_id):
    current_user = get_current_user()
    client_email = request.form.get("client_email") or (current_user.get("email") if current_user else None)
    sketches = save_uploaded_files(request.files, "sketches") if request.files else []
    site_photos = save_uploaded_files(request.files, "site_photos") if request.files else []
    camera_photo = save_base64_image(request.form.get("site_photo_base64"), "site_photo")
    if camera_photo:
        site_photos.append(camera_photo)

    fields = {
        "project_scope": request.form.get("project_scope"),
        "location": request.form.get("location"),
        "budget": float(request.form.get("budget")) if request.form.get("budget") else 0,
        "deadline": request.form.get("deadline"),
        "client_name": request.form.get("client_name"),
        "client_email": client_email,
        "client_phone": request.form.get("client_phone"),
        "project_type": request.form.get("project_type"),
        "floors": int(request.form.get("floors")) if request.form.get("floors") else None,
        "area_sqm": float(request.form.get("area_sqm")) if request.form.get("area_sqm") else None,
        "soil_type": ", ".join(request.form.getlist("soil_type")),
        "ai_estimated_area": float(request.form.get("ai_estimated_area")) if request.form.get("ai_estimated_area") else None,
        "payment_milestone": request.form.get("payment_milestone"),
        "env_impact": 1 if request.form.get("env_impact") == "on" else 0,
        "project_details": request.form.get("project_details"),
    }

    assignments = [f"{key} = ?" for key in fields]
    values = list(fields.values())
    if sketches:
        assignments.append("sketches = ?")
        values.append(str(sketches))
    if site_photos:
        assignments.append("site_photos = ?")
        values.append(str(site_photos))
    values.append(inquiry_id)

    db = get_db()
    db.execute(f"UPDATE project_inquiries SET {', '.join(assignments)} WHERE id = ?", values)
    db.commit()

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    if not login_required():
        return redirect(url_for('login'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(user) if user else None

def login_required():
    return get_current_user() is not None

def admin_required():
    user = get_current_user()
    return user and user["role"] == "admin"

def module_for_employee_type(employee_type):
    return {
        "engineer": "progress",
        "quantity_surveyor": "boq",
        "resource_manager": "team",
        "procurement_officer": "orders",
        "logistics_coordinator": "dispatch",
        "site_manager": "progress",
        "finance_officer": "payments",
        "survey_operator": "site_survey",
        "safety_officer": "safety",
    }.get(employee_type, "dashboard")

# ─────────────────────────────────────────────
# AUTHENTICATION ROUTES
# ─────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        if not role:
            role = 'client'
        
        employee_type = None
        employee_number = None
        pm_code = None
        
        if role == 'employee':
            employee_type = request.form.get("employee_type")
            employee_number = request.form.get("employee_number")
        elif role == 'project_manager':
            pm_code = request.form.get("pm_code")
        
        db = get_db()
        existing = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            error = "User already exists"
        else:
            user_id = str(uuid.uuid4())
            db.execute('''
                INSERT INTO users (id, username, email, password, role, employee_type, employee_number, pm_code, assigned_tasks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, email, password, role, employee_type, employee_number, pm_code, "[]"))
            db.commit()
            return redirect(url_for('login'))
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?",
            (username, username, password)
        ).fetchone()
        if user:
            session["user_id"] = user["id"]
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    message = None
    if request.method == 'POST':
        email = request.form.get("email")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            new_password = secrets.token_urlsafe(12)
            db.execute("UPDATE users SET password = ? WHERE email = ?", (new_password, email))
            db.commit()
            subject = "Password Reset - MUHLE CONSTRUCTION"
            body = f"Hello {user['username']},\n\nYour password has been reset to: {new_password}\n\nPlease login and change your password immediately.\n\nRegards,\nMUHLE CONSTRUCTION"
            send_email_with_attachment(email, subject, body)
            message = "Password reset successful. A new secure password has been sent to your email."
        else:
            message = "Email not found"
    return render_template('forgot_password.html', message=message)

# ─────────────────────────────────────────────
# DASHBOARD (role‑based)
# ─────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    db = get_db()
    all_users = db.execute("SELECT * FROM users").fetchall()
    all_inquiries = get_inquiries()
    all_boqs = db.execute("SELECT * FROM boq_submissions").fetchall()
    all_orders = db.execute("SELECT * FROM purchase_orders").fetchall()
    all_payments = db.execute("SELECT * FROM payments").fetchall()
    all_site_surveys = db.execute("""
        SELECT site_surveys.*, users.username AS submitted_by
        FROM site_surveys
        LEFT JOIN users ON users.id = site_surveys.user_id
        ORDER BY site_surveys.created_at DESC
    """).fetchall()
    all_safety_audits = db.execute("SELECT * FROM safety_audits ORDER BY created_at DESC").fetchall()
    
    if user['role'] == 'admin':
        stats = {
            "total_users": len(all_users),
            "project_managers": len([u for u in all_users if u["role"] == "project_manager"]),
            "clients": len([u for u in all_users if u["role"] == "client"]),
            "employees": len([u for u in all_users if u["role"] == "employee"]),
            "total_inquiries": len(all_inquiries),
            "total_boqs": len(all_boqs),
            "total_orders": len(all_orders),
            "total_payments": len(all_payments)
        }
        return render_template("admin_dashboard.html", 
                               stats=stats, 
                               users=all_users,
                               inquiries=all_inquiries,
                               pending_inquiries=[i for i in all_inquiries if i["status"] == "pending_review"],
                               site_surveys=all_site_surveys,
                               safety_audits=all_safety_audits,
                               current_user=user)
    elif user['role'] == 'project_manager':
        my_inquiries = [dict(i) for i in all_inquiries if i["user_id"] == user["id"]]
        my_boqs = [dict(b) for b in all_boqs if b["user_id"] == user["id"]]
        stats = {"inquiries": len(my_inquiries), "boqs": len(my_boqs)}
        return render_template("user_dashboard.html", stats=stats, inquiries=my_inquiries,
                               pending_inquiries=[i for i in all_inquiries if i["status"] == "pending_review"],
                               boqs=my_boqs, current_user=user)
    elif user['role'] == 'client':
        my_inquiries = [dict(i) for i in all_inquiries if i["client_email"] == user["email"] or i["user_id"] == user["id"]]
        my_agreements = db.execute("SELECT * FROM agreements WHERE client_email = ? ORDER BY created_at DESC", (user["email"],)).fetchall()
        my_payments = db.execute("SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()
        return render_template("client_dashboard.html", 
                               inquiries=my_inquiries,
                               agreements=my_agreements,
                               payments=my_payments, 
                               current_user=user)
    elif user['role'] == 'employee':
        employee_type = user.get('employee_type')
        if employee_type == 'survey_operator':
            assigned_surveys = db.execute("SELECT * FROM site_surveys WHERE assigned_to = ? OR user_id = ? ORDER BY created_at DESC", (user["id"], user["id"])).fetchall()
            return render_template("employee_dashboard.html", tasks=assigned_surveys,
                                   employee_type=employee_type, current_user=user,
                                   module_endpoint=module_for_employee_type(employee_type))
        elif employee_type == 'safety_officer':
            safety_tasks = db.execute("SELECT * FROM safety_audits WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()
            return render_template("employee_dashboard.html", tasks=safety_tasks,
                                   employee_type=employee_type, current_user=user,
                                   module_endpoint=module_for_employee_type(employee_type))
        else:
            return render_template("employee_dashboard.html", tasks=[],
                                   employee_type=employee_type, current_user=user,
                                   module_endpoint=module_for_employee_type(employee_type))
    else:
        return redirect(url_for('login'))

# ─────────────────────────────────────────────
# ADMIN - USER MANAGEMENT
# ─────────────────────────────────────────────
@app.route('/users', methods=['GET', 'POST'])
def users():
    if not login_required() or not admin_required():
        return "Access Denied"
    db = get_db()
    if request.method == 'POST':
        action = request.form.get("action")
        if action == "add":
            user_id = str(uuid.uuid4())
            db.execute('''
                INSERT INTO users (id, username, email, password, role, employee_type, employee_number, pm_code, assigned_tasks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, request.form.get("username"), request.form.get("email") or request.form.get("username") + "@mail.com",
                  request.form.get("password"), request.form.get("role"),
                  request.form.get("employee_type") if request.form.get("role") == 'employee' else None,
                  request.form.get("employee_number"), request.form.get("pm_code"), "[]"))
            db.commit()
        elif action == "update_role":
            user_id = request.form.get("user_id")
            new_role = request.form.get("new_role")
            new_employee_type = request.form.get("new_employee_type") if new_role == 'employee' else None
            db.execute("UPDATE users SET role = ?, employee_type = ? WHERE id = ?", (new_role, new_employee_type, user_id))
            db.commit()
    all_users = db.execute("SELECT * FROM users").fetchall()
    return render_template('users.html', users=all_users, current_user=get_current_user())

# ─────────────────────────────────────────────
# PROJECT INQUIRY (creates pending agreement)
# ─────────────────────────────────────────────
@app.route('/project_inquiry', methods=['GET', 'POST'])
def project_inquiry():
    if not login_required():
        return redirect(url_for('login'))
    current_user = get_current_user()
    if request.method == 'POST':
        inquiry_id = str(uuid.uuid4())
        user_id = session.get("user_id")
        timestamp = datetime.now().isoformat()
        status = "pending_review"
        
        db = get_db()
        db.execute('''
            INSERT INTO project_inquiries 
            (id, user_id, timestamp, status)
            VALUES (?, ?, ?, ?)
        ''', (inquiry_id, user_id, timestamp, status))
        db.commit()
        update_inquiry_from_form(inquiry_id)
        
        # Create a placeholder agreement record (status pending, but no signature token yet)
        # The actual token will be generated when the PM creates the full agreement.
        # For now, we just create an empty agreement (optional, can be omitted).
        # We'll keep the old behaviour for backward compatibility, but the real signing happens after PM sends agreement.
        # To avoid confusion, we do NOT send a signature link here.
        return redirect(url_for('dashboard'))
    return render_template("project_inquiry.html", current_user=current_user)

# ─────────────────────────────────────────────
# SIGN AGREEMENT (client signing via token)
# ─────────────────────────────────────────────
@app.route('/sign_agreement/<token>', methods=['GET', 'POST'])
def sign_agreement(token):
    db = get_db()
    agreement = db.execute("SELECT * FROM agreements WHERE signature_token = ?", (token,)).fetchone()
    if not agreement:
        return "Invalid or expired link", 404
    
    # If already signed, show a different page
    if agreement["status"] == "signed":
        return render_template("agreement_already_signed.html", agreement=dict(agreement))
    
    # Only allow signing if status is 'pending' (i.e., PM has sent the agreement)
    if agreement["status"] != "pending":
        return "This agreement cannot be signed. Current status: " + agreement["status"], 400
    
    if request.method == 'POST':
        signature = request.form.get("signature")
        if not signature:
            return "Please provide your full name as signature.", 400
        db.execute('''
            UPDATE agreements SET status = ?, signed_at = ?, client_signature = ?
            WHERE signature_token = ?
        ''', ("signed", datetime.now().isoformat(), signature, token))
        db.commit()
        # Update related inquiry status
        db.execute("UPDATE project_inquiries SET status = 'agreement_signed' WHERE id = ?", (agreement["inquiry_id"],))
        db.commit()
        # Notify PM
        pm_user = db.execute("SELECT * FROM users WHERE role = 'project_manager' LIMIT 1").fetchone()
        if pm_user:
            send_email_with_attachment(pm_user["email"], f"Agreement signed by {agreement['client_name']}",
                                       f"Client {agreement['client_name']} has signed the service agreement.\n\nContract: {agreement.get('contract_title', 'N/A')}")
        return redirect(url_for('agreement_confirmation'))
    return render_template("sign_agreement.html", agreement=dict(agreement))

@app.route('/client/sign_agreement')
def client_sign_agreement():
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    db = get_db()
    pending = db.execute("SELECT * FROM agreements WHERE client_email = ? AND status = 'pending'", (user["email"],)).fetchone()
    if pending:
        return redirect(url_for('sign_agreement', token=pending["signature_token"]))
    else:
        # Show a friendly page instead of raw error
        return render_template("no_pending_agreement.html", current_user=user)

@app.route('/agreement-confirmation')
def agreement_confirmation():
    return render_template("agreement_confirmation.html")

# ─────────────────────────────────────────────
# PROJECT INQUIRIES LIST & ACTIONS (PM)
# ─────────────────────────────────────────────
@app.route('/project_inquiries_list')
def project_inquiries_list():
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] not in ['project_manager', 'admin']:
        return "Access Denied", 403
    db = get_db()
    inquiries = get_inquiries()
    return render_template("project_inquiries_list.html", inquiries=inquiries, current_user=user)

@app.route('/inquiry/<inquiry_id>')
def view_inquiry_detail(inquiry_id):
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] not in ['project_manager', 'admin']:
        return "Access Denied", 403
    db = get_db()
    inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if not inquiry:
        return "Inquiry not found", 404
    return render_template("inquiry_detail.html", inquiry=inquiry_to_dict(inquiry), current_user=user)

@app.route('/inquiry/<inquiry_id>/edit', methods=['GET', 'POST'])
def edit_inquiry(inquiry_id):
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    db = get_db()
    inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if not inquiry:
        return "Inquiry not found", 404
    if user['role'] not in ['project_manager', 'admin'] and inquiry["user_id"] != user["id"]:
        return "Access Denied", 403
    if request.method == 'POST':
        update_inquiry_from_form(inquiry_id)
        return redirect(url_for('view_inquiry_detail', inquiry_id=inquiry_id))
    return render_template("project_inquiry.html", current_user=user, inquiry=inquiry_to_dict(inquiry), edit_mode=True)

@app.route('/approve_inquiry/<inquiry_id>')
def approve_inquiry(inquiry_id):
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] not in ['project_manager', 'admin']:
        return "Access Denied", 403
    db = get_db()
    inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if not inquiry:
        return "Inquiry not found", 404
    if inquiry["status"] != "pending_review":
        return "Inquiry already processed", 400
    db.execute("UPDATE project_inquiries SET status = 'approved' WHERE id = ?", (inquiry_id,))
    db.commit()
    send_email_with_attachment(inquiry["client_email"], "Your project inquiry has been approved",
                               f"Dear {inquiry['client_name']},\n\nYour project inquiry has been approved by the project manager. We will contact you shortly to proceed with the service agreement.\n\nThank you for choosing MUHLE CONSTRUCTION.")
    return redirect(url_for('project_inquiries_list'))

@app.route('/reject_inquiry/<inquiry_id>')
def reject_inquiry(inquiry_id):
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] not in ['project_manager', 'admin']:
        return "Access Denied", 403
    db = get_db()
    inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if not inquiry:
        return "Inquiry not found", 404
    if inquiry["status"] != "pending_review":
        return "Inquiry already processed", 400
    db.execute("UPDATE project_inquiries SET status = 'rejected' WHERE id = ?", (inquiry_id,))
    db.commit()
    send_email_with_attachment(inquiry["client_email"], "Update on your project inquiry",
                               f"Dear {inquiry['client_name']},\n\nThank you for your interest. After careful review, we regret to inform you that your project inquiry has not been approved at this time.\n\nFor more details, please contact us directly.\n\nRegards,\nMUHLE CONSTRUCTION")
    return redirect(url_for('project_inquiries_list'))

# ─────────────────────────────────────────────
# SERVICE AGREEMENT (Project Manager creates and sends) - FIXED COLUMN COUNT
# ─────────────────────────────────────────────
@app.route('/agreement', methods=['GET', 'POST'])
def agreement():
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] != 'project_manager':
        return "Access Denied: Only project managers can create agreements.", 403
    db = get_db()
    if request.method == 'POST':
        contract_title = request.form.get("contract_title")
        contract_number = request.form.get("contract_number")
        contract_date = request.form.get("contract_date")
        milestones = request.form.get("milestones")
        payment_terms = request.form.get("payment_terms")
        project_scope = request.form.get("project_scope")
        warranties = request.form.get("warranties")
        legal_clauses = request.form.get("legal_clauses")
        
        pm_name = request.form.get("pm_name")
        pm_signature_method = request.form.get("pm_signature_method")
        pm_signature_date = request.form.get("pm_signature_date")
        pm_confirmed = 1 if request.form.get("pm_confirmed") == "yes" else 0
        
        client_id = request.form.get("client_id")
        client_email = request.form.get("client_email")
        client_name = request.form.get("client_name")
        email_message = request.form.get("email_message")
        send_sms_flag = request.form.get("send_sms") == "yes"
        client_phone = request.form.get("client_phone")
        
        if not pm_confirmed:
            return "You must confirm the agreement.", 400
        if not client_id:
            return "Please select a client from the list.", 400
        
        selected_inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (client_id,)).fetchone()
        if not selected_inquiry:
            return "Selected client inquiry not found.", 400
        
        legal_docs = save_uploaded_files(request.files, "legal_docs")
        pm_signed_file = None
        if pm_signature_method == 'upload':
            file = request.files.get("pm_signed_agreement")
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"pm_signed_{contract_number}_{uuid.uuid4().hex}.pdf")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                pm_signed_file = filename
        
        # Generate a unique signature token for this agreement
        signature_token = secrets.token_urlsafe(32)
        
        agreement_id = str(uuid.uuid4())
        # CORRECTED: 24 columns (excluding signed_at, client_signature) and 24 placeholders
        db.execute('''
            INSERT INTO agreements (
                id, inquiry_id, client_name, client_email, project_scope, budget, deadline,
                status, created_at, contract_title, contract_number, contract_date,
                milestones, payment_terms, warranties, legal_clauses, legal_documents,
                pm_name, pm_signature_method, pm_signature_date, pm_confirmed,
                pm_signed_file, client_message, signature_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            agreement_id, selected_inquiry["id"], client_name, client_email,
            selected_inquiry["project_scope"], selected_inquiry["budget"],
            selected_inquiry["deadline"], "pending", datetime.now().isoformat(),
            contract_title, contract_number, contract_date, milestones, payment_terms,
            warranties, legal_clauses, str(legal_docs), pm_name, pm_signature_method,
            pm_signature_date, pm_confirmed, pm_signed_file, email_message, signature_token
        ))
        db.commit()
        
        # Generate PDF contract
        agreement_dict = {
            "contract_title": contract_title,
            "contract_number": contract_number,
            "contract_date": contract_date,
            "client_name": client_name,
            "client_email": client_email,
            "pm_name": pm_name,
            "project_scope": selected_inquiry["project_scope"],
            "budget": selected_inquiry["budget"],
            "milestones": milestones,
            "payment_terms": payment_terms,
            "warranties": warranties,
            "legal_clauses": legal_clauses
        }
        pdf_buffer = generate_agreement_pdf(agreement_dict)
        pdf_bytes = pdf_buffer.getvalue() if pdf_buffer else None
        
        # Build the signature link
        sign_link = url_for('sign_agreement', token=signature_token, _external=True)
        
        email_subject = f"Service Agreement for {contract_title} – Please Sign"
        email_body = f"""Dear {client_name},

{email_message or 'Please find attached the service agreement.'}

To sign the agreement electronically, click the link below:
{sign_link}

If you have any questions, please contact your project manager.

Regards,
MUHLE CONSTRUCTION"""
        
        # Send email with PDF attachment AND signature link
        send_email_with_attachment(client_email, email_subject, email_body, pdf_bytes, f"Agreement_{contract_number}.pdf")
        
        if send_sms_flag and client_phone:
            sms_msg = f"MUHLE CONSTRUCTION: Your service agreement for {contract_title} has been sent to your email. Please check your inbox and sign using the link provided."
            send_sms(client_phone, sms_msg)
        
        return redirect(url_for('dashboard'))
    
    all_inquiries = db.execute("SELECT * FROM project_inquiries WHERE status = 'approved'").fetchall()
    return render_template("service_agreement.html", 
                           project_inquiries=all_inquiries,
                           current_user=user,
                           now=datetime.now())

# ─────────────────────────────────────────────
# SMS SEND ROUTE
# ─────────────────────────────────────────────
@app.route('/send_sms/<inquiry_id>', methods=['POST'])
def send_sms_to_client(inquiry_id):
    if not login_required():
        return redirect(url_for('login'))
    user = get_current_user()
    if user['role'] not in ['project_manager', 'admin']:
        return "Access Denied", 403
    db = get_db()
    inquiry = db.execute("SELECT * FROM project_inquiries WHERE id = ?", (inquiry_id,)).fetchone()
    if not inquiry:
        return "Inquiry not found", 404
    phone = request.form.get('phone_number')
    message = request.form.get('message')
    if not phone or not message:
        return "Phone number and message required", 400
    send_sms(phone, message)
    return redirect(url_for('project_inquiries_list'))

# ─────────────────────────────────────────────
# BOQ GENERATION
# ─────────────────────────────────────────────
@app.route('/boq', methods=['GET', 'POST'])
def boq():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        boq_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "timestamp": datetime.now().isoformat(),
            "terrain_inspection": request.form.get("terrain_inspection"),
            "infrastructure_eval": request.form.get("infrastructure_eval"),
            "soil_condition": request.form.get("soil_condition"),
            "utility_access": request.form.get("utility_access"),
            "technical_risks": request.form.get("technical_risks"),
            "risk_mitigation": request.form.get("risk_mitigation"),
            "survey_report": str(save_uploaded_files(request.files, "survey_report")),
            "survey_photos": str(save_uploaded_files(request.files, "survey_photos")),
            "materials": request.form.get("materials"),
            "labour_rate": request.form.get("labour_rate"),
            "machinery_rate": request.form.get("machinery_rate"),
            "other_resources": request.form.get("other_resources"),
            "overhead_percent": request.form.get("overhead_percent"),
            "contingency_percent": request.form.get("contingency_percent"),
            "cost": request.form.get("cost"),
            "quote_ref": request.form.get("quote_ref"),
            "quote_notes": request.form.get("quote_notes"),
            "status": "quotation_generated"
        }
        db = get_db()
        db.execute('''
            INSERT INTO boq_submissions (
                id, user_id, timestamp, terrain_inspection, infrastructure_eval, soil_condition,
                utility_access, technical_risks, risk_mitigation, survey_report, survey_photos,
                materials, labour_rate, machinery_rate, other_resources, overhead_percent,
                contingency_percent, cost, quote_ref, quote_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (boq_data["id"], boq_data["user_id"], boq_data["timestamp"], boq_data["terrain_inspection"],
              boq_data["infrastructure_eval"], boq_data["soil_condition"], boq_data["utility_access"],
              boq_data["technical_risks"], boq_data["risk_mitigation"], boq_data["survey_report"],
              boq_data["survey_photos"], boq_data["materials"], boq_data["labour_rate"],
              boq_data["machinery_rate"], boq_data["other_resources"], boq_data["overhead_percent"],
              boq_data["contingency_percent"], boq_data["cost"], boq_data["quote_ref"],
              boq_data["quote_notes"], boq_data["status"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("boq.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# TEAM MATCH
# ─────────────────────────────────────────────
@app.route('/team', methods=['GET', 'POST'])
def team():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        team_allocation = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "timestamp": datetime.now().isoformat(),
            "start_date": request.form.get("start_date"),
            "end_date": request.form.get("end_date"),
            "managers": str(request.form.getlist("managers")),
            "crews": str(request.form.getlist("crews")),
            "availability_notes": request.form.get("availability_notes"),
            "machinery_list": request.form.get("machinery_list"),
            "machinery_date": request.form.get("machinery_date"),
            "machinery_duration": request.form.get("machinery_duration"),
            "machinery_conflicts": request.form.get("machinery_conflicts"),
            "role": request.form.get("role"),
            "skill_rating": request.form.get("skill_rating"),
            "location": request.form.get("location"),
            "assigned_workers": request.form.get("assigned_workers"),
            "reserve_managers": 1 if request.form.get("reserve_managers") == "yes" else 0,
            "reserve_crews": 1 if request.form.get("reserve_crews") == "yes" else 0,
            "reserve_machinery": 1 if request.form.get("reserve_machinery") == "yes" else 0,
            "reserve_vehicles": 1 if request.form.get("reserve_vehicles") == "yes" else 0,
            "calendar_start": request.form.get("calendar_start"),
            "calendar_end": request.form.get("calendar_end"),
            "event_name": request.form.get("event_name"),
            "calendar_notes": request.form.get("calendar_notes"),
            "status": "reserved"
        }
        db = get_db()
        db.execute('''
            INSERT INTO team_allocations (
                id, user_id, timestamp, start_date, end_date, managers, crews, availability_notes,
                machinery_list, machinery_date, machinery_duration, machinery_conflicts, role,
                skill_rating, location, assigned_workers, reserve_managers, reserve_crews,
                reserve_machinery, reserve_vehicles, calendar_start, calendar_end, event_name,
                calendar_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (team_allocation["id"], team_allocation["user_id"], team_allocation["timestamp"],
              team_allocation["start_date"], team_allocation["end_date"], team_allocation["managers"],
              team_allocation["crews"], team_allocation["availability_notes"], team_allocation["machinery_list"],
              team_allocation["machinery_date"], team_allocation["machinery_duration"], team_allocation["machinery_conflicts"],
              team_allocation["role"], team_allocation["skill_rating"], team_allocation["location"],
              team_allocation["assigned_workers"], team_allocation["reserve_managers"], team_allocation["reserve_crews"],
              team_allocation["reserve_machinery"], team_allocation["reserve_vehicles"], team_allocation["calendar_start"],
              team_allocation["calendar_end"], team_allocation["event_name"], team_allocation["calendar_notes"],
              team_allocation["status"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("team_match.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# PURCHASE ORDERS
# ─────────────────────────────────────────────
@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        po_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "supplier": request.form.get("supplier"),
            "materials_list": request.form.get("materials_list"),
            "unit_prices": request.form.get("unit_prices"),
            "po_reference": request.form.get("po_reference"),
            "boq_reference": request.form.get("boq_reference"),
            "total_quantity_summary": request.form.get("total_quantity_summary"),
            "amount": float(request.form.get("amount")) if request.form.get("amount") else 0,
            "high_value": 1 if request.form.get("high_value") == "yes" else 0,
            "auth_manager": request.form.get("auth_manager"),
            "auth_code": request.form.get("auth_code"),
            "auth_date": request.form.get("auth_date"),
            "po_delivery_method": request.form.get("po_delivery_method"),
            "supplier_email": request.form.get("supplier_email"),
            "expected_delivery": request.form.get("expected_delivery"),
            "delivery_site": request.form.get("delivery_site"),
            "tracking_email": 1 if request.form.get("tracking_email") == "yes" else 0,
            "tracking_sms": 1 if request.form.get("tracking_sms") == "yes" else 0,
            "tracking_dashboard": 1 if request.form.get("tracking_dashboard") == "yes" else 0,
            "procurement_notes": request.form.get("procurement_notes"),
            "status": "submitted",
            "boq_filename": "",
            "auth_filename": ""
        }
        
        boq_file = request.files.get("boq_file")
        if boq_file and boq_file.filename and allowed_file(boq_file.filename):
            filename = secure_filename(f"boq_{po_data['po_reference']}.pdf")
            boq_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            po_data["boq_filename"] = filename
        
        auth_doc = request.files.get("auth_document")
        if auth_doc and auth_doc.filename and allowed_file(auth_doc.filename):
            filename = secure_filename(f"auth_{po_data['po_reference']}.pdf")
            auth_doc.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            po_data["auth_filename"] = filename
        
        db = get_db()
        db.execute('''
            INSERT INTO purchase_orders (
                id, user_id, created_at, supplier, materials_list, unit_prices, po_reference,
                boq_reference, total_quantity_summary, amount, high_value, auth_manager, auth_code,
                auth_date, po_delivery_method, supplier_email, expected_delivery, delivery_site,
                tracking_email, tracking_sms, tracking_dashboard, procurement_notes, status,
                boq_filename, auth_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (po_data["id"], po_data["user_id"], po_data["created_at"], po_data["supplier"],
              po_data["materials_list"], po_data["unit_prices"], po_data["po_reference"],
              po_data["boq_reference"], po_data["total_quantity_summary"], po_data["amount"],
              po_data["high_value"], po_data["auth_manager"], po_data["auth_code"], po_data["auth_date"],
              po_data["po_delivery_method"], po_data["supplier_email"], po_data["expected_delivery"],
              po_data["delivery_site"], po_data["tracking_email"], po_data["tracking_sms"],
              po_data["tracking_dashboard"], po_data["procurement_notes"], po_data["status"],
              po_data["boq_filename"], po_data["auth_filename"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("purchase_orders.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────
@app.route('/dispatch', methods=['GET', 'POST'])
def dispatch():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        dispatch_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "machinery_list": request.form.get("machinery_list"),
            "transport_date": request.form.get("transport_date"),
            "transport_arrival_time": request.form.get("transport_arrival_time"),
            "transport_provider": request.form.get("transport_provider"),
            "vehicle_reg": request.form.get("vehicle_reg"),
            "office_type": request.form.get("office_type"),
            "power_source": request.form.get("power_source"),
            "power_kva": request.form.get("power_kva"),
            "office_setup_date": request.form.get("office_setup_date"),
            "crew_name": request.form.get("crew_name"),
            "date": request.form.get("date"),
            "shift": request.form.get("shift"),
            "accommodation": request.form.get("accommodation"),
            "crew_transport": request.form.get("crew_transport"),
            "site_status": request.form.get("site_status"),
            "check_machinery": 1 if request.form.get("check_machinery") == "yes" else 0,
            "check_office": 1 if request.form.get("check_office") == "yes" else 0,
            "check_crews": 1 if request.form.get("check_crews") == "yes" else 0,
            "check_safety": 1 if request.form.get("check_safety") == "yes" else 0,
            "confirmed_by": request.form.get("confirmed_by"),
            "confirmation_datetime": request.form.get("confirmation_datetime"),
            "completion_remarks": request.form.get("completion_remarks"),
            "status": "completed",
            "office_photo_filename": ""
        }
        
        office_photo = request.files.get("office_photo")
        if office_photo and office_photo.filename and allowed_file(office_photo.filename):
            filename = secure_filename(f"office_{dispatch_data['id']}.jpg")
            office_photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            dispatch_data["office_photo_filename"] = filename
        
        db = get_db()
        db.execute('''
            INSERT INTO dispatches (
                id, user_id, created_at, machinery_list, transport_date, transport_arrival_time,
                transport_provider, vehicle_reg, office_type, power_source, power_kva, office_setup_date,
                crew_name, date, shift, accommodation, crew_transport, site_status, check_machinery,
                check_office, check_crews, check_safety, confirmed_by, confirmation_datetime,
                completion_remarks, status, office_photo_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dispatch_data["id"], dispatch_data["user_id"], dispatch_data["created_at"],
              dispatch_data["machinery_list"], dispatch_data["transport_date"], dispatch_data["transport_arrival_time"],
              dispatch_data["transport_provider"], dispatch_data["vehicle_reg"], dispatch_data["office_type"],
              dispatch_data["power_source"], dispatch_data["power_kva"], dispatch_data["office_setup_date"],
              dispatch_data["crew_name"], dispatch_data["date"], dispatch_data["shift"], dispatch_data["accommodation"],
              dispatch_data["crew_transport"], dispatch_data["site_status"], dispatch_data["check_machinery"],
              dispatch_data["check_office"], dispatch_data["check_crews"], dispatch_data["check_safety"],
              dispatch_data["confirmed_by"], dispatch_data["confirmation_datetime"], dispatch_data["completion_remarks"],
              dispatch_data["status"], dispatch_data["office_photo_filename"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("dispatch.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# PROJECT PROGRESS
# ─────────────────────────────────────────────
@app.route('/progress', methods=['GET', 'POST'])
def progress():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        progress_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "timestamp": datetime.now().isoformat(),
            "project_phase": request.form.get("project_phase"),
            "completed_tasks": request.form.get("completed_tasks"),
            "percentage": int(request.form.get("percentage")) if request.form.get("percentage") else 0,
            "completion_date": request.form.get("completion_date"),
            "progress_update": request.form.get("update"),
            "photo_descriptions": request.form.get("photo_descriptions"),
            "latitude": request.form.get("latitude"),
            "longitude": request.form.get("longitude"),
            "has_delay": request.form.get("has_delay"),
            "delay_description": request.form.get("delay_description"),
            "recovery_plan": request.form.get("recovery_plan"),
            "change_requirements": request.form.get("change_requirements"),
            "change_ref": request.form.get("change_ref"),
            "milestone": request.form.get("milestone"),
            "client_email": request.form.get("client_email"),
            "notify_client": 1 if request.form.get("notify_client") == "yes" else 0,
            "client_message": request.form.get("client_message"),
            "attach_photos": 1 if request.form.get("attach_photos") == "yes" else 0,
            "internal_notes": request.form.get("internal_notes"),
            "status": "reported",
            "photos": str(save_uploaded_files(request.files, "progress_photos"))
        }
        db = get_db()
        db.execute('''
            INSERT INTO progress_reports (
                id, user_id, timestamp, project_phase, completed_tasks, percentage, completion_date,
                progress_update, photo_descriptions, latitude, longitude, has_delay, delay_description,
                recovery_plan, change_requirements, change_ref, milestone, client_email, notify_client,
                client_message, attach_photos, internal_notes, status, photos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (progress_data["id"], progress_data["user_id"], progress_data["timestamp"],
              progress_data["project_phase"], progress_data["completed_tasks"], progress_data["percentage"],
              progress_data["completion_date"], progress_data["progress_update"], progress_data["photo_descriptions"],
              progress_data["latitude"], progress_data["longitude"], progress_data["has_delay"],
              progress_data["delay_description"], progress_data["recovery_plan"], progress_data["change_requirements"],
              progress_data["change_ref"], progress_data["milestone"], progress_data["client_email"],
              progress_data["notify_client"], progress_data["client_message"], progress_data["attach_photos"],
              progress_data["internal_notes"], progress_data["status"], progress_data["photos"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("progress.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# MILESTONE PAYMENTS
# ─────────────────────────────────────────────
@app.route('/payments', methods=['GET', 'POST'])
def payments():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        payment_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "milestone": request.form.get("milestone"),
            "amount": float(request.form.get("amount")) if request.form.get("amount") else 0,
            "payment_method": request.form.get("payment_method"),
            "account_number": request.form.get("account_number"),
            "expiry": request.form.get("expiry"),
            "cvv": request.form.get("cvv"),
            "mobile_number": request.form.get("mobile_number"),
            "pin_reference": request.form.get("pin_reference"),
            "bank_name": request.form.get("bank_name"),
            "eft_account": request.form.get("eft_account"),
            "status": "completed",
            "account_number_masked": ""
        }
        if payment_data["account_number"] and len(payment_data["account_number"]) > 4:
            payment_data["account_number_masked"] = "****" + payment_data["account_number"][-4:]
        db = get_db()
        db.execute('''
            INSERT INTO payments (
                id, user_id, created_at, milestone, amount, payment_method, account_number,
                expiry, cvv, mobile_number, pin_reference, bank_name, eft_account, status,
                account_number_masked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (payment_data["id"], payment_data["user_id"], payment_data["created_at"],
              payment_data["milestone"], payment_data["amount"], payment_data["payment_method"],
              payment_data["account_number"], payment_data["expiry"], payment_data["cvv"],
              payment_data["mobile_number"], payment_data["pin_reference"], payment_data["bank_name"],
              payment_data["eft_account"], payment_data["status"], payment_data["account_number_masked"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("payments.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# SITE SURVEY
# ─────────────────────────────────────────────
@app.route('/site_survey', methods=['GET', 'POST'])
def site_survey():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        survey_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "assigned_to": session.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "location": request.form.get("location"),
            "terrain_description": request.form.get("terrain_description"),
            "infrastructure_assessment": request.form.get("infrastructure_assessment"),
            "soil_conditions": request.form.get("soil_conditions"),
            "utility_access": request.form.get("utility_access"),
            "survey_notes": request.form.get("survey_notes"),
            "technical_risks": request.form.get("technical_risks"),
            "risk_impact": request.form.get("risk_impact"),
            "risk_mitigation": request.form.get("risk_mitigation"),
            "flag_qs": 1 if request.form.get("flag_qs") == "yes" else 0,
            "status": "submitted",
            "report_filename": "",
            "site_photos": "",
            "aerial_photos": ""
        }
        
        report = request.files.get("survey_report")
        if report and report.filename and allowed_file(report.filename):
            filename = secure_filename(f"survey_{survey_data['id']}.pdf")
            report.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            survey_data["report_filename"] = filename
        
        survey_data["site_photos"] = str(save_uploaded_files(request.files, "site_photos"))
        survey_data["aerial_photos"] = str(save_uploaded_files(request.files, "aerial_photos"))
        
        db = get_db()
        db.execute('''
            INSERT INTO site_surveys (
                id, user_id, assigned_to, created_at, location, terrain_description,
                infrastructure_assessment, soil_conditions, utility_access, survey_notes,
                technical_risks, risk_impact, risk_mitigation, flag_qs, status,
                report_filename, site_photos, aerial_photos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (survey_data["id"], survey_data["user_id"], survey_data["assigned_to"],
              survey_data["created_at"], survey_data["location"], survey_data["terrain_description"],
              survey_data["infrastructure_assessment"], survey_data["soil_conditions"],
              survey_data["utility_access"], survey_data["survey_notes"], survey_data["technical_risks"],
              survey_data["risk_impact"], survey_data["risk_mitigation"], survey_data["flag_qs"],
              survey_data["status"], survey_data["report_filename"], survey_data["site_photos"],
              survey_data["aerial_photos"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("site_survey.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# SAFETY AUDIT
# ─────────────────────────────────────────────
@app.route('/safety', methods=['GET', 'POST'])
def safety():
    if not login_required():
        return redirect(url_for('login'))
    if request.method == 'POST':
        audit_data = {
            "id": str(uuid.uuid4()),
            "user_id": session.get("user_id"),
            "created_at": datetime.now().isoformat(),
            "audit_date": request.form.get("audit_date"),
            "auditor": request.form.get("auditor"),
            "site_location": request.form.get("site_location"),
            "weather": request.form.get("weather"),
            "audit_scope": request.form.get("audit_scope"),
            "ppe_hard_hat": 1 if request.form.get("ppe_hard_hat") == "yes" else 0,
            "ppe_vest": 1 if request.form.get("ppe_vest") == "yes" else 0,
            "ppe_gloves": 1 if request.form.get("ppe_gloves") == "yes" else 0,
            "ppe_safety_glasses": 1 if request.form.get("ppe_safety_glasses") == "yes" else 0,
            "ppe_harness": 1 if request.form.get("ppe_harness") == "yes" else 0,
            "housekeeping_clear": 1 if request.form.get("housekeeping_clear") == "yes" else 0,
            "housekeeping_signage": 1 if request.form.get("housekeeping_signage") == "yes" else 0,
            "housekeeping_lighting": 1 if request.form.get("housekeeping_lighting") == "yes" else 0,
            "housekeeping_fire": 1 if request.form.get("housekeeping_fire") == "yes" else 0,
            "equipment_guards": 1 if request.form.get("equipment_guards") == "yes" else 0,
            "equipment_certified": 1 if request.form.get("equipment_certified") == "yes" else 0,
            "equipment_emergency_stops": 1 if request.form.get("equipment_emergency_stops") == "yes" else 0,
            "checklist_notes": request.form.get("checklist_notes"),
            "hazards": request.form.get("hazards"),
            "overall_risk": request.form.get("overall_risk"),
            "corrective_actions": request.form.get("corrective_actions"),
            "action_owner": request.form.get("action_owner"),
            "audit_conclusion": request.form.get("audit_conclusion"),
            "auditor_signature": request.form.get("auditor_signature"),
            "audit": request.form.get("audit"),
            "audit_finalized": 1 if request.form.get("audit_finalized") == "yes" else 0,
            "status": "submitted",
            "hazard_photos": str(save_uploaded_files(request.files, "hazard_photos"))
        }
        db = get_db()
        db.execute('''
            INSERT INTO safety_audits (
                id, user_id, created_at, audit_date, auditor, site_location, weather,
                audit_scope, ppe_hard_hat, ppe_vest, ppe_gloves, ppe_safety_glasses,
                ppe_harness, housekeeping_clear, housekeeping_signage, housekeeping_lighting,
                housekeeping_fire, equipment_guards, equipment_certified, equipment_emergency_stops,
                checklist_notes, hazards, overall_risk, corrective_actions, action_owner,
                audit_conclusion, auditor_signature, audit, audit_finalized, status, hazard_photos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (audit_data["id"], audit_data["user_id"], audit_data["created_at"],
              audit_data["audit_date"], audit_data["auditor"], audit_data["site_location"],
              audit_data["weather"], audit_data["audit_scope"], audit_data["ppe_hard_hat"],
              audit_data["ppe_vest"], audit_data["ppe_gloves"], audit_data["ppe_safety_glasses"],
              audit_data["ppe_harness"], audit_data["housekeeping_clear"], audit_data["housekeeping_signage"],
              audit_data["housekeeping_lighting"], audit_data["housekeeping_fire"],
              audit_data["equipment_guards"], audit_data["equipment_certified"],
              audit_data["equipment_emergency_stops"], audit_data["checklist_notes"],
              audit_data["hazards"], audit_data["overall_risk"], audit_data["corrective_actions"],
              audit_data["action_owner"], audit_data["audit_conclusion"], audit_data["auditor_signature"],
              audit_data["audit"], audit_data["audit_finalized"], audit_data["status"],
              audit_data["hazard_photos"]))
        db.commit()
        return redirect(url_for('dashboard'))
    return render_template("safety.html", current_user=get_current_user())

# ─────────────────────────────────────────────
# RUN APP
# ─────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
