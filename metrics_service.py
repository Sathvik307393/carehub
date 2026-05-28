import json
import time
import platform
import psutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from db_client import get_db_collection

PORT = 5006
START_TIME = time.time()

# Tables to count for dashboard summary
patients_col = get_db_collection("patients")
doctors_col = get_db_collection("doctors")
appointments_col = get_db_collection("appointments")
prescriptions_col = get_db_collection("prescriptions")
billing_col = get_db_collection("billing")

# Request statistics in-memory for live reporting
stats = {
    "total": 0,
    "by_status": {},
    "by_service": {}
}

class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Prevent spamming the console with metrics reporting logs
        pass

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
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        parts = [p for p in path.split("/") if p]

        status = 404
        result = {"error": "Not found"}

        try:
            # GET /api/metrics - returns aggregate system statistics and database record counts
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "metrics":
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory().percent
                    
                    db_counts = {
                        "patients": patients_col.count_documents(),
                        "doctors": doctors_col.count_documents(),
                        "appointments": appointments_col.count_documents(),
                        "prescriptions": prescriptions_col.count_documents(),
                        "billing": billing_col.count_documents(),
                    }

                    result = {
                        "uptime_seconds": round(time.time() - START_TIME, 1),
                        "system": {
                            "cpu_usage": cpu,
                            "memory_usage": mem,
                            "platform": platform.system()
                        },
                        "db": db_counts,
                        "requests": stats
                    }
                    status = 200

            # POST /api/metrics/report - registers response metrics from services asynchronously
            elif self.command == "POST":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "metrics" and parts[2] == "report":
                    body = self._read_json()
                    service = body.get("service", "unknown")
                    status_code = str(body.get("status_code", 200))
                    
                    # Update stats
                    stats["total"] += 1
                    stats["by_status"][status_code] = stats["by_status"].get(status_code, 0) + 1
                    stats["by_service"][service] = stats["by_service"].get(service, 0) + 1
                    
                    status = 200
                    result = {"status": "ok"}
        except Exception as e:
            status, result = 500, {"error": f"Internal metrics error: {str(e)}"}

        self._send_json(status, result)

    def do_GET(self):    self._handle()
    def do_POST(self):   self._handle()

if __name__ == "__main__":
    try:
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(("", PORT), MetricsHandler)
    except:
        server = HTTPServer(("", PORT), MetricsHandler)
        
    print(f"Metrics Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Metrics Service.")
