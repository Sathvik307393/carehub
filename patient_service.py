import json
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from db_client import get_db_collection

PORT = 5001
patients_col = get_db_collection("patients")

SEED_PATIENTS = [
    {"id": "p1", "name": "John Doe", "dob": "1985-05-12", "gender": "Male", "phone": "555-0199", "email": "john.doe@example.com", "blood_group": "O+", "medical_history": ["Hypertension", "Seasonal Allergies"]},
    {"id": "p2", "name": "Jane Smith", "dob": "1990-08-23", "gender": "Female", "phone": "555-0144", "email": "jane.smith@example.com", "blood_group": "A-", "medical_history": ["Asthma"]},
    {"id": "p3", "name": "Robert Johnson", "dob": "1972-11-03", "gender": "Male", "phone": "555-0177", "email": "robert.j@example.com", "blood_group": "B+", "medical_history": ["Type 2 Diabetes", "High Cholesterol"]}
]

if patients_col.count_documents() == 0:
    print("Seeding patient records...")
    for p in SEED_PATIENTS:
        p["_id"] = p["id"]
        patients_col.insert_one(p)

def report_metrics(status_code, elapsed_ms):
    try:
        url = "http://127.0.0.1:5006/api/metrics/report"
        data = json.dumps({
            "service": "patient",
            "status_code": status_code,
            "elapsed_ms": elapsed_ms
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        def run():
            try:
                with urllib.request.urlopen(req, timeout=1.0) as r:
                    r.read()
            except:
                pass
        threading.Thread(target=run, daemon=True).start()
    except:
        pass

class PatientHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Patient] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try: return json.loads(self.rfile.read(length).decode("utf-8"))
            except: return {}
        return {}

    def _send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle(self):
        start_time = time.time()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = [p for p in path.split("/") if p]

        status = 404
        result = {"error": "Not found"}

        try:
            # GET /api/patient or GET /api/patient/<id>
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "patient":
                    patient_id = parts[2] if len(parts) > 2 else None
                    if patient_id:
                        patient = patients_col.find_one({"_id": patient_id})
                        if patient:
                            status, result = 200, patient
                        else:
                            status, result = 404, {"error": "Patient not found"}
                    else:
                        patients = patients_col.find()
                        status, result = 200, {"patients": patients, "total": len(patients)}

            # POST /api/patient
            elif self.command == "POST":
                if len(parts) == 2 and parts[0] == "api" and parts[1] == "patient":
                    body = self._read_json()
                    pid = "p" + str(patients_col.count_documents() + 1)
                    while patients_col.find_one({"_id": pid}):
                        pid = "p" + str(int(pid[1:]) + 1)
                    
                    patient = {
                        "_id": pid,
                        "id": pid,
                        "name": body.get("name", "Unknown"),
                        "dob": body.get("dob", ""),
                        "gender": body.get("gender", ""),
                        "phone": body.get("phone", ""),
                        "email": body.get("email", ""),
                        "blood_group": body.get("blood_group", ""),
                        "medical_history": body.get("medical_history", [])
                    }
                    patients_col.insert_one(patient)
                    status, result = 201, patient

            # PUT /api/patient/<id>
            elif self.command == "PUT":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "patient":
                    patient_id = parts[2]
                    body = self._read_json()
                    existing = patients_col.find_one({"_id": patient_id})
                    if existing:
                        body.pop("_id", None)
                        body.pop("id", None)
                        patients_col.update_one({"_id": patient_id}, {"$set": body})
                        status, result = 200, patients_col.find_one({"_id": patient_id})
                    else:
                        status, result = 404, {"error": "Patient not found"}

            # DELETE /api/patient/<id>
            elif self.command == "DELETE":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "patient":
                    patient_id = parts[2]
                    existing = patients_col.find_one({"_id": patient_id})
                    if existing:
                        patients_col.delete_one({"_id": patient_id})
                        status, result = 200, {"deleted": existing}
                    else:
                        status, result = 404, {"error": "Patient not found"}

        except Exception as e:
            status, result = 500, {"error": f"Patient service error: {str(e)}"}

        self._send_json(status, result)
        elapsed_ms = (time.time() - start_time) * 1000.0
        report_metrics(status, elapsed_ms)

    def do_GET(self):    self._handle()
    def do_POST(self):   self._handle()
    def do_PUT(self):    self._handle()
    def do_DELETE(self): self._handle()

if __name__ == "__main__":
    try:
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(("", PORT), PatientHandler)
    except:
        server = HTTPServer(("", PORT), PatientHandler)
        
    print(f"Patient Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Patient Service.")
