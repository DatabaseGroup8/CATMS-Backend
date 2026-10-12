"""Seed *only* a fresh local CATMS MySQL database with synthetic test data.

Run from directory containing manage.py:
  python seed_catms.py

This intentionally uses installed stored procedures for consultation, insurance,
and patient payments, rather than fabricating invoice/claim/payment balances.
"""

import json
import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CATMS__backend.settings")
import django  # noqa: E402

django.setup()
from django.contrib.auth.hashers import make_password  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402

ROOT = Path(__file__).resolve().parent
MONEY = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def abort(message):
    raise SystemExit(f"SEED REFUSED: {message}")


def sql(statement, params=()):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.lastrowid


def one(statement, params=()):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchone()[0]


def procedure(name, arguments, outs):
    """Read procedure OUT vars on same connection; surface SQL-defined failure reason."""
    var_names = [f"@catms_seed_out_{i}" for i in range(len(outs))]
    # name and output names are fixed values defined in this script, not user data.
    with connection.cursor() as cursor:
        cursor.execute("SET " + ", ".join(f"{v}=NULL" for v in var_names))
        arg_text = ", ".join(["%s"] * len(arguments) + var_names)
        cursor.execute(f"CALL {name}({arg_text})", arguments)
        while cursor.nextset():
            pass
        cursor.execute("SELECT " + ", ".join(var_names))
        values = dict(zip(outs, cursor.fetchone()))
    if "success" in values and not values["success"]:
        abort(f"{name} failed: {values.get('message')}; partial seed may exist")
    return values


def ensure_local_empty_database():
    d = connection.settings_dict
    database_name = d.get("NAME")
    host = d.get("HOST")
    if database_name != "catms_local" or host not in ("127.0.0.1", "localhost"):
        abort(f"Requires DB_NAME=catms_local and DB_HOST=127.0.0.1; got {database_name!r}/{host!r}")
    if os.getenv("CATMS_SEED_CONFIRM") != "YES_LOCAL_DEMO_ONLY":
        abort("Set CATMS_SEED_CONFIRM=YES_LOCAL_DEMO_ONLY in the terminal")
    password = os.getenv("CATMS_DEMO_PASSWORD", "")
    if len(password) < 12:
        abort("Set CATMS_DEMO_PASSWORD to a unique demo-only password (at least 12 characters)")
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE(), @@hostname, VERSION()")
        database, hostname, version = cursor.fetchone()
    print(f"Connected to {database} ({hostname}, MySQL {version})")
    tables = (
        "Address", "User", "Branch", "Employee", "Doctor", "Patient",
        "Condition_category", "Conditions", "Patient_condition",
        "Specialization", "Doctor_Specialization", "Time_Slot", "Appointment",
        "Medical_record", "Medication", "Prescription", "Treatment_Category",
        "Treatment_Catalogue", "Treatment", "Invoice", "Payment",
        "Insurance_Packages", "Insurance", "Claims", "consultation_record", "Manager"
    )
    for table in tables:
        if one(f"SELECT COUNT(*) FROM `{table}`"):
            abort(f"Table {table} already has records. This script is fresh-database-only.")
    routine_names = (
        "FinalizeConsultationBill", "ApplyInvoiceInsurance", "RecordPayment",
        "ResolveInsuranceClaim", "RecordInsuranceSettlement", "BookAppointment"
    )
    available = one(
        "SELECT COUNT(*) FROM information_schema.ROUTINES "
        "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_TYPE='PROCEDURE' "
        f"AND ROUTINE_NAME IN ({', '.join(['%s'] * len(routine_names))})",
        routine_names
    )
    if available != len(routine_names):
        abort("Expected stored procedures are not all installed")
    print("Local-only and empty-database checks passed. Starting seed...")
    return password


BRANCHES = [
    ("Colombo Central Clinic", "Colombo", "42 Galle Road", "Colombo 03", "Western", "00300"),
    ("Kandy Lake Clinic", "Kandy", "18 Peradeniya Road", "Kandy", "Central", "20000"),
    ("Galle Fort Clinic", "Galle", "9 Lighthouse Street", "Galle", "Southern", "80000"),
]

# All names, contact details, DOBs, and ID numbers below are fictitious.
PATIENT_NAMES = [
    "Nethmi Jayasinghe", "Sahan Wickramasinghe", "Dilushi Perera", "Kavindu Fernando",
    "Amaya Silva", "Nimesh Gunawardena", "Thejani Abeysekara", "Kasun Ranasinghe",
    "Sachini Rathnayake", "Isuru Madushanka", "Tharushi Kumari", "Dinuka Samaraweera",
    "Hiruni Herath", "Malith Bandara", "Nadeesha Ekanayake", "Ravindu Dissanayake",
    "Piumi Senanayake", "Supun Liyanage", "Chamath Jayawardena", "Ishani Weerakoon",
    "Pavithra Udara", "Hasini Pathirana", "Dulaj Rajapaksha", "Shavindi Nirosha",
    "Ayesh Fernando", "Rashmi Wijesundara", "Oshan De Silva", "Dinithi Karunaratne",
    "Janith Peiris", "Yasara Madushani", "Mihiran Hettiarachchi", "Ashen Gamage",
    "Shakya Rathnayake", "Vihanga Sandaruwan", "Mandira Samarasinghe", "Sithum Akalanka",
]

TEAM = [
    # branch index, role, full name, email local-part, extra doctor specialization
    (0, "Manager", "Madhavi Samarasinghe", "manager.colombo", None),
    (0, "Receptionist", "Ruwani Perera", "reception.colombo", None),
    (0, "Receptionist", "Dinusha Fernando", "reception2.colombo", None),
    (0, "Doctor", "Dr Anjali Jayawardena", "doctor.anjali", "General Medicine"),
    (0, "Doctor", "Dr Nuwan Wijeratne", "doctor.nuwan", "Cardiology"),
    (1, "Manager", "Nimali Herath", "manager.kandy", None),
    (1, "Receptionist", "Pasan Ekanayake", "reception.kandy", None),
    (1, "Doctor", "Dr Harsha Gunawardena", "doctor.harsha", "Pediatrics"),
    (1, "Doctor", "Dr Shalini Kumari", "doctor.shalini", "General Medicine"),
    (2, "Manager", "Hiranya Abeykoon", "manager.galle", None),
    (2, "Receptionist", "Sanjeewa Peiris", "reception.galle", None),
    (2, "Doctor", "Dr Malini Dias", "doctor.malini", "Dermatology"),
    (2, "Doctor", "Dr Suren Karunarathne", "doctor.suren", "General Medicine"),
]

CATEGORIES = [
    ("General Medicine", "General outpatient and primary care"),
    ("Cardiology", "Cardiovascular assessment"),
    ("Pediatrics", "Children's health"),
    ("Dermatology", "Skin health"),
    ("Orthopedics", "Bones, joints, muscles"),
]

MEDICATIONS = [
    ("Paracetamol 500 mg", "Demo Pharma", "Tablet", "Liver disease", "Nausea", "12.00"),
    ("Cetirizine 10 mg", "Sunrise Labs", "Tablet", "Hypersensitivity", "Drowsiness", "25.00"),
    ("Amoxicillin 500 mg", "Demo Pharma", "Capsule", "Penicillin allergy", "Diarrhoea", "55.00"),
    ("Omeprazole 20 mg", "Lanka Generics", "Capsule", "Hypersensitivity", "Headache", "38.00"),
    ("Metformin 500 mg", "Wellcare Pharma", "Tablet", "Severe renal impairment", "Nausea", "18.00"),
    ("Amlodipine 5 mg", "Wellcare Pharma", "Tablet", "Hypotension", "Swelling", "22.00"),
    ("Ibuprofen 400 mg", "Demo Pharma", "Tablet", "Active peptic ulcer", "Stomach upset", "28.00"),
    ("Oral Rehydration Salts", "Healthline", "Sachet", "Follow clinical guidance", "Occasional nausea", "70.00"),
    ("Salbutamol inhaler", "Sunrise Labs", "Inhaler", "Hypersensitivity", "Tremor", "850.00"),
    ("Atorvastatin 10 mg", "Lanka Generics", "Tablet", "Active liver disease", "Muscle pain", "42.00"),
]

TREATMENTS = [
    # category, name, price, minutes, eligible
    ("Consultation", "General consultation", "1500.00", "20 min", False),
    ("Consultation", "Specialist consultation", "2500.00", "30 min", False),
    ("Laboratory", "Full blood count", "1200.00", "15 min", True),
    ("Laboratory", "Fasting blood sugar", "750.00", "10 min", True),
    ("Diagnostics", "12-lead ECG", "2800.00", "20 min", True),
    ("Diagnostics", "Chest X-ray", "4500.00", "25 min", True),
    ("Procedures", "Wound dressing", "1800.00", "20 min", True),
    ("Procedures", "Nebulization", "1600.00", "15 min", True),
    ("Physiotherapy", "Physiotherapy session", "3200.00", "40 min", True),
    ("Diagnostics", "Blood pressure assessment", "400.00", "10 min", False),
]

CONDITIONS = [
    ("Respiratory", "Upper respiratory tract infection", "Common respiratory presentation"),
    ("Respiratory", "Asthma", "Chronic airway condition"),
    ("Cardiovascular", "Hypertension", "High blood pressure"),
    ("Cardiovascular", "Hyperlipidemia", "Elevated blood lipids"),
    ("Metabolic", "Type 2 diabetes", "Glucose metabolism disorder"),
    ("Skin", "Eczema", "Inflammatory skin condition"),
    ("Musculoskeletal", "Low back pain", "Musculoskeletal pain"),
    ("General", "Fever", "Elevated body temperature"),
]


def seed():
    pwd = ensure_local_empty_database()
    today = timezone.localdate()
    staff = []
    doctors = []
    branches = []
    treatments = []
    meds = []
    patient_ids = []
    package_ids = []
    insurance_for_patient = {}
    appointment_ids = []
    invoice_ids = []
    accounts = []

    for name, district, line, city, province, postcode in BRANCHES:
        address_id = sql(
            "INSERT INTO Address (address_line_1,city,province,postal_code) VALUES (%s,%s,%s,%s)",
            (line, city, province, postcode)
        )
        branches.append(sql(
            "INSERT INTO Branch (branch_name,district,address_id) VALUES (%s,%s,%s)",
            (name, district, address_id)
        ))

    specs = {}
    for name, description in CATEGORIES:
        specs[name] = sql(
            "INSERT INTO Specialization (specialization_name,description) VALUES (%s,%s)",
            (name, description)
        )

    for idx, (bidx, role, name, email_prefix, specialty) in enumerate(TEAM):
        addr_id = sql("INSERT INTO Address (address_line_1,city,province,postal_code) VALUES (%s,%s,%s,%s)",
                      (f"Demo address {idx+1}", BRANCHES[bidx][3], BRANCHES[bidx][4], BRANCHES[bidx][5]))
        email = f"{email_prefix}@catms.test"
        uid = sql("""INSERT INTO `User` (address_id,full_name,NIC,gender,DOB,email,contact_no,Password_hash)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                  (addr_id, name, f"STAFF-DEMO-{idx+1:03}", "Female" if idx % 2 else "Male",
                   date(1980 + idx % 12, (idx % 12)+1, 10), email,
                   f"077000{idx+1000:04}", make_password(pwd)))
        salary = {"Manager": 185000, "Receptionist": 78000, "Doctor": 280000}[role]
        eid = sql("""INSERT INTO Employee (user_id,branch_id,role,salary,joined_date,status)
                  VALUES (%s,%s,%s,%s,%s,'Active')""",
                  (uid, branches[bidx], role, salary, today-timedelta(days=800-idx*22)))
        staff.append({"employee_id": eid, "branch_id": branches[bidx], "role": role, "name": name, "email": email})
        accounts.append({"email": email, "branch_id": branches[bidx], "role": role})
        if role == "Doctor":
            did = sql("INSERT INTO Doctor (employee_id,room_no,medical_licence_number) VALUES (%s,%s,%s)",
                      (eid, f"R{idx+1:02}", f"DEMO-SLMC-{idx+1:04}"))
            sql("INSERT INTO Doctor_Specialization (specialization_id,doctor_id) VALUES (%s,%s)",
                (specs[specialty], did))
            doctors.append({"doctor_id": did, "employee_id": eid, "branch_id": branches[bidx], "specialty": specialty})
        if role == "Manager":
            sql("INSERT INTO Manager (branch_id,employee_id) VALUES (%s,%s)", (branches[bidx], eid))

    for idx, name in enumerate(PATIENT_NAMES):
        bidx = idx // 12
        dob = date(1970 + (idx*3) % 36, 1 + idx % 12, 1 + idx % 25)
        pid = sql("""INSERT INTO Patient (registered_branch_id,contact_no,full_name,NIC,gender,DOB)
                     VALUES (%s,%s,%s,%s,%s,%s)""",
                  (branches[bidx], f"07000{idx+10000:05}", name, f"PAT-DEMO-{idx+1:04}",
                   "Female" if idx%2 == 0 else "Male", dob))
        patient_ids.append(pid)

    cat_ids = {}
    for name in ("Respiratory", "Cardiovascular", "Metabolic", "Skin", "Musculoskeletal", "General"):
        cat_ids[name] = sql("INSERT INTO Condition_category (category_name) VALUES (%s)", (name,))
    condition_ids = []
    for category, name, description in CONDITIONS:
        condition_ids.append(sql("INSERT INTO Conditions (condition_category_id,condition_name,description) VALUES (%s,%s,%s)",
                                 (cat_ids[category],name,description)))
    for i, pid in enumerate(patient_ids):
        if i%3 != 2:
            sql("""INSERT INTO Patient_condition (patient_id,condition_id,diagnosed_date,is_chronic,current_status)
                  VALUES (%s,%s,%s,%s,%s)""",
                (pid, condition_ids[i%len(condition_ids)], today-timedelta(days=30+i*8),
                 1 if i%4==0 else 0, "Under Treatment" if i%5==0 else "Stable"))

    for generic, maker, form, contraindication, effects, price in MEDICATIONS:
        meds.append(sql("""INSERT INTO Medication (generic_name,manufacturer,form,contraindications,side_effects,price)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
                        (generic,maker,form,contraindication,effects,price)))
    treatment_categories = {}
    for name, description in (
        ("Consultation", "Clinic assessment visits"),
        ("Laboratory", "Laboratory tests"),
        ("Diagnostics", "Diagnostic investigations"),
        ("Procedures", "Outpatient procedures"),
        ("Physiotherapy", "Therapeutic exercise sessions"),
    ):
        treatment_categories[name] = sql("INSERT INTO Treatment_Category (category_name,description) VALUES (%s,%s)", (name,description))
    for category, name, price, duration, eligible in TREATMENTS:
        treatments.append(sql("""INSERT INTO Treatment_Catalogue
                  (treatment_category_id,treatment_name,base_price,duration,updated_date,insurance_eligible)
                  VALUES (%s,%s,%s,%s,%s,%s)""",
                  (treatment_categories[category],name,price,duration,today,1 if eligible else 0)))

    for name, copay in (("Care Basic", "30.00"), ("Care Plus", "20.00"), ("Family Advantage", "10.00")):
        package_ids.append(sql("""INSERT INTO Insurance_Packages
            (package_name,annual_name,copayment_percentage,updated_date,started_date)
            VALUES (%s,%s,%s,%s,%s)""", (name,"Annual",copay,today,today-timedelta(days=400))))
    for i,pid in enumerate(patient_ids):
        if i%4!=3:
            iid = sql("""INSERT INTO Insurance
                    (patient_id,insurance_package_id,updated_date,status,started_date,end_date)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (pid,package_ids[i%len(package_ids)],today,"Active",today-timedelta(days=330),today+timedelta(days=365)))
            insurance_for_patient[pid]=iid
        elif i%8 == 3:
            sql("""INSERT INTO Insurance
                    (patient_id,insurance_package_id,updated_date,status,started_date,end_date)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (pid,package_ids[i%len(package_ids)],today,"Expired",today-timedelta(days=700),today-timedelta(days=30)))

    employees_by_branch = {
        b: {role: next(item["employee_id"] for item in staff
                       if item["branch_id"] == b and item["role"] == role)
            for role in ("Manager", "Receptionist")}
        for b in branches
    }

    # Past appointments create reportable activity; today's and future sessions
    # are available for actual receptionist/doctor UI testing.
    days = (-8,-5,-2,0,1,4)
    slots = []
    for d in doctors:
        for offset in days:
            day = today + timedelta(days=offset)
            # One session closed with bookings, one closed and empty.
            unavailable = ((d["doctor_id"] % 3 == 1 and offset == 4)
                           or (d["doctor_id"] % 3 == 2 and offset == 1))
            start, end = ("09:00:00", "12:00:00") if d["doctor_id"]%2 else ("14:00:00", "17:00:00")
            slot_id = sql("""INSERT INTO Time_Slot
                (doctor_id,branch_id,available_date,start_time,end_time,available)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (d["doctor_id"],d["branch_id"],day,start,end,0 if unavailable else 1))
            slots.append((slot_id,d,offset,unavailable))

    completed = []
    for slot_idx, (slot_id,d,offset,unavailable) in enumerate(slots):
        bidx = branches.index(d["branch_id"])
        # All branches share the Patient registry; most patients are local.
        candidates = patient_ids[bidx*12:(bidx+1)*12]
        n = 3 if offset < 0 else (2 if offset in (0,1) else 1)
        if unavailable and offset == 4:
            n = 0
        for queue in range(1,n+1):
            patient = candidates[(slot_idx*3+queue*2) % len(candidates)]
            if offset < 0:
                status = "Cancelled" if queue == 3 else "Completed"
            else:
                status = "Scheduled"
            appointment_id = sql("""INSERT INTO Appointment
                (patient_id,time_slot_id,appointment_number,type,status,notes,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (patient,slot_id,queue,"FollowUp" if queue==2 else "Consultation",status,
                 "Synthetic training appointment",min(today+timedelta(days=offset-3),today),
                 today+timedelta(days=offset) if offset<0 else today))
            appointment_ids.append(appointment_id)
            if status == "Completed":
                completed.append((appointment_id,patient,d["branch_id"],slot_idx,queue))

    # Leave three completed appointments unbilled for the receptionist's
    # completed-appointments / finalize workflow.
    unbilled = completed[-3:]
    billed = completed[:-3]
    outcomes = {"no_insurance":0,"submitted":0,"approved":0,"paid":0,"partially_paid":0,"rejected":0}
    for i,(appointment_id,patient,branch_id,slot_idx,queue) in enumerate(billed):
        receptionist = employees_by_branch[branch_id]["Receptionist"]
        med_data = [{
            "medication_id": meds[i%len(meds)],
            "quantity": 10 if i%2==0 else 5,
            "dosage": "As directed", "frequency": "Daily",
            "duration_days": 5 if i%2 else 10,
            "instructions": "Synthetic case: use only as directed by an authorized clinician"
        }]
        treatment_data = [
            {"treatment_service_code": treatments[i%2]},
            {"treatment_service_code": treatments[2+(i%7)]},
        ]
        finished = procedure("FinalizeConsultationBill", [
            appointment_id,receptionist,
            "Demo consultation — fatigue or routine check-up",
            "Synthetic symptoms for workflow testing only",
            "Recorded by receptionist from fictional clinician instructions",
            json.dumps(med_data),json.dumps(treatment_data)
        ], ("medical_record_id","invoice_id","subtotal","success","message"))
        iid = finished["invoice_id"]
        invoice_ids.append(iid)

        # Apply coverage only where eligible and a valid policy exists; always
        # do so *before* recording patient payments.
        if i % 4 != 0 and patient in insurance_for_patient:
            coverage = procedure("ApplyInvoiceInsurance", [iid,insurance_for_patient[patient],receptionist],
                                 ("claim_amount","success","message"))
            pattern = i%5
            if pattern == 0:
                outcomes["submitted"] += 1
            else:
                manager = employees_by_branch[branch_id]["Manager"]
                claim = money(coverage["claim_amount"])
                approved = money(0 if pattern==4 else claim if pattern in (1,3) else claim*Decimal("0.60"))
                procedure("ResolveInsuranceClaim",[iid,manager,approved],("success","message"))
                if approved == 0:
                    outcomes["rejected"] += 1
                else:
                    outcomes["approved"] += 1
                    if pattern == 3:
                        procedure("RecordInsuranceSettlement",[iid,manager,approved],("success","message"))
                        outcomes["paid"] += 1
                    elif pattern == 2:
                        procedure("RecordInsuranceSettlement",[iid,manager,money(approved/2)],("success","message"))
                        outcomes["partially_paid"] += 1
        else:
            outcomes["no_insurance"] += 1

        remain = money(one("SELECT CalculateOutstandingBalance(%s)",(iid,)))
        # Leave some fully unpaid, some partially paid, and some fully paid.
        pay_pattern = i%4
        amounts = []
        if pay_pattern == 1:
            amounts = [remain]
        elif pay_pattern == 2:
            first = money(remain*Decimal("0.30"))
            if first>0 and first<remain:
                second = money(remain*Decimal("0.20"))
                amounts = [first,second]
        elif pay_pattern == 3:
            first = money(remain/2)
            if first>0 and first<remain:
                amounts = [first, money(remain-first)]
        for j, amt in enumerate(amounts):
            procedure("RecordPayment",[
                iid,receptionist,amt,"Cash" if j%2==0 else "Card",str(uuid.uuid4())
            ],("payment_id","success","message"))

    totals = {
        "branches": len(branches), "staff": len(staff), "doctors": len(doctors),
        "patients": len(patient_ids), "slots": len(slots),
        "appointments": len(appointment_ids), "completed": len(completed),
        "completed_not_invoiced":len(unbilled),"invoices":len(invoice_ids),
        "payments":one("SELECT COUNT(*) FROM Payment"),
        "claims":one("SELECT COUNT(*) FROM Claims"),
        "active_insurance":one("SELECT COUNT(*) FROM Insurance WHERE status='Active'"),
    }
    manifest = {
        "note":"SYNTHETIC LOCAL DEVELOPMENT ONLY. Password is intentionally not written to this file.",
        "seed_date": today.isoformat(), "accounts":accounts,
        "counts":totals,"claim_example_outcomes":outcomes,
        "completed_unbilled_appointment_ids":[x[0] for x in unbilled],
        "branch_ids":branches,
        "example_invoice_ids":invoice_ids[:6],
        "tip":"For doctor appointment screens use today's date; for revenue reports filter invoice date = seed_date."
    }
    target = ROOT/"CATMS_seed_manifest.json"
    target.write_text(json.dumps(manifest,indent=2,default=str),encoding="utf-8")
    print("\nSEED COMPLETE:\n",json.dumps(totals,indent=2))
    print("Demo login emails/branch IDs saved to:",target)
    print("All accounts use your CATMS_DEMO_PASSWORD environment variable.")


if __name__ == "__main__":
    try:
        seed()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"SEED ERROR: {exc}",file=sys.stderr)
        print("A partial seed may exist. Do NOT simply run again; reset a development-only DB first.",file=sys.stderr)
        raise
