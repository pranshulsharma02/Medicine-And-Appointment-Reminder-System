"""
MedCare+ - Medicine & Appointment Management System (Database Edition)

What changed from the JSON version:
  - All data (patients/users, medicines, appointments, doctors) now lives in a
    real SQLite database file (medcare.db) instead of loose JSON files.
  - Backup/Restore now uses SQLite's built-in backup API to copy the whole
    database atomically, instead of copying JSON files that may or may not
    exist yet.
  - A brand new Doctor side of the app: doctors table (capped at 15 records,
    each with name, phone, email, specialization), a Doctor Login screen, and
    a read-only Doctor Dashboard where a doctor can see their own upcoming
    appointments and search patient medicine history.
  - On first run, the database is auto-seeded with 15 demo patients and 15
    demo doctors (one for each of 15 different specializations) so the app
    has data to explore immediately.

Run with:  python medcare_plus.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import sqlite3
from datetime import datetime, timedelta

# winsound is Windows-only; import safely so the app still runs on other OS too
try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

# Pillow is needed to preview uploaded photos inside the app. Import safely so
# the app still runs (minus the live preview) if it isn't installed.
try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# Twilio is needed to send real SMS reminders. Import safely so the app still
# runs (minus SMS) if it isn't installed or configured.
try:
    from twilio.rest import Client as _TwilioClient
    _HAS_TWILIO = True
except ImportError:
    _HAS_TWILIO = False


def beep_alert():
    """Play a beep sound. Uses winsound on Windows, terminal bell on other OS."""
    try:
        if _HAS_WINSOUND:
            winsound.Beep(1000, 600)  # frequency=1000Hz, duration=600ms
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        # Never let a beep failure crash the app
        pass


# ================= Config / Theme =================
BG_DARK = "#0B1E2D"
BG_MID = "#102A3E"
ACCENT = "#00C6FF"
ACCENT2 = "#1E90FF"
GOLD = "#FFD700"
DANGER = "#E74C3C"
TEXT_LIGHT = "#B0C4DE"
DOC_ACCENT = "#9B59B6"   # purple accent used to visually mark doctor screens

PHOTOS_DIR = "medicine_photos"

DB_FILE = "medcare.db"
BACKUP_DB_FILE = "backup_medcare.db"

MAX_DOCTORS = 15

# ---- SMS Reminder Configuration ----
# To enable real, real-time SMS alerts, create a free Twilio account at
# https://www.twilio.com, grab your Account SID, Auth Token, and a Twilio
# phone number, and paste them in below. Leaving these blank simply disables
# SMS sending — the rest of the app (beep + popup reminders) keeps working.
TWILIO_ACCOUNT_SID = ""   # e.g. "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN = ""    # your Twilio Auth Token
TWILIO_FROM_NUMBER = ""   # your Twilio number, e.g. "+15551234567"


# ================= Database Layer =================
def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist yet, and seed demo data once."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            age INTEGER,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            age TEXT,
            disease TEXT,
            medicine TEXT,
            time TEXT,
            photo_path TEXT,
            suggested_by TEXT
        )
    """)

    # Reference table of real, commonly-prescribed medicines grouped by
    # doctor specialization (7 per specialization). This powers the doctor
    # "Suggest Medicine" feature and the suggestion panel on the patient
    # appointment screen.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS specialization_medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            specialization TEXT NOT NULL,
            medicine_name TEXT NOT NULL,
            usage_note TEXT
        )
    """)

    # Log of every medicine a doctor has suggested for a patient, so the
    # suggestion history is kept independent of (and in addition to) the
    # patient's own medicine records.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suggested_medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER,
            doctor_name TEXT,
            specialization TEXT,
            patient_name TEXT NOT NULL,
            medicine TEXT NOT NULL,
            notes TEXT,
            date_suggested TEXT,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            phone TEXT,
            date TEXT,
            time TEXT,
            doctor TEXT
        )
    """)

    # Doctors table — capped at MAX_DOCTORS (15) records by add_doctor().
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            email TEXT,
            specialization TEXT
        )
    """)

    # Migration: older databases created before "suggested_by" existed won't
    # have the column yet. Add it in place so existing data isn't lost.
    existing_cols = [r["name"] for r in cur.execute("PRAGMA table_info(medicines)").fetchall()]
    if "suggested_by" not in existing_cols:
        cur.execute("ALTER TABLE medicines ADD COLUMN suggested_by TEXT")

    conn.commit()
    _seed_demo_data(conn)
    _seed_specialization_medicines(conn)
    conn.close()


def _seed_demo_data(conn):
    """Populate 15 demo patients and 15 demo doctors the first time the
    database is created, so the app has data to explore right away. Safe to
    call repeatedly — only inserts when each table is empty."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        demo_students = [
            ("Aarav Sharma", "9876543210", 21, "pass123"),
            ("Priya Patel", "9876543211", 22, "pass123"),
            ("Rohan Mehta", "9876543212", 20, "pass123"),
            ("Sneha Verma", "9876543213", 23, "pass123"),
            ("Karan Singh", "9876543214", 21, "pass123"),
            ("Ananya Gupta", "9876543215", 22, "pass123"),
            ("Vikram Rao", "9876543216", 24, "pass123"),
            ("Neha Joshi", "9876543217", 20, "pass123"),
            ("Arjun Nair", "9876543218", 23, "pass123"),
            ("Ishita Kapoor", "9876543219", 21, "pass123"),
            ("Aditya Malhotra", "9876543220", 22, "pass123"),
            ("Riya Chopra", "9876543221", 20, "pass123"),
            ("Siddharth Iyer", "9876543222", 24, "pass123"),
            ("Pooja Reddy", "9876543223", 21, "pass123"),
            ("Manav Kohli", "9876543224", 23, "pass123"),
        ]
        cur.executemany(
            "INSERT INTO users (name, phone, age, password) VALUES (?, ?, ?, ?)",
            demo_students,
        )

    cur.execute("SELECT COUNT(*) FROM doctors")
    if cur.fetchone()[0] == 0:
        demo_doctors = [
            ("Dr. Ramesh Kumar", "9812345001", "ramesh.kumar@medcareplus.com", "Cardiologist"),
            ("Dr. Sunita Rao", "9812345002", "sunita.rao@medcareplus.com", "Dermatologist"),
            ("Dr. Anil Mehra", "9812345003", "anil.mehra@medcareplus.com", "Neurologist"),
            ("Dr. Kavita Nair", "9812345004", "kavita.nair@medcareplus.com", "Pediatrician"),
            ("Dr. Suresh Iyer", "9812345005", "suresh.iyer@medcareplus.com", "Orthopedic Surgeon"),
            ("Dr. Meena Joshi", "9812345006", "meena.joshi@medcareplus.com", "General Physician"),
            ("Dr. Rajesh Verma", "9812345007", "rajesh.verma@medcareplus.com", "ENT Specialist"),
            ("Dr. Pooja Malhotra", "9812345008", "pooja.malhotra@medcareplus.com", "Dentist"),
            ("Dr. Vivek Chopra", "9812345009", "vivek.chopra@medcareplus.com", "Psychiatrist"),
            ("Dr. Anjali Singh", "9812345010", "anjali.singh@medcareplus.com", "Gynecologist"),
            ("Dr. Manoj Gupta", "9812345011", "manoj.gupta@medcareplus.com", "Ophthalmologist"),
            ("Dr. Deepa Kapoor", "9812345012", "deepa.kapoor@medcareplus.com", "Endocrinologist"),
            ("Dr. Arvind Rao", "9812345013", "arvind.rao@medcareplus.com", "Gastroenterologist"),
            ("Dr. Shalini Menon", "9812345014", "shalini.menon@medcareplus.com", "Pulmonologist"),
            ("Dr. Nikhil Bhatt", "9812345015", "nikhil.bhatt@medcareplus.com", "Urologist"),
        ]
        cur.executemany(
            "INSERT INTO doctors (name, phone, email, specialization) VALUES (?, ?, ?, ?)",
            demo_doctors,
        )

    conn.commit()


def _seed_specialization_medicines(conn):
    """Populate the specialization -> medicine reference list once, with 7
    real, commonly-prescribed medicines for each of the 15 specializations
    used in the demo doctor data. Safe to call repeatedly — only inserts
    when the table is empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM specialization_medicines")
    if cur.fetchone()[0] != 0:
        return

    spec_medicines = {
        "Cardiologist": [
            ("Atorvastatin", "Lowers LDL cholesterol"),
            ("Amlodipine", "Calcium channel blocker for hypertension"),
            ("Metoprolol", "Beta blocker for heart rate/BP control"),
            ("Aspirin (low dose)", "Antiplatelet, reduces clot risk"),
            ("Losartan", "ARB for hypertension/heart failure"),
            ("Clopidogrel", "Antiplatelet after cardiac events"),
            ("Furosemide", "Diuretic for fluid overload"),
        ],
        "Dermatologist": [
            ("Tretinoin Cream", "Topical retinoid for acne/anti-aging"),
            ("Clindamycin Gel", "Topical antibiotic for acne"),
            ("Hydrocortisone Cream", "Mild topical steroid for eczema/rashes"),
            ("Ketoconazole Cream", "Antifungal for fungal skin infections"),
            ("Cetirizine", "Antihistamine for allergic skin reactions"),
            ("Isotretinoin", "Oral retinoid for severe acne"),
            ("Fusidic Acid Cream", "Topical antibiotic for skin infections"),
        ],
        "Neurologist": [
            ("Sodium Valproate", "Anticonvulsant for seizures"),
            ("Levetiracetam", "Anticonvulsant for epilepsy"),
            ("Gabapentin", "Nerve pain / neuropathy relief"),
            ("Sumatriptan", "Acute migraine treatment"),
            ("Amitriptyline", "Migraine prevention / nerve pain"),
            ("Carbamazepine", "Anticonvulsant / trigeminal neuralgia"),
            ("Propranolol", "Migraine prophylaxis"),
        ],
        "Pediatrician": [
            ("Paracetamol Syrup", "Fever and pain relief for children"),
            ("Amoxicillin Suspension", "Antibiotic for common infections"),
            ("Oral Rehydration Salts (ORS)", "Rehydration for diarrhea"),
            ("Cetirizine Syrup", "Pediatric allergy relief"),
            ("Vitamin D3 Drops", "Bone development supplement"),
            ("Salbutamol Syrup", "Bronchodilator for pediatric wheezing"),
            ("Zinc Sulphate Syrup", "Supports recovery from diarrhea"),
        ],
        "Orthopedic Surgeon": [
            ("Ibuprofen", "NSAID for pain and inflammation"),
            ("Diclofenac Gel", "Topical anti-inflammatory for joints"),
            ("Calcium + Vitamin D3", "Bone strength supplement"),
            ("Tramadol", "Moderate to severe pain relief"),
            ("Glucosamine Sulphate", "Joint cartilage support"),
            ("Methylcobalamin", "Nerve support for lower back pain"),
            ("Etoricoxib", "NSAID for arthritis pain"),
        ],
        "General Physician": [
            ("Paracetamol", "Fever and general pain relief"),
            ("Amoxicillin", "Broad-spectrum antibiotic"),
            ("Omeprazole", "Reduces stomach acid / acidity relief"),
            ("Cetirizine", "General allergy relief"),
            ("Azithromycin", "Antibiotic for respiratory infections"),
            ("Metformin", "First-line treatment for type 2 diabetes"),
            ("Ibuprofen", "Pain and inflammation relief"),
        ],
        "ENT Specialist": [
            ("Amoxicillin-Clavulanate", "Antibiotic for ear/sinus infections"),
            ("Fluticasone Nasal Spray", "Reduces nasal inflammation"),
            ("Cetirizine", "Allergy/rhinitis relief"),
            ("Xylometazoline Nasal Drops", "Short-term nasal decongestant"),
            ("Azithromycin", "Antibiotic for throat infections"),
            ("Betadine Gargle", "Antiseptic for sore throat"),
            ("Levocetirizine", "Long-acting antihistamine"),
        ],
        "Dentist": [
            ("Amoxicillin", "Antibiotic for dental infections"),
            ("Metronidazole", "Antibiotic for gum/anaerobic infections"),
            ("Ibuprofen", "Pain relief after dental procedures"),
            ("Chlorhexidine Mouthwash", "Antiseptic oral rinse"),
            ("Paracetamol", "Post-procedure pain relief"),
            ("Clove Oil (Eugenol)", "Topical relief for toothache"),
            ("Diclofenac", "Anti-inflammatory for dental pain"),
        ],
        "Psychiatrist": [
            ("Sertraline", "SSRI for depression/anxiety"),
            ("Escitalopram", "SSRI for depression/anxiety disorders"),
            ("Alprazolam", "Short-term anxiety relief"),
            ("Fluoxetine", "SSRI for depression/OCD"),
            ("Quetiapine", "Antipsychotic / mood stabilizer"),
            ("Mirtazapine", "Antidepressant, aids sleep/appetite"),
            ("Clonazepam", "Anxiolytic / anticonvulsant"),
        ],
        "Gynecologist": [
            ("Folic Acid", "Prenatal supplement"),
            ("Iron + Folic Acid", "Anemia prevention in pregnancy"),
            ("Clomiphene Citrate", "Fertility treatment"),
            ("Mefenamic Acid", "Relief for menstrual pain"),
            ("Combined Oral Contraceptive Pill", "Contraception/cycle regulation"),
            ("Metronidazole", "Treats vaginal infections"),
            ("Progesterone", "Hormonal support in pregnancy"),
        ],
        "Ophthalmologist": [
            ("Moxifloxacin Eye Drops", "Antibiotic for eye infections"),
            ("Timolol Eye Drops", "Lowers intraocular pressure (glaucoma)"),
            ("Artificial Tears", "Relief for dry eyes"),
            ("Prednisolone Eye Drops", "Anti-inflammatory for eye conditions"),
            ("Ketorolac Eye Drops", "NSAID for eye pain/inflammation"),
            ("Latanoprost Eye Drops", "Glaucoma treatment"),
            ("Olopatadine Eye Drops", "Relief for allergic conjunctivitis"),
        ],
        "Endocrinologist": [
            ("Metformin", "First-line diabetes management"),
            ("Insulin Glargine", "Long-acting insulin for diabetes"),
            ("Levothyroxine", "Thyroid hormone replacement"),
            ("Glimepiride", "Sulfonylurea for type 2 diabetes"),
            ("Carbimazole", "Treats hyperthyroidism"),
            ("Sitagliptin", "DPP-4 inhibitor for diabetes"),
            ("Vitamin D3", "Corrects deficiency-related disorders"),
        ],
        "Gastroenterologist": [
            ("Omeprazole", "Proton pump inhibitor for acidity/GERD"),
            ("Pantoprazole", "Reduces stomach acid production"),
            ("Domperidone", "Relieves nausea/bloating"),
            ("Rifaximin", "Antibiotic for gut infections/IBS"),
            ("Ondansetron", "Anti-nausea medication"),
            ("Lactulose", "Relief for constipation"),
            ("Mesalamine", "Treats inflammatory bowel disease"),
        ],
        "Pulmonologist": [
            ("Salbutamol Inhaler", "Bronchodilator for asthma/COPD"),
            ("Budesonide Inhaler", "Inhaled steroid for asthma control"),
            ("Montelukast", "Prevents asthma/allergy symptoms"),
            ("Theophylline", "Bronchodilator for chronic airway disease"),
            ("Azithromycin", "Antibiotic for respiratory infections"),
            ("Prednisolone", "Oral steroid for severe flare-ups"),
            ("N-Acetylcysteine", "Mucolytic to loosen chest congestion"),
        ],
        "Urologist": [
            ("Tamsulosin", "Relaxes prostate/bladder muscles (BPH)"),
            ("Finasteride", "Reduces prostate enlargement"),
            ("Ciprofloxacin", "Antibiotic for urinary tract infections"),
            ("Nitrofurantoin", "Antibiotic for UTIs"),
            ("Sildenafil", "Treats erectile dysfunction"),
            ("Potassium Citrate", "Helps prevent kidney stones"),
            ("Oxybutynin", "Reduces overactive bladder symptoms"),
        ],
    }

    for specialization, meds in spec_medicines.items():
        for medicine_name, usage_note in meds:
            cur.execute(
                "INSERT INTO specialization_medicines (specialization, medicine_name, usage_note) VALUES (?, ?, ?)",
                (specialization, medicine_name, usage_note),
            )

    conn.commit()


def backup_db():
    """Atomic database backup using SQLite's built-in backup API — far more
    reliable than copying JSON files that may not exist yet."""
    try:
        src = sqlite3.connect(DB_FILE)
        dst = sqlite3.connect(BACKUP_DB_FILE)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return True
    except sqlite3.Error:
        return False


def restore_db():
    """Restore the working database from the last backup file."""
    if not os.path.exists(BACKUP_DB_FILE):
        return False
    try:
        src = sqlite3.connect(BACKUP_DB_FILE)
        dst = sqlite3.connect(DB_FILE)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return True
    except sqlite3.Error:
        return False


def send_sms_reminder(to_number, message):
    """Send a real-time SMS via Twilio. Safely does nothing (returns False)
    if Twilio isn't installed or TWILIO_* credentials above aren't filled in,
    so the app keeps working normally without SMS configured."""
    if not (_HAS_TWILIO and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        return False
    if not to_number:
        return False
    try:
        client = _TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_number)
        return True
    except Exception as e:
        print(f"SMS send failed: {e}")
        return False


# ================= Reusable Widgets =================
def styled_button(parent, text, command, color=ACCENT, fg="white", width=15):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=color,
        fg=fg,
        font=("Segoe UI", 11, "bold"),
        relief="flat",
        width=width,
        cursor="hand2",
    )


def entry_field(parent, width=30):
    var = tk.StringVar()
    entry = tk.Entry(parent, textvariable=var, width=width, font=("Segoe UI", 11))
    return entry, var


def field_row(parent, label_text, bg=BG_MID):
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=10)

    tk.Label(
        row,
        text=label_text,
        bg=bg,
        fg="white",
        font=("Segoe UI", 12, "bold"),
        width=17,
        anchor="w",
    ).pack(side="left", padx=10)

    entry, var = entry_field(row, width=30)
    entry.pack(side="left", padx=10)

    return entry, var


def add_topbar(frame, master, current_user=""):
    top = tk.Frame(frame, bg=BG_DARK)
    top.pack(fill="x")
    tk.Label(
        top,
        text=f"Logged in as: {current_user}",
        bg=BG_DARK,
        fg=TEXT_LIGHT,
        font=("Segoe UI", 10),
    ).pack(side="right", padx=10, pady=5)


def add_status_bar(root):
    status = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor="w")
    status.pack(side="bottom", fill="x")
    return status


def add_footer(frame, text, color=ACCENT):
    footer = tk.Frame(frame, bg=color, height=4)
    footer.pack(fill="x", side="bottom")
    tk.Label(
        frame, text=text, bg=BG_DARK, fg="white", font=("Segoe UI", 9)
    ).pack(side="bottom", pady=4)


def show_about():
    win = tk.Toplevel()
    win.title("About Developer")
    win.geometry("400x300")
    win.configure(bg=BG_DARK)

    tk.Label(
        win, text="MedCare+", font=("Segoe UI", 22, "bold"), bg=BG_DARK, fg=ACCENT
    ).pack(pady=15)



    tk.Label(
        win, text="Python | Tkinter | SQLite", bg=BG_DARK, fg=TEXT_LIGHT
    ).pack(pady=10)


def backup():
    """Manual full backup (in addition to the automatic per-record backup
    that runs every time a Medicine or Appointment record is saved)."""
    if backup_db():
        messagebox.showinfo("Backup", "Database Backup Created Successfully")
    else:
        messagebox.showerror("Backup", "Could not create a backup right now.")


def restore():
    if restore_db():
        messagebox.showinfo("Restore", "Database Restored From Backup")
    else:
        messagebox.showerror("Restore", "No backup database found.")


# ================= Splash Screen =================
class Splash(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.geometry("500x300")
        self.configure(bg=BG_DARK)
        self.overrideredirect(True)

        # center the splash window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 250
        y = (self.winfo_screenheight() // 2) - 150
        self.geometry(f"500x300+{x}+{y}")

        tk.Label(
            self,
            text="🏥 MedCare+",
            font=("Segoe UI", 30, "bold"),
            bg=BG_DARK,
            fg=ACCENT,
        ).pack(expand=True)

        self.after(1500, self.destroy)


# ================= Login Chooser =================
class LoginScreen(tk.Frame):
    """Patient login, with links to Register, Doctor Login, and the admin
    Manage Doctors screen."""

    def __init__(self, master):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master

        tk.Label(
            self,
            text="🏥 MedCare+ Login",
            bg=BG_DARK,
            fg=ACCENT,
            font=("Segoe UI", 26, "bold"),
        ).pack(pady=25)

        card = tk.Frame(
            self, bg=BG_MID, highlightbackground=ACCENT, highlightthickness=2
        )
        card.pack(padx=40, pady=10, fill="x")

        self.phone_entry, self.phone_var = field_row(card, "Phone")

        pass_row = tk.Frame(card, bg=BG_MID)
        pass_row.pack(fill="x", pady=10)
        tk.Label(
            pass_row,
            text="Password",
            bg=BG_MID,
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=17,
            anchor="w",
        ).pack(side="left", padx=10)
        self.password_var = tk.StringVar()
        tk.Entry(
            pass_row, textvariable=self.password_var, show="*", width=30, font=("Segoe UI", 11)
        ).pack(side="left", padx=10)

        nav_frame = tk.Frame(card, bg=BG_MID)
        nav_frame.pack(pady=10)

        tk.Button(
            nav_frame,
            text="❌ Exit",
            font=("Segoe UI", 11, "bold"),
            bg="#607D8B",
            fg="white",
            relief="flat",
            width=12,
            cursor="hand2",
            command=self.master.destroy,
        ).pack(side="left", padx=10)

        tk.Button(
            nav_frame,
            text="Login ➡",
            font=("Segoe UI", 11, "bold"),
            bg=ACCENT2,
            fg="white",
            relief="flat",
            width=12,
            cursor="hand2",
            command=self._submit,
        ).pack(side="left", padx=10)

        # ---- Register link ----
        register_frame = tk.Frame(self, bg=BG_DARK)
        register_frame.pack(pady=8)

        tk.Label(
            register_frame,
            text="Don't have an account?",
            bg=BG_DARK,
            fg=TEXT_LIGHT,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=5)

        tk.Button(
            register_frame,
            text="📝 Register",
            font=("Segoe UI", 10, "bold"),
            bg=GOLD,
            fg=BG_DARK,
            relief="flat",
            cursor="hand2",
            command=self.master._show_register,
        ).pack(side="left", padx=5)

        # ---- Doctor portal links ----
        doctor_frame = tk.Frame(self, bg=BG_DARK)
        doctor_frame.pack(pady=15)

        tk.Button(
            doctor_frame,
            text="🩺 Doctor Login",
            font=("Segoe UI", 10, "bold"),
            bg=DOC_ACCENT,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.master._show_doctor_login,
        ).pack(side="left", padx=5)

        tk.Button(
            doctor_frame,
            text="⚙ Manage Doctors (Admin)",
            font=("Segoe UI", 10, "bold"),
            bg="#607D8B",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self.master._show_manage_doctors,
        ).pack(side="left", padx=5)

    def _submit(self):
        phone = self.phone_var.get().strip()
        password = self.password_var.get()

        if not phone or not password:
            messagebox.showwarning("Missing Info", "Please enter phone and password.")
            return

        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM users WHERE phone = ?", (phone,)
        ).fetchone()
        conn.close()

        if row is None:
            messagebox.showerror("Login Failed", "No account found with this phone number.")
            return

        if row["password"] != password:
            messagebox.showerror("Login Failed", "Incorrect password.")
            return

        self.destroy()
        self.master._show_welcome(row["name"], row["phone"], row["age"])


# ================= Register Screen =================
class RegisterScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master

        tk.Label(
            self,
            text="📝 Create an Account",
            bg=BG_DARK,
            fg=ACCENT,
            font=("Segoe UI", 26, "bold"),
        ).pack(pady=30)

        card = tk.Frame(
            self, bg=BG_MID, highlightbackground=ACCENT, highlightthickness=2
        )
        card.pack(padx=40, pady=20, fill="x")

        self.name_entry, self.name_var = field_row(card, "Name")
        self.phone_entry, self.phone_var = field_row(card, "Phone")
        self.age_entry, self.age_var = field_row(card, "Age")

        pass_row = tk.Frame(card, bg=BG_MID)
        pass_row.pack(fill="x", pady=10)
        tk.Label(
            pass_row,
            text="Password",
            bg=BG_MID,
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=17,
            anchor="w",
        ).pack(side="left", padx=10)
        self.password_var = tk.StringVar()
        tk.Entry(
            pass_row, textvariable=self.password_var, show="*", width=30, font=("Segoe UI", 11)
        ).pack(side="left", padx=10)

        confirm_row = tk.Frame(card, bg=BG_MID)
        confirm_row.pack(fill="x", pady=10)
        tk.Label(
            confirm_row,
            text="Confirm Password",
            bg=BG_MID,
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=17,
            anchor="w",
        ).pack(side="left", padx=10)
        self.confirm_var = tk.StringVar()
        tk.Entry(
            confirm_row, textvariable=self.confirm_var, show="*", width=30, font=("Segoe UI", 11)
        ).pack(side="left", padx=10)

        nav_frame = tk.Frame(card, bg=BG_MID)
        nav_frame.pack(pady=10)

        tk.Button(
            nav_frame,
            text="⬅ Back to Login",
            font=("Segoe UI", 11, "bold"),
            bg="#607D8B",
            fg="white",
            relief="flat",
            width=15,
            cursor="hand2",
            command=self.master._show_login,
        ).pack(side="left", padx=10)

        tk.Button(
            nav_frame,
            text="Register ✔",
            font=("Segoe UI", 11, "bold"),
            bg=ACCENT2,
            fg="white",
            relief="flat",
            width=15,
            cursor="hand2",
            command=self._submit,
        ).pack(side="left", padx=10)

    def _submit(self):
        name = self.name_var.get().strip()
        phone = self.phone_var.get().strip()
        age = self.age_var.get().strip()
        password = self.password_var.get()
        confirm = self.confirm_var.get()

        if not name or not phone or not age or not password or not confirm:
            messagebox.showwarning("Missing Info", "Please fill in all fields.")
            return

        if not age.isdigit():
            messagebox.showwarning("Invalid Age", "Age must be a number.")
            return

        if not phone.isdigit() or len(phone) < 7:
            messagebox.showwarning("Invalid Phone", "Please enter a valid phone number.")
            return

        if password != confirm:
            messagebox.showwarning("Password Mismatch", "Passwords do not match.")
            return

        conn = get_connection()
        exists = conn.execute(
            "SELECT 1 FROM users WHERE phone = ?", (phone,)
        ).fetchone()
        if exists:
            conn.close()
            messagebox.showerror("Account Exists", "An account with this phone number already exists.")
            return

        conn.execute(
            "INSERT INTO users (name, phone, age, password) VALUES (?, ?, ?, ?)",
            (name, phone, int(age), password),
        )
        conn.commit()
        conn.close()

        messagebox.showinfo("Success", "Account created successfully! Please log in.")
        self.master._show_login()


# ================= Welcome Screen =================
class WelcomeScreen(tk.Frame):
    def __init__(self, master, name, phone, age, on_continue):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)

        self.master = master
        self.on_continue = on_continue

        add_topbar(self, master, current_user=name)

        tk.Label(
            self,
            text="🏥 Welcome to MedCare+",
            bg=BG_DARK,
            fg=ACCENT,
            font=("Segoe UI", 28, "bold"),
        ).pack(pady=20)

        card = tk.Frame(
            self, bg=BG_MID, highlightbackground=ACCENT, highlightthickness=2
        )
        card.pack(padx=40, pady=20, fill="x")

        tk.Label(
            card,
            text=f"👤 Name : {name}",
            bg=BG_MID,
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=10)

        tk.Label(
            card, text=f"📱 Mobile : {phone}", bg=BG_MID, fg="white", font=("Segoe UI", 14)
        ).pack()

        tk.Label(
            card, text=f"🎂 Age : {age}", bg=BG_MID, fg="white", font=("Segoe UI", 14)
        ).pack(pady=10)

        btn_frame = tk.Frame(self, bg=BG_DARK)
        btn_frame.pack(pady=25)

        tk.Button(
            btn_frame,
            text="⬅ Back",
            width=12,
            bg="#607D8B",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            command=lambda: master._show_login(),
        ).pack(side="left", padx=10)

        tk.Button(
            btn_frame,
            text="Continue ➡",
            width=15,
            bg=ACCENT2,
            fg="white",
            font=("Segoe UI", 11, "bold"),
            command=lambda: self.on_continue(name, phone, age),
        ).pack(side="left", padx=10)

        tk.Button(
            btn_frame,
            text="❌ Exit",
            width=12,
            bg="red",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            command=master.destroy,
        ).pack(side="left", padx=10)


# ================= Dashboard (Sidebar + Pages) =================
class Dashboard(tk.Frame):
    def __init__(self, master, name, phone, age):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master
        self.name = name
        self.phone = phone
        self.age = age

        self.content_area = None
        self._build_sidebar()
        self._build_content_area()
        self.show_home()

    def _build_sidebar(self):
        main_frame = tk.Frame(self, bg=BG_DARK)
        main_frame.pack(fill="both", expand=True)
        self.main_frame = main_frame

        sidebar = tk.Frame(main_frame, bg="#08131F", width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="🏥 MedCare+", bg="#08131F", fg=ACCENT, font=("Segoe UI", 18, "bold")
        ).pack(pady=20)

        tk.Label(
            sidebar, text=f"👤 {self.name}", bg="#08131F", fg="white", font=("Segoe UI", 11)
        ).pack(pady=5)

        styled_button(sidebar, "🏠 Home", self.show_home, color=ACCENT, width=18).pack(pady=5)
        styled_button(
            sidebar, "💊 Medicines", self.show_medicines, color=ACCENT2, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "📅 Appointments", self.show_appointments, color=ACCENT2, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "⚖ BMI", self.show_bmi, color=GOLD, fg="black", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "💾 Backup", backup, color=ACCENT, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "♻ Restore", restore, color=ACCENT, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "ℹ About", show_about, color=GOLD, fg=BG_DARK, width=18
        ).pack(pady=5)

        tk.Frame(sidebar, bg="#08131F").pack(expand=True)

        styled_button(
            sidebar, "⬅ Back", lambda: self.master._show_login(), color="#607D8B", fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "🚪 Logout", self.logout, color=DANGER, fg="white", width=18
        ).pack(pady=5)

    def _build_content_area(self):
        self.content_area = tk.Frame(self.main_frame, bg=BG_DARK)
        self.content_area.pack(side="left", fill="both", expand=True)

    def _clear_content(self):
        for widget in self.content_area.winfo_children():
            widget.destroy()

    def logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.master._show_login()

    # ---------- Pages ----------
    def show_home(self):
        self._clear_content()
        tk.Label(
            self.content_area,
            text=f"Welcome back, {self.name}!",
            bg=BG_DARK,
            fg=ACCENT,
            font=("Segoe UI", 20, "bold"),
        ).pack(pady=40)
        tk.Label(
            self.content_area,
            text="Use the sidebar to manage medicines, appointments, or check your BMI.",
            bg=BG_DARK,
            fg=TEXT_LIGHT,
            font=("Segoe UI", 11),
        ).pack()

    def show_medicines(self):
        self._clear_content()
        MedicinePage(self.content_area, self.name)

    def show_appointments(self):
        self._clear_content()
        AppointmentPage(self.content_area, self.name)

    def show_bmi(self):
        self._clear_content()
        BMIPage(self.content_area)


# ================= Medicine Page =================
class MedicinePage(tk.Frame):
    def __init__(self, parent, name):
        super().__init__(parent, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.name = name
        self.editing_id = None
        self.photo_path = None  # path to the currently uploaded/selected patient photo

        # ---- Nav bar ----
        nav = tk.Frame(self, bg=BG_DARK)
        nav.pack(fill="x", padx=10, pady=5)

        styled_button(nav, "🧹 Clear Form", self._cancel_edit, color=GOLD, fg=BG_DARK, width=15).pack(
            side="left", padx=5
        )

        # ---- Form ----
        form = tk.Frame(self, bg=BG_MID, highlightbackground=ACCENT, highlightthickness=1)
        form.pack(fill="x", padx=10, pady=5)

        self.patient_entry, self.patient_var = field_row(form, "Patient Name")
        self.age_entry, self.age_var = field_row(form, "Age")
        self.disease_entry, self.disease_var = field_row(form, "Disease")
        self.medicine_entry, self.medicine_var = field_row(form, "Medicine")
        self.time_entry, self.time_var = field_row(form, "Time")

        # ---- Photo upload + live preview ----
        photo_row = tk.Frame(form, bg=BG_MID)
        photo_row.pack(fill="x", pady=10)

        tk.Label(
            photo_row,
            text="Photo",
            bg=BG_MID,
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=17,
            anchor="w",
        ).pack(side="left", padx=10)

        self.photo_thumb_label = tk.Label(
            photo_row, text="No Photo", bg=BG_MID, fg=TEXT_LIGHT, font=("Segoe UI", 9),
            width=8, height=3,
        )
        self.photo_thumb_label.pack(side="left", padx=10)

        styled_button(photo_row, "📷 Upload Photo", self._upload_photo, color=ACCENT, width=15).pack(
            side="left", padx=5
        )
        styled_button(photo_row, "🖼 View Photo", self._view_photo, color=ACCENT2, width=15).pack(
            side="left", padx=5
        )

        btn_row = tk.Frame(form, bg=BG_MID)
        btn_row.pack(pady=10)
        styled_button(btn_row, "💾 Save", self._save_record, color=ACCENT2, width=15).pack(
            side="left", padx=5
        )
        styled_button(btn_row, "🗑 Delete", self._delete_record, color=DANGER, width=15).pack(
            side="left", padx=5
        )

        # ---- Search ----
        search_frame = tk.Frame(self, bg=BG_DARK)
        search_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(search_frame, text="🔍 Search Patient", bg=BG_DARK, fg="white").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._load_table())
        tk.Entry(search_frame, textvariable=self.search_var).pack(side="left", padx=5)

        # ---- Table ----
        columns = ("patient_name", "age", "disease", "medicine", "time", "suggested_by")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for col in columns:
            heading = "Suggested By (Doctor)" if col == "suggested_by" else col.replace("_", " ").title()
            self.tree.heading(col, text=heading)
        self.tree.column("suggested_by", width=160)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self._edit_selected)

        self.record_label = tk.Label(
            self, text="📋 Total Records : 0", bg=BG_DARK, fg=GOLD, font=("Segoe UI", 11, "bold")
        )
        self.record_label.pack(pady=5)

        tk.Label(
            self, text="💡 Double Click any record to Edit.", bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 10)
        ).pack(pady=5)

        add_footer(self, "MedCare+ Medicine Management System", ACCENT)

        self._load_table()
        self._refresh_photo_preview()

    def _fetch_records(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM medicines ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return rows

    def _filtered_data(self):
        query = self.search_var.get().lower().strip()
        rows = self._fetch_records()
        if not query:
            return rows
        return [r for r in rows if query in (r["patient_name"] or "").lower()]

    def _load_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        data = self._filtered_data()

        for m in data:
            self.tree.insert(
                "",
                "end",
                iid=str(m["id"]),
                values=(
                    m["patient_name"],
                    m["age"],
                    m["disease"],
                    m["medicine"],
                    m["time"],
                    m["suggested_by"] or "—",
                ),
            )

        self.record_label.config(text=f"📋 Total Records : {len(data)}")

    def _upload_photo(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not path:
            return
        try:
            os.makedirs(PHOTOS_DIR, exist_ok=True)
            ext = os.path.splitext(path)[1].lower() or ".png"
            dest_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext}"
            dest_path = os.path.join(PHOTOS_DIR, dest_name)
            import shutil
            shutil.copy(path, dest_path)
        except OSError as e:
            messagebox.showerror("Upload Failed", f"Could not save photo: {e}")
            return

        self.photo_path = dest_path
        self._refresh_photo_preview()
        messagebox.showinfo("Success", "Photo Uploaded Successfully")

    def _refresh_photo_preview(self):
        """Show a small thumbnail of the currently attached photo so the user
        can actually see what was uploaded, instead of it just disappearing."""
        if not self.photo_path or not os.path.exists(self.photo_path):
            self.photo_thumb_label.config(image="", text="No Photo", fg=TEXT_LIGHT)
            self.photo_thumb_label.image = None
            return

        if not _HAS_PIL:
            self.photo_thumb_label.config(image="", text="Saved\n(install\nPillow)", fg=TEXT_LIGHT)
            self.photo_thumb_label.image = None
            return

        try:
            img = Image.open(self.photo_path)
            img.thumbnail((60, 60))
            photo = ImageTk.PhotoImage(img)
            self.photo_thumb_label.config(image=photo, text="")
            self.photo_thumb_label.image = photo  # keep a reference so it isn't garbage-collected
        except Exception:
            self.photo_thumb_label.config(image="", text="Preview\nerror", fg=DANGER)
            self.photo_thumb_label.image = None

    def _view_photo(self):
        if not self.photo_path or not os.path.exists(self.photo_path):
            messagebox.showinfo("No Photo", "No photo has been uploaded for this record yet.")
            return

        if not _HAS_PIL:
            messagebox.showinfo(
                "Photo Saved",
                f"The photo is saved at:\n{self.photo_path}\n\nInstall Pillow (pip install Pillow) to preview it inside the app.",
            )
            return

        win = tk.Toplevel(self)
        win.title("Patient Photo")
        win.configure(bg=BG_DARK)
        try:
            img = Image.open(self.photo_path)
            img.thumbnail((500, 500))
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(win, image=photo, bg=BG_DARK)
            lbl.image = photo  # keep a reference
            lbl.pack(padx=10, pady=10)
        except Exception as e:
            tk.Label(win, text=f"Could not open photo: {e}", bg=BG_DARK, fg=DANGER).pack(padx=20, pady=20)

    def _save_record(self):
        patient_name = self.patient_var.get().strip()
        age = self.age_var.get().strip()
        disease = self.disease_var.get().strip()
        medicine = self.medicine_var.get().strip()
        time_val = self.time_var.get().strip()

        if not patient_name:
            messagebox.showwarning("Missing Info", "Patient name is required.")
            return

        conn = get_connection()
        if self.editing_id is not None:
            conn.execute(
                """UPDATE medicines SET patient_name=?, age=?, disease=?, medicine=?,
                   time=?, photo_path=? WHERE id=?""",
                (patient_name, age, disease, medicine, time_val, self.photo_path, self.editing_id),
            )
        else:
            conn.execute(
                """INSERT INTO medicines (patient_name, age, disease, medicine, time, photo_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (patient_name, age, disease, medicine, time_val, self.photo_path),
            )
        conn.commit()
        conn.close()

        backup_db()  # auto-backup the database every save
        self._cancel_edit()
        self._load_table()

    def _delete_record(self):
        if self.editing_id is None:
            messagebox.showwarning("No Selection", "Select a record from the table first.")
            return
        conn = get_connection()
        conn.execute("DELETE FROM medicines WHERE id=?", (self.editing_id,))
        conn.commit()
        conn.close()

        backup_db()  # keep backup in sync after delete too
        self._cancel_edit()
        self._load_table()

    def _edit_selected(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        record_id = int(selection[0])

        conn = get_connection()
        m = conn.execute("SELECT * FROM medicines WHERE id=?", (record_id,)).fetchone()
        conn.close()
        if m is None:
            return

        self.editing_id = m["id"]
        self.patient_var.set(m["patient_name"] or "")
        self.age_var.set(m["age"] or "")
        self.disease_var.set(m["disease"] or "")
        self.medicine_var.set(m["medicine"] or "")
        self.time_var.set(m["time"] or "")
        self.photo_path = m["photo_path"]
        self._refresh_photo_preview()

    def _cancel_edit(self):
        self.editing_id = None
        self.patient_var.set("")
        self.age_var.set("")
        self.disease_var.set("")
        self.medicine_var.set("")
        self.time_var.set("")
        self.photo_path = None
        self._refresh_photo_preview()


# ================= Appointment Page =================
class AppointmentPage(tk.Frame):
    def __init__(self, parent, name):
        super().__init__(parent, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.name = name
        self.editing_id = None
        self._alerted_keys = set()  # tracks appointments already beeped, avoid repeat beeps

        nav = tk.Frame(self, bg=BG_DARK)
        nav.pack(fill="x", padx=10, pady=5)
        tk.Label(
            nav, text="📅 Book an Appointment", bg=BG_DARK, fg=DOC_ACCENT, font=("Segoe UI", 16, "bold"),
        ).pack(side="left", padx=5)
        styled_button(nav, "🧹 Clear Form", self._cancel_edit, color=GOLD, fg=BG_DARK, width=15).pack(
            side="right", padx=5
        )

        # Same purple accent used on the doctor login/dashboard screens, so
        # booking an appointment visually matches the doctor side of the app.
        form = tk.Frame(self, bg=BG_MID, highlightbackground=DOC_ACCENT, highlightthickness=2)
        form.pack(fill="x", padx=10, pady=5)

        self.patient_entry, self.patient_var = field_row(form, "Patient Name")
        self.phone_entry, self.phone_var = field_row(form, "Phone (+countrycode)")
        self.date_entry, self.date_var = field_row(form, "Date (YYYY-MM-DD)")
        self.time_entry, self.time_var = field_row(form, "Time (HH:MM)")

        # ---- Doctor dropdown, populated straight from the doctors table ----
        doctor_row = tk.Frame(form, bg=BG_MID)
        doctor_row.pack(fill="x", pady=10)
        tk.Label(
            doctor_row, text="Doctor", bg=BG_MID, fg="white",
            font=("Segoe UI", 12, "bold"), width=17, anchor="w",
        ).pack(side="left", padx=10)
        self.doctor_var = tk.StringVar()
        conn = get_connection()
        doctor_rows = conn.execute(
            "SELECT name, specialization FROM doctors ORDER BY name"
        ).fetchall()
        conn.close()
        doctor_choices = [f"{d['name']} ({d['specialization']})" for d in doctor_rows]
        # doctor name -> specialization lookup, used to drive the suggested
        # medicines panel below whenever the doctor selection changes.
        self._doctor_specialization = {d["name"]: d["specialization"] for d in doctor_rows}
        self.doctor_combo = ttk.Combobox(
            doctor_row, textvariable=self.doctor_var, values=doctor_choices, width=32, state="readonly"
        )
        self.doctor_combo.pack(side="left", padx=10)
        self.doctor_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_suggested_medicines())

        # ---- Suggested medicines panel (based on the chosen doctor's
        # specialization) so patients can see what's typically prescribed
        # before their visit. ----
        suggest_panel = tk.Frame(self, bg=BG_MID, highlightbackground=DOC_ACCENT, highlightthickness=1)
        suggest_panel.pack(fill="x", padx=10, pady=5)
        tk.Label(
            suggest_panel, text="💊 Commonly Suggested Medicines for Selected Doctor",
            bg=BG_MID, fg=DOC_ACCENT, font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self.suggested_meds_label = tk.Label(
            suggest_panel, text="Select a doctor above to see their specialization's common medicines.",
            bg=BG_MID, fg=TEXT_LIGHT, font=("Segoe UI", 9), justify="left", wraplength=760,
        )
        self.suggested_meds_label.pack(anchor="w", padx=10, pady=(0, 8))

        btn_row = tk.Frame(form, bg=BG_MID)
        btn_row.pack(pady=10)
        styled_button(btn_row, "💾 Save", self._save_record, color=DOC_ACCENT, width=15).pack(
            side="left", padx=5
        )
        styled_button(btn_row, "🗑 Delete", self._delete_record, color=DANGER, width=15).pack(
            side="left", padx=5
        )

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._load_table())
        search_frame = tk.Frame(self, bg=BG_DARK)
        search_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(search_frame, text="🔍 Search Patient", bg=BG_DARK, fg="white").pack(side="left")
        tk.Entry(search_frame, textvariable=self.search_var).pack(side="left", padx=5)

        stats_frame = tk.Frame(self, bg=BG_DARK)
        stats_frame.pack(fill="x", pady=5)
        self.total_label = tk.Label(
            stats_frame, text="📅 Total Appointments : 0", bg=BG_DARK, fg=GOLD, font=("Segoe UI", 11, "bold")
        )
        self.total_label.pack(side="left", padx=10)
        self.upcoming_label = tk.Label(
            stats_frame, text="⏰ Upcoming : 0", bg=BG_DARK, fg=DOC_ACCENT, font=("Segoe UI", 11, "bold")
        )
        self.upcoming_label.pack(side="right", padx=10)

        columns = ("patient_name", "phone", "date", "time", "doctor")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title())
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self._edit_selected)

        tk.Label(
            self,
            text="💡 Double Click any appointment to Edit.  📲 SMS reminders send automatically if a phone number is entered and Twilio is configured.",
            bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 10),
        ).pack(pady=5)

        add_footer(self, "MedCare+ Appointment Management System", DOC_ACCENT)

        self._load_table()
        self._check_reminders()  # start 24-hour-before beep reminder loop

    def _refresh_suggested_medicines(self):
        """Look up the 7 common medicines for the selected doctor's
        specialization and show them in the panel below the doctor dropdown."""
        choice = self.doctor_var.get().strip()
        if not choice:
            return
        doctor_name = choice.split(" (")[0].strip()
        specialization = self._doctor_specialization.get(doctor_name)
        if not specialization:
            self.suggested_meds_label.config(text="No specialization data found for this doctor.")
            return

        conn = get_connection()
        rows = conn.execute(
            "SELECT medicine_name, usage_note FROM specialization_medicines WHERE specialization=? ORDER BY id",
            (specialization,),
        ).fetchall()
        conn.close()

        if not rows:
            self.suggested_meds_label.config(text=f"No reference medicines found for {specialization}.")
            return

        lines = [f"• {r['medicine_name']} — {r['usage_note']}" for r in rows]
        self.suggested_meds_label.config(
            text=f"Typically prescribed by a {specialization}:\n" + "\n".join(lines)
        )

    def _fetch_records(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM appointments ORDER BY date, time"
        ).fetchall()
        conn.close()
        return rows

    def _filtered_data(self):
        query = self.search_var.get().lower().strip()
        rows = self._fetch_records()
        if not query:
            return rows
        return [r for r in rows if query in (r["patient_name"] or "").lower()]

    def _load_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        data = self._filtered_data()
        for m in data:
            self.tree.insert(
                "",
                "end",
                iid=str(m["id"]),
                values=(m["patient_name"], m["phone"], m["date"], m["time"], m["doctor"]),
            )

        total = len(data)
        upcoming = 0
        for item in data:
            try:
                dt = datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
                if dt > datetime.now():
                    upcoming += 1
            except (KeyError, ValueError, TypeError):
                pass

        self.total_label.config(text=f"📅 Total Appointments : {total}")
        self.upcoming_label.config(text=f"⏰ Upcoming : {upcoming}")

    def _check_reminders(self):
        """Runs every 60 seconds. Beeps once for any appointment whose time
        is within the next 24 hours (and hasn't already been alerted)."""
        now = datetime.now()

        for item in self._fetch_records():
            try:
                dt = datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                continue

            key = f"{item['patient_name']}|{item['date']}|{item['time']}"
            time_left = dt - now

            # Within next 24 hours and still in the future -> beep once
            if timedelta(seconds=0) < time_left <= timedelta(hours=24) and key not in self._alerted_keys:
                self._alerted_keys.add(key)
                beep_alert()

                reminder_text = (
                    f"Reminder: {item['patient_name']}'s appointment with "
                    f"{item['doctor'] or 'Doctor'} is on {item['date']} at {item['time']} "
                    f"(within 24 hours)."
                )
                messagebox.showinfo("⏰ Appointment Reminder", reminder_text)

                # Real-time SMS alert (requires TWILIO_* credentials to be
                # filled in at the top of this file, plus a phone number on
                # the appointment). Fails silently if not configured.
                sms_text = (
                    f"MedCare+ Reminder: Hi {item['patient_name']}, your appointment with "
                    f"{item['doctor'] or 'Doctor'} is on {item['date']} at {item['time']}."
                )
                send_sms_reminder(item["phone"], sms_text)

        # Re-check every 60 seconds, only while this page still exists
        if self.winfo_exists():
            self.after(60000, self._check_reminders)

    def _save_record(self):
        patient_name = self.patient_var.get().strip()
        phone = self.phone_var.get().strip()
        date_val = self.date_var.get().strip()
        time_val = self.time_var.get().strip()
        doctor = self.doctor_var.get().strip()

        if not patient_name:
            messagebox.showwarning("Missing Info", "Patient name is required.")
            return

        conn = get_connection()
        if self.editing_id is not None:
            conn.execute(
                """UPDATE appointments SET patient_name=?, phone=?, date=?, time=?, doctor=?
                   WHERE id=?""",
                (patient_name, phone, date_val, time_val, doctor, self.editing_id),
            )
        else:
            conn.execute(
                """INSERT INTO appointments (patient_name, phone, date, time, doctor)
                   VALUES (?, ?, ?, ?, ?)""",
                (patient_name, phone, date_val, time_val, doctor),
            )
        conn.commit()
        conn.close()

        backup_db()  # auto-backup every save
        self._cancel_edit()
        self._load_table()

    def _delete_record(self):
        if self.editing_id is None:
            messagebox.showwarning("No Selection", "Select an appointment from the table first.")
            return
        conn = get_connection()
        conn.execute("DELETE FROM appointments WHERE id=?", (self.editing_id,))
        conn.commit()
        conn.close()

        backup_db()  # keep backup in sync after delete too
        self._cancel_edit()
        self._load_table()

    def _edit_selected(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        record_id = int(selection[0])

        conn = get_connection()
        m = conn.execute("SELECT * FROM appointments WHERE id=?", (record_id,)).fetchone()
        conn.close()
        if m is None:
            return

        self.editing_id = m["id"]
        self.patient_var.set(m["patient_name"] or "")
        self.phone_var.set(m["phone"] or "")
        self.date_var.set(m["date"] or "")
        self.time_var.set(m["time"] or "")
        self.doctor_var.set(m["doctor"] or "")
        self._refresh_suggested_medicines()

    def _cancel_edit(self):
        self.editing_id = None
        self.patient_var.set("")
        self.phone_var.set("")
        self.date_var.set("")
        self.time_var.set("")
        self.doctor_var.set("")
        self.suggested_meds_label.config(
            text="Select a doctor above to see their specialization's common medicines."
        )


# ================= BMI Page =================
class BMIPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_DARK)
        self.pack(fill="both", expand=True)

        tk.Label(
            self, text="⚖ BMI Calculator", bg=BG_DARK, fg=GOLD, font=("Segoe UI", 20, "bold")
        ).pack(pady=20)

        form = tk.Frame(self, bg=BG_MID, highlightbackground=GOLD, highlightthickness=1)
        form.pack(padx=40, pady=10, fill="x")

        self.weight_entry, self.weight_var = field_row(form, "Weight (kg)")
        self.height_entry, self.height_var = field_row(form, "Height (cm)")

        styled_button(form, "Calculate", self._calculate, color=GOLD, fg=BG_DARK, width=15).pack(pady=15)

        self.result_label = tk.Label(
            self, text="", bg=BG_DARK, fg="white", font=("Segoe UI", 14, "bold")
        )
        self.result_label.pack(pady=20)

    def _calculate(self):
        try:
            weight = float(self.weight_var.get())
            height_cm = float(self.height_var.get())
            height_m = height_cm / 100
            bmi = weight / (height_m ** 2)

            if bmi < 18.5:
                category = "Underweight"
            elif bmi < 25:
                category = "Normal"
            elif bmi < 30:
                category = "Overweight"
            else:
                category = "Obese"

            self.result_label.config(text=f"BMI: {bmi:.1f} ({category})")
        except (ValueError, ZeroDivisionError):
            messagebox.showwarning("Invalid Input", "Please enter valid numeric weight and height.")


# ================= Doctor Login Screen =================
class DoctorLoginScreen(tk.Frame):
    """Doctors log in with just their registered phone number — the doctors
    table only stores name/phone/email/specialization (no password field),
    matching the fields requested for the doctor database."""

    def __init__(self, master):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master

        tk.Label(
            self,
            text="🩺 Doctor Login",
            bg=BG_DARK,
            fg=DOC_ACCENT,
            font=("Segoe UI", 26, "bold"),
        ).pack(pady=30)

        card = tk.Frame(
            self, bg=BG_MID, highlightbackground=DOC_ACCENT, highlightthickness=2
        )
        card.pack(padx=40, pady=20, fill="x")

        tk.Label(
            card,
            text="Enter the phone number registered for your doctor account.",
            bg=BG_MID, fg=TEXT_LIGHT, font=("Segoe UI", 10),
        ).pack(pady=(15, 0))

        self.phone_entry, self.phone_var = field_row(card, "Phone")

        nav_frame = tk.Frame(card, bg=BG_MID)
        nav_frame.pack(pady=15)

        tk.Button(
            nav_frame,
            text="⬅ Back",
            font=("Segoe UI", 11, "bold"),
            bg="#607D8B",
            fg="white",
            relief="flat",
            width=12,
            cursor="hand2",
            command=self.master._show_login,
        ).pack(side="left", padx=10)

        tk.Button(
            nav_frame,
            text="Login ➡",
            font=("Segoe UI", 11, "bold"),
            bg=DOC_ACCENT,
            fg="white",
            relief="flat",
            width=12,
            cursor="hand2",
            command=self._submit,
        ).pack(side="left", padx=10)

    def _submit(self):
        phone = self.phone_var.get().strip()
        if not phone:
            messagebox.showwarning("Missing Info", "Please enter your phone number.")
            return

        conn = get_connection()
        row = conn.execute("SELECT * FROM doctors WHERE phone = ?", (phone,)).fetchone()
        conn.close()

        if row is None:
            messagebox.showerror("Login Failed", "No doctor account found with this phone number.")
            return

        self.destroy()
        self.master._show_doctor_dashboard(row["id"], row["name"], row["specialization"])


# ================= Doctor Dashboard =================
class DoctorDashboard(tk.Frame):
    """Read-only view for doctors: their own upcoming appointments, plus
    search access to patient medicine history. Doctors don't edit patient
    records directly — that stays with the patient side of the app."""

    def __init__(self, master, doctor_id, name, specialization):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master
        self.doctor_id = doctor_id
        self.name = name
        self.specialization = specialization

        self.content_area = None
        self._build_sidebar()
        self._build_content_area()
        self.show_home()

    def _build_sidebar(self):
        main_frame = tk.Frame(self, bg=BG_DARK)
        main_frame.pack(fill="both", expand=True)
        self.main_frame = main_frame

        sidebar = tk.Frame(main_frame, bg="#1B1330", width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="🩺 MedCare+", bg="#1B1330", fg=DOC_ACCENT, font=("Segoe UI", 18, "bold")
        ).pack(pady=20)

        tk.Label(
            sidebar, text=f"Dr. {self.name.replace('Dr. ', '')}", bg="#1B1330", fg="white",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(0, 2))
        tk.Label(
            sidebar, text=self.specialization, bg="#1B1330", fg=TEXT_LIGHT, font=("Segoe UI", 9),
        ).pack(pady=(0, 10))

        styled_button(sidebar, "🏠 Home", self.show_home, color=DOC_ACCENT, width=18).pack(pady=5)
        styled_button(
            sidebar, "📅 My Appointments", self.show_appointments, color=ACCENT2, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "💊 Patient Records", self.show_patient_records, color=ACCENT2, fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "➕ Suggest Medicine", self.show_suggest_medicine, color=DOC_ACCENT, fg="white", width=18
        ).pack(pady=5)

        tk.Frame(sidebar, bg="#1B1330").pack(expand=True)

        styled_button(
            sidebar, "⬅ Back", lambda: self.master._show_login(), color="#607D8B", fg="white", width=18
        ).pack(pady=5)
        styled_button(
            sidebar, "🚪 Logout", self.logout, color=DANGER, fg="white", width=18
        ).pack(pady=5)

    def _build_content_area(self):
        self.content_area = tk.Frame(self.main_frame, bg=BG_DARK)
        self.content_area.pack(side="left", fill="both", expand=True)

    def _clear_content(self):
        for widget in self.content_area.winfo_children():
            widget.destroy()

    def logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.master._show_login()

    def show_home(self):
        self._clear_content()
        tk.Label(
            self.content_area,
            text=f"Welcome back, Dr. {self.name.replace('Dr. ', '')}!",
            bg=BG_DARK, fg=DOC_ACCENT, font=("Segoe UI", 20, "bold"),
        ).pack(pady=40)
        tk.Label(
            self.content_area,
            text=f"Specialization: {self.specialization}",
            bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 12),
        ).pack()
        tk.Label(
            self.content_area,
            text="Use the sidebar to view your appointments or look up patient medicine history.",
            bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 11),
        ).pack(pady=10)

    def show_appointments(self):
        self._clear_content()

        tk.Label(
            self.content_area, text="📅 My Appointments", bg=BG_DARK, fg=DOC_ACCENT,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=15)

        conn = get_connection()
        # Match appointments booked under this doctor's name (the appointment
        # form stores "Dr. Name (Specialization)", so match on name prefix).
        rows = conn.execute(
            "SELECT * FROM appointments WHERE doctor LIKE ? ORDER BY date, time",
            (f"{self.name}%",),
        ).fetchall()
        conn.close()

        columns = ("patient_name", "phone", "date", "time")
        tree = ttk.Treeview(self.content_area, columns=columns, show="headings", height=12)
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
        tree.pack(fill="both", expand=True, padx=20, pady=5)

        upcoming = 0
        for r in rows:
            tree.insert("", "end", values=(r["patient_name"], r["phone"], r["date"], r["time"]))
            try:
                dt = datetime.strptime(f"{r['date']} {r['time']}", "%Y-%m-%d %H:%M")
                if dt > datetime.now():
                    upcoming += 1
            except (ValueError, TypeError):
                pass

        tk.Label(
            self.content_area,
            text=f"📅 Total : {len(rows)}   ⏰ Upcoming : {upcoming}",
            bg=BG_DARK, fg=GOLD, font=("Segoe UI", 11, "bold"),
        ).pack(pady=10)

    def show_patient_records(self):
        self._clear_content()

        tk.Label(
            self.content_area, text="💊 Patient Medicine Records", bg=BG_DARK, fg=DOC_ACCENT,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=15)

        search_frame = tk.Frame(self.content_area, bg=BG_DARK)
        search_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(search_frame, text="🔍 Search Patient", bg=BG_DARK, fg="white").pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(search_frame, textvariable=search_var).pack(side="left", padx=5)

        columns = ("patient_name", "age", "disease", "medicine", "time", "suggested_by")
        tree = ttk.Treeview(self.content_area, columns=columns, show="headings", height=12)
        for col in columns:
            heading = "Suggested By (Doctor)" if col == "suggested_by" else col.replace("_", " ").title()
            tree.heading(col, text=heading)
        tree.column("suggested_by", width=160)
        tree.pack(fill="both", expand=True, padx=20, pady=5)

        def load_table(*_args):
            for row in tree.get_children():
                tree.delete(row)
            conn = get_connection()
            query = search_var.get().lower().strip()
            if query:
                rows = conn.execute(
                    "SELECT * FROM medicines WHERE LOWER(patient_name) LIKE ? ORDER BY id DESC",
                    (f"%{query}%",),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM medicines ORDER BY id DESC").fetchall()
            conn.close()
            for m in rows:
                tree.insert(
                    "", "end",
                    values=(
                        m["patient_name"], m["age"], m["disease"], m["medicine"], m["time"],
                        m["suggested_by"] or "—",
                    ),
                )

        search_var.trace_add("write", load_table)
        load_table()

        tk.Label(
            self.content_area,
            text="🔒 Read-only view — doctors can look up history but medicine records are managed by patients.",
            bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 9),
        ).pack(pady=8)

    def show_suggest_medicine(self):
        """Lets a doctor suggest a medicine (from their specialization's
        reference list) for a named patient. The suggestion is logged in the
        suggested_medicines table AND written into the patient's medicines
        record with suggested_by set, so it shows up on both the doctor and
        patient sides of the app."""
        self._clear_content()

        tk.Label(
            self.content_area, text="➕ Suggest Medicine to a Patient", bg=BG_DARK, fg=DOC_ACCENT,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=15)

        form = tk.Frame(self.content_area, bg=BG_MID, highlightbackground=DOC_ACCENT, highlightthickness=1)
        form.pack(fill="x", padx=20, pady=5)

        patient_entry, patient_var = field_row(form, "Patient Name")
        disease_entry, disease_var = field_row(form, "Disease / Reason")

        # ---- Medicine dropdown, populated from this doctor's specialization ----
        med_row = tk.Frame(form, bg=BG_MID)
        med_row.pack(fill="x", pady=10)
        tk.Label(
            med_row, text="Medicine", bg=BG_MID, fg="white",
            font=("Segoe UI", 12, "bold"), width=17, anchor="w",
        ).pack(side="left", padx=10)

        conn = get_connection()
        med_rows = conn.execute(
            "SELECT medicine_name, usage_note FROM specialization_medicines WHERE specialization=? ORDER BY id",
            (self.specialization,),
        ).fetchall()
        conn.close()
        med_lookup = {r["medicine_name"]: r["usage_note"] for r in med_rows}

        medicine_var = tk.StringVar()
        medicine_combo = ttk.Combobox(
            med_row, textvariable=medicine_var, values=list(med_lookup.keys()), width=32, state="readonly",
        )
        medicine_combo.pack(side="left", padx=10)

        usage_label = tk.Label(
            form, text="", bg=BG_MID, fg=TEXT_LIGHT, font=("Segoe UI", 9, "italic"),
        )
        usage_label.pack(anchor="w", padx=27, pady=(0, 5))

        def on_medicine_selected(event=None):
            note = med_lookup.get(medicine_var.get(), "")
            usage_label.config(text=f"Typical use: {note}" if note else "")

        medicine_combo.bind("<<ComboboxSelected>>", on_medicine_selected)

        notes_entry, notes_var = field_row(form, "Notes (dosage/instructions)")

        status_label = tk.Label(
            self.content_area, text="", bg=BG_DARK, fg=GOLD, font=("Segoe UI", 10, "bold"),
        )
        status_label.pack(pady=5)

        def save_suggestion():
            patient_name = patient_var.get().strip()
            disease = disease_var.get().strip()
            medicine = medicine_var.get().strip()
            notes = notes_var.get().strip()

            if not patient_name or not medicine:
                messagebox.showwarning("Missing Info", "Patient name and medicine are required.")
                return

            today = datetime.now().strftime("%Y-%m-%d %H:%M")
            suggested_by = f"Dr. {self.name.replace('Dr. ', '')} ({self.specialization})"

            conn = get_connection()
            # 1. Log the suggestion in its own table (doctor-side history).
            conn.execute(
                """INSERT INTO suggested_medicines
                   (doctor_id, doctor_name, specialization, patient_name, medicine, notes, date_suggested)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.doctor_id, self.name, self.specialization, patient_name, medicine, notes, today),
            )
            # 2. Also add it to the patient's medicine records, tagged with
            #    who suggested it, so it appears in the Medicine page too.
            conn.execute(
                """INSERT INTO medicines (patient_name, age, disease, medicine, time, photo_path, suggested_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (patient_name, "", disease, medicine, today, None, suggested_by),
            )
            conn.commit()
            conn.close()
            backup_db()

            status_label.config(text=f"✅ Suggested '{medicine}' for {patient_name}.")
            patient_var.set("")
            disease_var.set("")
            notes_var.set("")
            medicine_var.set("")
            usage_label.config(text="")
            load_history()

        styled_button(form, "💾 Send Suggestion", save_suggestion, color=DOC_ACCENT, width=20).pack(pady=10)

        # ---- History of this doctor's past suggestions ----
        tk.Label(
            self.content_area, text="📜 Your Recent Suggestions", bg=BG_DARK, fg=DOC_ACCENT,
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(15, 5))

        hist_columns = ("patient_name", "medicine", "notes", "date_suggested")
        hist_tree = ttk.Treeview(self.content_area, columns=hist_columns, show="headings", height=8)
        for col in hist_columns:
            hist_tree.heading(col, text=col.replace("_", " ").title())
        hist_tree.pack(fill="both", expand=True, padx=20, pady=5)

        def load_history():
            for row in hist_tree.get_children():
                hist_tree.delete(row)
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM suggested_medicines WHERE doctor_id=? ORDER BY id DESC",
                (self.doctor_id,),
            ).fetchall()
            conn.close()
            for r in rows:
                hist_tree.insert(
                    "", "end",
                    values=(r["patient_name"], r["medicine"], r["notes"] or "", r["date_suggested"]),
                )

        load_history()


# ================= Manage Doctors (Admin) Screen =================
class ManageDoctorsScreen(tk.Frame):
    """Add/view/remove doctor accounts. Capped at MAX_DOCTORS (15) records,
    each storing name, phone number, email, and specialization."""

    def __init__(self, master):
        super().__init__(master, bg=BG_DARK)
        self.pack(fill="both", expand=True)
        self.master = master

        tk.Label(
            self, text="⚙ Manage Doctors", bg=BG_DARK, fg=DOC_ACCENT, font=("Segoe UI", 24, "bold"),
        ).pack(pady=20)

        form = tk.Frame(self, bg=BG_MID, highlightbackground=DOC_ACCENT, highlightthickness=1)
        form.pack(padx=40, pady=5, fill="x")

        self.name_entry, self.name_var = field_row(form, "Name")
        self.phone_entry, self.phone_var = field_row(form, "Phone")
        self.email_entry, self.email_var = field_row(form, "Email")
        self.spec_entry, self.spec_var = field_row(form, "Specialization")

        btn_row = tk.Frame(form, bg=BG_MID)
        btn_row.pack(pady=10)
        styled_button(btn_row, "➕ Add Doctor", self._add_doctor, color=DOC_ACCENT, width=15).pack(
            side="left", padx=5
        )
        styled_button(btn_row, "🗑 Remove Selected", self._remove_doctor, color=DANGER, width=18).pack(
            side="left", padx=5
        )

        self.count_label = tk.Label(
            self, text="", bg=BG_DARK, fg=GOLD, font=("Segoe UI", 11, "bold")
        )
        self.count_label.pack(pady=5)

        columns = ("name", "phone", "email", "specialization")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col.title())
        self.tree.pack(fill="both", expand=True, padx=20, pady=5)

        styled_button(
            self, "⬅ Back to Login", self.master._show_login, color="#607D8B", fg="white", width=18
        ).pack(pady=10)

        self._load_table()

    def _load_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        conn = get_connection()
        rows = conn.execute("SELECT * FROM doctors ORDER BY id").fetchall()
        conn.close()

        for d in rows:
            self.tree.insert(
                "", "end", iid=str(d["id"]),
                values=(d["name"], d["phone"], d["email"], d["specialization"]),
            )

        self.count_label.config(text=f"👨‍⚕️ Doctors : {len(rows)} / {MAX_DOCTORS}")

    def _add_doctor(self):
        name = self.name_var.get().strip()
        phone = self.phone_var.get().strip()
        email = self.email_var.get().strip()
        specialization = self.spec_var.get().strip()

        if not name or not phone or not specialization:
            messagebox.showwarning("Missing Info", "Name, phone, and specialization are required.")
            return

        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
        if count >= MAX_DOCTORS:
            conn.close()
            messagebox.showerror(
                "Doctor Limit Reached",
                f"Only {MAX_DOCTORS} doctors are allowed. Remove one before adding another.",
            )
            return

        exists = conn.execute("SELECT 1 FROM doctors WHERE phone = ?", (phone,)).fetchone()
        if exists:
            conn.close()
            messagebox.showerror("Duplicate", "A doctor with this phone number already exists.")
            return

        conn.execute(
            "INSERT INTO doctors (name, phone, email, specialization) VALUES (?, ?, ?, ?)",
            (name, phone, email, specialization),
        )
        conn.commit()
        conn.close()

        backup_db()
        self.name_var.set("")
        self.phone_var.set("")
        self.email_var.set("")
        self.spec_var.set("")
        self._load_table()

    def _remove_doctor(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Select a doctor from the table first.")
            return
        doctor_id = int(selection[0])

        conn = get_connection()
        conn.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
        conn.commit()
        conn.close()

        backup_db()
        self._load_table()


# ================= Main App =================
class MedCareApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MedCare+")
        self.geometry("900x650")
        self.configure(bg=BG_DARK)

        self.status_bar = add_status_bar(self)

        self.current_frame = None
        self._show_login()

    def _clear_frame(self):
        if self.current_frame is not None:
            self.current_frame.destroy()

    def _show_login(self):
        self._clear_frame()
        self.current_frame = LoginScreen(self)

    def _show_register(self):
        self._clear_frame()
        self.current_frame = RegisterScreen(self)

    def _show_welcome(self, name, phone, age):
        self._clear_frame()
        self.current_frame = WelcomeScreen(self, name, phone, age, self._show_dashboard)

    def _show_dashboard(self, name, phone, age):
        self._clear_frame()
        self.current_frame = Dashboard(self, name, phone, age)

    def _show_doctor_login(self):
        self._clear_frame()
        self.current_frame = DoctorLoginScreen(self)

    def _show_doctor_dashboard(self, doctor_id, name, specialization):
        self._clear_frame()
        self.current_frame = DoctorDashboard(self, doctor_id, name, specialization)

    def _show_manage_doctors(self):
        self._clear_frame()
        self.current_frame = ManageDoctorsScreen(self)


def main():
    init_db()

    root = tk.Tk()
    root.withdraw()  # hide the empty root window used only to host the splash

    splash = Splash(root)
    root.wait_window(splash)
    root.destroy()

    app = MedCareApp()
    app.mainloop()


if __name__ == "__main__":
    main()
