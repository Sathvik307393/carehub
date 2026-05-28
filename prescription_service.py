import json
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from db_client import get_db_collection

PORT = 5004
prescriptions_col = get_db_collection("prescriptions")
patients_col = get_db_collection("patients")
doctors_col = get_db_collection("doctors")

SEED_PRESCRIPTIONS = [
    {"id": "pr1", "patient_id": "p1", "doctor_id": "d1", "date": "2026-05-15", "medication": "Lisinopril 10mg", "dosage": "Once daily", "refills": 3, "notes": "Monitor blood pressure weekly"},
    {"id": "pr2", "patient_id": "p2", "doctor_id": "d2", "date": "2026-05-18", "medication": "Amitriptyline 25mg", "dosage": "Once daily at bedtime", "refills": 1, "notes": "For preventative migraine control"},
    {"id": "pr3", "patient_id": "p3", "doctor_id": "d3", "date": "2026-05-20", "medication": "Metformin 500mg", "dosage": "Twice daily with meals", "refills": 5, "notes": "Take with breakfast and dinner"}
]

if prescriptions_col.count_documents() == 0:
    print("Seeding prescription records...")
    for pr in SEED_PRESCRIPTIONS:
        pr["_id"] = pr["id"]
        prescriptions_col.insert_one(pr)

def report_metrics(status_code, elapsed_ms):
    try:
        import os
        metrics_url = os.environ.get("SERVICE_METRICS_URL", "http://127.0.0.1:5006")
        url = f"{metrics_url}/api/metrics/report"
        data = json.dumps({
            "service": "prescription",
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

class PrescriptionHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Prescription] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

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
        query = parse_qs(parsed.query)
        parts = [p for p in path.split("/") if p]

        status = 404
        result = {"error": "Not found"}

        try:
            # GET /api/prescription or GET /api/prescription/<id>
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "prescription":
                    pres_id = parts[2] if len(parts) > 2 else None
                    if pres_id:
                        pres = prescriptions_col.find_one({"_id": pres_id})
                        if pres:
                            pres_copy = dict(pres)
                            pres_copy["patient"] = patients_col.find_one({"_id": pres["patient_id"]}) or {}
                            pres_copy["doctor"] = doctors_col.find_one({"_id": pres["doctor_id"]}) or {}
                            status, result = 200, pres_copy
                        else:
                            status, result = 404, {"error": "Prescription not found"}
                    else:
                        patient_id_filter = query.get("patient_id", [None])[0]
                        doctor_id_filter = query.get("doctor_id", [None])[0]
                        
                        all_pres = prescriptions_col.find()
                        filtered = []
                        for pres in all_pres:
                            if patient_id_filter and pres.get("patient_id") != patient_id_filter:
                                continue
                            if doctor_id_filter and pres.get("doctor_id") != doctor_id_filter:
                                continue
                            
                            pres_copy = dict(pres)
                            pres_copy["patient"] = patients_col.find_one({"_id": pres["patient_id"]}) or {}
                            pres_copy["doctor"] = doctors_col.find_one({"_id": pres["doctor_id"]}) or {}
                            filtered.append(pres_copy)
                        status, result = 200, {"prescriptions": filtered, "total": len(filtered)}

            # POST /api/prescription
            elif self.command == "POST":
                if len(parts) == 2 and parts[0] == "api" and parts[1] == "prescription":
                    body = self._read_json()
                    
                    patient_id = body.get("patient_id")
                    doctor_id = body.get("doctor_id")
                    
                    # Verify patient and doctor exist
                    if not patients_col.find_one({"_id": patient_id}):
                        status, result = 400, {"error": "Invalid patient_id"}
                    elif not doctors_col.find_one({"_id": doctor_id}):
                        status, result = 400, {"error": "Invalid doctor_id"}
                    else:
                        prid = "pr" + str(prescriptions_col.count_documents() + 1)
                        while prescriptions_col.find_one({"_id": prid}):
                            prid = "pr" + str(int(prid[2:]) + 1)
                        
                        pres = {
                            "_id": prid,
                            "id": prid,
                            "patient_id": patient_id,
                            "doctor_id": doctor_id,
                            "date": body.get("date", time.strftime("%Y-%m-%d")),
                            "medication": body.get("medication", ""),
                            "dosage": body.get("dosage", ""),
                            "refills": body.get("refills", 0),
                            "notes": body.get("notes", "")
                        }
                        prescriptions_col.insert_one(pres)
                        status, result = 201, pres

            # PUT /api/prescription/<id>
            elif self.command == "PUT":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "prescription":
                    pres_id = parts[2]
                    body = self._read_json()
                    existing = prescriptions_col.find_one({"_id": pres_id})
                    if existing:
                        body.pop("_id", None)
                        body.pop("id", None)
                        prescriptions_col.update_one({"_id": pres_id}, {"$set": body})
                        status, result = 200, prescriptions_col.find_one({"_id": pres_id})
                    else:
                        status, result = 404, {"error": "Prescription not found"}

            # DELETE /api/prescription/<id>
            elif self.command == "DELETE":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "prescription":
                    pres_id = parts[2]
                    existing = prescriptions_col.find_one({"_id": pres_id})
                    if existing:
                        prescriptions_col.delete_one({"_id": pres_id})
                        status, result = 200, {"deleted": existing}
                    else:
                        status, result = 404, {"error": "Prescription not found"}

        except Exception as e:
            status, result = 500, {"error": f"Prescription service error: {str(e)}"}

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
        server = ThreadingHTTPServer(("", PORT), PrescriptionHandler)
    except:
        server = HTTPServer(("", PORT), PrescriptionHandler)
        
    print(f"Prescription Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Prescription Service.")
