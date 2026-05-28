import json
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from db_client import get_db_collection

PORT = 5003
appointments_col = get_db_collection("appointments")
patients_col = get_db_collection("patients")
doctors_col = get_db_collection("doctors")

SEED_APPOINTMENTS = [
    {"id": "a1", "patient_id": "p1", "doctor_id": "d1", "date": "2026-06-01", "time": "10:00 AM", "reason": "Follow-up Cardiology", "status": "Scheduled"},
    {"id": "a2", "patient_id": "p2", "doctor_id": "d2", "date": "2026-06-02", "time": "02:30 PM", "reason": "Chronic headaches investigation", "status": "Scheduled"},
    {"id": "a3", "patient_id": "p3", "doctor_id": "d3", "date": "2026-06-03", "time": "11:15 AM", "reason": "Pre-surgery consultation", "status": "Scheduled"}
]

if appointments_col.count_documents() == 0:
    print("Seeding appointment records...")
    for a in SEED_APPOINTMENTS:
        a["_id"] = a["id"]
        appointments_col.insert_one(a)

def report_metrics(status_code, elapsed_ms):
    try:
        import os
        metrics_url = os.environ.get("SERVICE_METRICS_URL", "http://127.0.0.1:5006")
        url = f"{metrics_url}/api/metrics/report"
        data = json.dumps({
            "service": "appointment",
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

class AppointmentHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Appointment] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

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
            # GET /api/appointment or GET /api/appointment/<id>
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "appointment":
                    app_id = parts[2] if len(parts) > 2 else None
                    if app_id:
                        app = appointments_col.find_one({"_id": app_id})
                        if app:
                            app_copy = dict(app)
                            app_copy["patient"] = patients_col.find_one({"_id": app["patient_id"]}) or {}
                            app_copy["doctor"] = doctors_col.find_one({"_id": app["doctor_id"]}) or {}
                            status, result = 200, app_copy
                        else:
                            status, result = 404, {"error": "Appointment not found"}
                    else:
                        patient_id_filter = query.get("patient_id", [None])[0]
                        doctor_id_filter = query.get("doctor_id", [None])[0]
                        
                        all_apps = appointments_col.find()
                        filtered = []
                        for app in all_apps:
                            if patient_id_filter and app.get("patient_id") != patient_id_filter:
                                continue
                            if doctor_id_filter and app.get("doctor_id") != doctor_id_filter:
                                continue
                            
                            app_copy = dict(app)
                            app_copy["patient"] = patients_col.find_one({"_id": app["patient_id"]}) or {}
                            app_copy["doctor"] = doctors_col.find_one({"_id": app["doctor_id"]}) or {}
                            filtered.append(app_copy)
                        status, result = 200, {"appointments": filtered, "total": len(filtered)}

            # POST /api/appointment
            elif self.command == "POST":
                if len(parts) == 2 and parts[0] == "api" and parts[1] == "appointment":
                    body = self._read_json()
                    
                    patient_id = body.get("patient_id")
                    doctor_id = body.get("doctor_id")
                    
                    # Verify patient and doctor exist
                    if not patients_col.find_one({"_id": patient_id}):
                        status, result = 400, {"error": "Invalid patient_id"}
                    elif not doctors_col.find_one({"_id": doctor_id}):
                        status, result = 400, {"error": "Invalid doctor_id"}
                    else:
                        aid = "a" + str(appointments_col.count_documents() + 1)
                        while appointments_col.find_one({"_id": aid}):
                            aid = "a" + str(int(aid[1:]) + 1)
                        
                        app = {
                            "_id": aid,
                            "id": aid,
                            "patient_id": patient_id,
                            "doctor_id": doctor_id,
                            "date": body.get("date", ""),
                            "time": body.get("time", ""),
                            "reason": body.get("reason", "Consultation"),
                            "status": body.get("status", "Scheduled")
                        }
                        appointments_col.insert_one(app)
                        status, result = 201, app

            # PUT /api/appointment/<id>
            elif self.command == "PUT":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "appointment":
                    app_id = parts[2]
                    body = self._read_json()
                    existing = appointments_col.find_one({"_id": app_id})
                    if existing:
                        body.pop("_id", None)
                        body.pop("id", None)
                        appointments_col.update_one({"_id": app_id}, {"$set": body})
                        status, result = 200, appointments_col.find_one({"_id": app_id})
                    else:
                        status, result = 404, {"error": "Appointment not found"}

            # DELETE /api/appointment/<id>
            elif self.command == "DELETE":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "appointment":
                    app_id = parts[2]
                    existing = appointments_col.find_one({"_id": app_id})
                    if existing:
                        appointments_col.delete_one({"_id": app_id})
                        status, result = 200, {"deleted": existing}
                    else:
                        status, result = 404, {"error": "Appointment not found"}

        except Exception as e:
            status, result = 500, {"error": f"Appointment service error: {str(e)}"}

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
        server = ThreadingHTTPServer(("", PORT), AppointmentHandler)
    except:
        server = HTTPServer(("", PORT), AppointmentHandler)
        
    print(f"Appointment Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Appointment Service.")
