import urllib.request
import json
import os

base_url = os.environ.get("GATEWAY_URL", "http://localhost:5000")

def get(path):
    req = urllib.request.Request(f"{base_url}{path}")
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def post(path, data):
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def put(path, data):
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

print("=============================================")
print("  CareHub Integration Testing Suite          ")
print("=============================================")

# Cleanup test user from previous run to ensure test idempotency
try:
    from db_client import get_db_collection
    get_db_collection("users").delete_one({"username": "tester"})
except Exception as e:
    pass

# 0. Authentication service test
print("\n[0/6] Testing User Registration & Login...")
# Register new user
reg_body = {
    "username": "tester",
    "password": "TestPassword123!",
    "role": "Patient"
}
reg_res = post("/api/auth/register", reg_body)
print(f"  -> User registered: username={reg_res.get('username')}, role={reg_res.get('role')}")

# Login
login_body = {
    "username": "tester",
    "password": "TestPassword123!"
}
login_res = post("/api/auth/login", login_body)
token = login_res.get("token")
print(f"  -> User logged in successfully. Received token: {token[:10]}...")

# Verify token
verify_res = post("/api/auth/verify", {"token": token})
print(f"  -> Token verified: username={verify_res.get('username')}, role={verify_res.get('role')}")

# 1. Patients test
print("\n[1/6] Querying patient registry (GET /api/patient)...")
patient_res = get("/api/patient")
patients = patient_res["patients"]
print(f"  -> Found {len(patients)} seeded patient(s).")
for p in patients:
    print(f"     * [{p.get('_id')}] {p.get('name')} (Blood: {p.get('blood_group')})")

print("\n[2/6] Registering new patient (POST /api/patient)...")
new_patient = {
    "name": "Bruce Wayne",
    "dob": "1975-02-19",
    "gender": "Male",
    "phone": "555-0012",
    "email": "bruce@waynecorp.com",
    "blood_group": "AB+",
    "medical_history": ["Acute insomnia", "Fractured ribs history"]
}
added_patient = post("/api/patient", new_patient)
patient_id = added_patient.get("id") or added_patient.get("_id")
print(f"  -> Patient registered successfully. Generated ID: {patient_id}")

# 2. Doctors test
print("\n[3/6] Fetching available clinicians (GET /api/doctor)...")
doctor_res = get("/api/doctor")
doctors = doctor_res["doctors"]
print(f"  -> Found {len(doctors)} doctors.")
doctor_id = doctors[0]["_id"] # Use the first seeded doctor
print(f"  -> Selected Doctor ID for consultation: {doctor_id} ({doctors[0]['name']})")

# 3. Appointments test
print("\n[4/6] Scheduling new appointment (POST /api/appointment)...")
new_appointment = {
    "patient_id": patient_id,
    "doctor_id": doctor_id,
    "date": "2026-06-15",
    "time": "09:00 AM",
    "reason": "General checkup & sleep disorder consult",
    "status": "Scheduled"
}
added_appointment = post("/api/appointment", new_appointment)
app_id = added_appointment.get("id") or added_appointment.get("_id")
print(f"  -> Appointment scheduled. Confirmation ID: {app_id}")

# 4. Prescriptions test
print("\n[5/6] Creating medical prescription (POST /api/prescription)...")
new_prescription = {
    "patient_id": patient_id,
    "doctor_id": doctor_id,
    "medication": "Melatonin 5mg",
    "dosage": "1 tablet before bedtime",
    "refills": 2,
    "notes": "Take 30 mins before sleep"
}
added_prescription = post("/api/prescription", new_prescription)
pres_id = added_prescription.get("id") or added_prescription.get("_id")
print(f"  -> Prescription issued. ID: {pres_id}")

# 5. Billing test
print("\n[6/6] Generating bill invoice (POST /api/billing)...")
new_bill = {
    "patient_id": patient_id,
    "description": "Consultation with " + doctors[0]['name'],
    "amount": 175.50,
    "status": "Pending"
}
added_bill = post("/api/billing", new_bill)
bill_id = added_bill.get("id") or added_bill.get("_id")
print(f"  -> Invoice generated. ID: {bill_id}, Amount: ${added_bill.get('amount')}")

print("\nVerifying patient invoice list (GET /api/billing?patient_id=)...")
billing_res = get(f"/api/billing?patient_id={patient_id}")
billing_records = billing_res["billing_records"]
print(f"  -> Billed amount for {new_patient['name']}: ${billing_res['total_amount']} ({len(billing_records)} invoice(s))")

print("\nUpdating invoice status to Paid (PUT /api/billing/<id>)...")
updated_bill = put(f"/api/billing/{bill_id}", {"status": "Paid"})
print(f"  -> Updated Invoice Status: {updated_bill.get('status')}")

# 6. Metrics Check
print("\nFetching system operations metrics (GET /api/metrics)...")
metrics = get("/api/metrics")
print("=============================================")
print("  CareHub Platform Statistics Summary        ")
print("=============================================")
print(f"  * System Platform   : {metrics['system']['platform']}")
print(f"  * CPU usage         : {metrics['system']['cpu_usage']}%")
print(f"  * Memory usage      : {metrics['system']['memory_usage']}%")
print(f"  * Uptime            : {metrics['uptime_seconds']} seconds")
print(f"  * DB counts:")
for db_table, count in metrics["db"].items():
    print(f"     - {db_table}: {count} records")
print(f"  * Telemetry aggregated requests: {metrics['requests']['total']}")
print("=============================================")
print("  All verification tests completed successfully!")
print("=============================================")
