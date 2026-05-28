import json
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from db_client import get_db_collection

PORT = 5002
doctors_col = get_db_collection("doctors")

SEED_DOCTORS = [
    {"id": "d1", "name": "Dr. Sarah Connor", "specialty": "Cardiology", "phone": "555-0211", "email": "s.connor@carehub.com", "availability": ["Monday 9am-1pm", "Wednesday 9am-5pm"]},
    {"id": "d2", "name": "Dr. Gregory House", "specialty": "Diagnostic Medicine", "phone": "555-0222", "email": "g.house@carehub.com", "availability": ["Tuesday 10am-4pm", "Thursday 10am-4pm"]},
    {"id": "d3", "name": "Dr. Leonard McCoy", "specialty": "General Surgery", "phone": "555-0233", "email": "l.mccoy@carehub.com", "availability": ["Friday 9am-5pm", "Saturday 9am-1pm"]}
]

if doctors_col.count_documents() == 0:
    print("Seeding doctor records...")
    for d in SEED_DOCTORS:
        d["_id"] = d["id"]
        doctors_col.insert_one(d)

def report_metrics(status_code, elapsed_ms):
    try:
        import os
        metrics_url = os.environ.get("SERVICE_METRICS_URL", "http://127.0.0.1:5006")
        url = f"{metrics_url}/api/metrics/report"
        data = json.dumps({
            "service": "doctor",
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

class DoctorHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Doctor] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

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
            # GET /api/doctor or GET /api/doctor/<id>
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "doctor":
                    doctor_id = parts[2] if len(parts) > 2 else None
                    if doctor_id:
                        doctor = doctors_col.find_one({"_id": doctor_id})
                        if doctor:
                            status, result = 200, doctor
                        else:
                            status, result = 404, {"error": "Doctor not found"}
                    else:
                        doctors = doctors_col.find()
                        status, result = 200, {"doctors": doctors, "total": len(doctors)}

            # POST /api/doctor
            elif self.command == "POST":
                if len(parts) == 2 and parts[0] == "api" and parts[1] == "doctor":
                    body = self._read_json()
                    did = "d" + str(doctors_col.count_documents() + 1)
                    while doctors_col.find_one({"_id": did}):
                        did = "d" + str(int(did[1:]) + 1)
                    
                    doctor = {
                        "_id": did,
                        "id": did,
                        "name": body.get("name", "Unknown"),
                        "specialty": body.get("specialty", "General"),
                        "phone": body.get("phone", ""),
                        "email": body.get("email", ""),
                        "availability": body.get("availability", [])
                    }
                    doctors_col.insert_one(doctor)
                    status, result = 201, doctor

            # PUT /api/doctor/<id>
            elif self.command == "PUT":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "doctor":
                    doctor_id = parts[2]
                    body = self._read_json()
                    existing = doctors_col.find_one({"_id": doctor_id})
                    if existing:
                        body.pop("_id", None)
                        body.pop("id", None)
                        doctors_col.update_one({"_id": doctor_id}, {"$set": body})
                        status, result = 200, doctors_col.find_one({"_id": doctor_id})
                    else:
                        status, result = 404, {"error": "Doctor not found"}

            # DELETE /api/doctor/<id>
            elif self.command == "DELETE":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "doctor":
                    doctor_id = parts[2]
                    existing = doctors_col.find_one({"_id": doctor_id})
                    if existing:
                        doctors_col.delete_one({"_id": doctor_id})
                        status, result = 200, {"deleted": existing}
                    else:
                        status, result = 404, {"error": "Doctor not found"}

        except Exception as e:
            status, result = 500, {"error": f"Doctor service error: {str(e)}"}

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
        server = ThreadingHTTPServer(("", PORT), DoctorHandler)
    except:
        server = HTTPServer(("", PORT), DoctorHandler)
        
    print(f"Doctor Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Doctor Service.")
