# MedCare+ — Medicine & Appointment Management System

MedCare+ is a desktop application (built with Python and Tkinter) for
managing patients, medicines, appointments, and doctors, backed by a real
SQLite database. It has two sides: a **patient portal** for tracking
medicines, appointments, and BMI, and a **doctor portal** for viewing
appointments, looking up patient medicine history, and suggesting
medicines from a specialization-based reference list.

## Features

### Patient Side
- **Register / Login** — patient accounts stored in the database (name, phone, age, password).
- **Medicine Records** — add, edit, delete, and search medicine entries per patient, with an optional photo upload and live thumbnail preview.
- **Appointments** — book appointments with any registered doctor, with automatic 24-hour-before beep + popup reminders, and optional SMS reminders via Twilio.
- **Suggested Medicines Panel** — when booking an appointment, the 7 most common medicines for the selected doctor's specialization are shown automatically.
- **BMI Calculator** — quick BMI check with category feedback.

### Doctor Side
- **Doctor Login** — doctors log in with their registered phone number.
- **Doctor Dashboard** — home overview, "My Appointments" (auto-filtered to that doctor), and "Patient Records" (read-only search across all patient medicine history).
- **Suggest Medicine** — a doctor can suggest a medicine to a named patient, chosen from a curated list of 7 real, commonly-prescribed medicines for their specialization. Every suggestion is:
  - logged in the doctor's own suggestion history, **and**
  - written into the patient's medicine records tagged with **"Suggested By"**, so it's visible from both the doctor and patient side.

### Admin
- **Manage Doctors** — add/view up to 15 doctors, each with name, phone, email, and specialization.
- **Backup / Restore** — atomic SQLite backup and restore using the built-in backup API.

## Specializations & Medicine Reference List

The app ships with 15 specializations, each pre-loaded with 7 real,
commonly-prescribed medicines (with a short usage note) used to power the
"Suggest Medicine" feature and the appointment-page suggestion panel:

| Specialization | Example Medicines |
|---|---|
| Cardiologist | Atorvastatin, Amlodipine, Metoprolol, Aspirin, Losartan, Clopidogrel, Furosemide |
| Dermatologist | Tretinoin, Clindamycin Gel, Hydrocortisone, Ketoconazole Cream, Cetirizine, Isotretinoin, Fusidic Acid |
| Neurologist | Sodium Valproate, Levetiracetam, Gabapentin, Sumatriptan, Amitriptyline, Carbamazepine, Propranolol |
| Pediatrician | Paracetamol Syrup, Amoxicillin Suspension, ORS, Cetirizine Syrup, Vitamin D3 Drops, Salbutamol Syrup, Zinc Sulphate |
| Orthopedic Surgeon | Ibuprofen, Diclofenac Gel, Calcium+D3, Tramadol, Glucosamine, Methylcobalamin, Etoricoxib |
| General Physician | Paracetamol, Amoxicillin, Omeprazole, Cetirizine, Azithromycin, Metformin, Ibuprofen |
| ENT Specialist | Amoxicillin-Clavulanate, Fluticasone Spray, Cetirizine, Xylometazoline, Azithromycin, Betadine Gargle, Levocetirizine |
| Dentist | Amoxicillin, Metronidazole, Ibuprofen, Chlorhexidine Mouthwash, Paracetamol, Clove Oil, Diclofenac |
| Psychiatrist | Sertraline, Escitalopram, Alprazolam, Fluoxetine, Quetiapine, Mirtazapine, Clonazepam |
| Gynecologist | Folic Acid, Iron+Folic Acid, Clomiphene Citrate, Mefenamic Acid, Contraceptive Pill, Metronidazole, Progesterone |
| Ophthalmologist | Moxifloxacin Drops, Timolol Drops, Artificial Tears, Prednisolone Drops, Ketorolac Drops, Latanoprost, Olopatadine |
| Endocrinologist | Metformin, Insulin Glargine, Levothyroxine, Glimepiride, Carbimazole, Sitagliptin, Vitamin D3 |
| Gastroenterologist | Omeprazole, Pantoprazole, Domperidone, Rifaximin, Ondansetron, Lactulose, Mesalamine |
| Pulmonologist | Salbutamol Inhaler, Budesonide Inhaler, Montelukast, Theophylline, Azithromycin, Prednisolone, N-Acetylcysteine |
| Urologist | Tamsulosin, Finasteride, Ciprofloxacin, Nitrofurantoin, Sildenafil, Potassium Citrate, Oxybutynin |

## Tech Stack

- **Language:** Python 3
- **GUI:** Tkinter / ttk
- **Database:** SQLite3 (single file, `medcare.db`)
- **Optional integrations:** Pillow (photo preview), Twilio (SMS reminders), winsound (Windows beep alerts)

## Getting Started

### Requirements
- Python 3.8+
- Tkinter (usually bundled with Python; on Linux install via `sudo apt install python3-tk`)
- Optional: `pip install Pillow` for photo previews, `pip install twilio` for SMS reminders

### Run

```bash
python medcare_plus.py
```

On first run, the app automatically creates `medcare.db` and seeds it with
15 demo patients, 15 demo doctors (one per specialization), and the full
105-medicine specialization reference list.

### Demo Login
- **Patient:** phone `9876543210`, password `pass123` (or use any of the other 14 seeded patients)
- **Doctor:** any of the 15 seeded doctor phone numbers, e.g. `9812345001` (Dr. Ramesh Kumar, Cardiologist)

## Database Schema (Key Tables)

| Table | Purpose |
|---|---|
| `users` | Patient accounts (name, phone, age, password) |
| `doctors` | Doctor accounts (name, phone, email, specialization) — capped at 15 |
| `medicines` | Patient medicine records, including `suggested_by` when added via a doctor suggestion |
| `appointments` | Patient ↔ doctor appointment bookings |
| `specialization_medicines` | Reference list of 7 real medicines per specialization |
| `suggested_medicines` | Full log of every medicine a doctor has suggested, with patient, notes, and date |

Existing databases created before this update are automatically migrated
(the `suggested_by` column is added in place) — no data is lost.

## Visual Theme

The Appointment page uses the same purple accent (`#9B59B6`) as the Doctor
Login and Doctor Dashboard screens, so the doctor-facing and appointment-
booking parts of the app feel like one connected experience.

## Project Structure

```
medcare_plus.py     # Single-file application (UI + database layer)
medcare.db           # SQLite database (auto-created on first run)
backup_medcare.db     # Auto-backup, refreshed on every save/delete
medicine_photos/     # Uploaded patient photos
```

## Known Limitations / Future Scope

- Doctor passwords are not required (phone-number-only login) — a password field could be added for stronger security.
- Medicine reference data is a static seed list, not linked to a live drug database.
- No role-based admin authentication for "Manage Doctors."
- SMS reminders require manually filled-in Twilio credentials.
