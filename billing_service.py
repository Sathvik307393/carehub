import json
import time
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from db_client import get_db_collection

PORT = 5005
billing_col = get_db_collection("billing")
patients_col = get_db_collection("patients")

SEED_BILLING = [
    {"id": "b1", "patient_id": "p1", "date": "2026-05-10", "description": "Cardiology Consultation", "amount": 150.00, "status": "Paid"},
    {"id": "b2", "patient_id": "p2", "date": "2026-05-12", "description": "Diagnostic MRI Scan", "amount": 850.00, "status": "Pending"},
    {"id": "b3", "patient_id": "p3", "date": "2026-05-15", "description": "General Surgery deposit", "amount": 1200.00, "status": "Unpaid"}
]

if billing_col.count_documents() == 0:
    print("Seeding billing records...")
    for b in SEED_BILLING:
        b["_id"] = b["id"]
        billing_col.insert_one(b)

def report_metrics(status_code, elapsed_ms):
    try:
        import os
        metrics_url = os.environ.get("SERVICE_METRICS_URL", "http://127.0.0.1:5006")
        url = f"{metrics_url}/api/metrics/report"
        data = json.dumps({
            "service": "billing",
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

class BillingHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Billing] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

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
            # GET /api/billing or GET /api/billing/<id>
            if self.command == "GET":
                if len(parts) >= 2 and parts[0] == "api" and parts[1] == "billing":
                    bill_id = parts[2] if len(parts) > 2 else None
                    if bill_id:
                        bill = billing_col.find_one({"_id": bill_id})
                        if bill:
                            bill_copy = dict(bill)
                            bill_copy["patient"] = patients_col.find_one({"_id": bill["patient_id"]}) or {}
                            status, result = 200, bill_copy
                        else:
                            status, result = 404, {"error": "Invoice not found"}
                    else:
                        patient_id_filter = query.get("patient_id", [None])[0]
                        status_filter = query.get("status", [None])[0]
                        
                        all_bills = billing_col.find()
                        filtered = []
                        for bill in all_bills:
                            if patient_id_filter and bill.get("patient_id") != patient_id_filter:
                                continue
                            if status_filter and bill.get("status") != status_filter:
                                continue
                            
                            bill_copy = dict(bill)
                            bill_copy["patient"] = patients_col.find_one({"_id": bill["patient_id"]}) or {}
                            filtered.append(bill_copy)
                        
                        total_amount = sum(float(b["amount"]) for b in filtered)
                        status, result = 200, {
                            "billing_records": filtered,
                            "total": len(filtered),
                            "total_amount": round(total_amount, 2)
                        }

            # POST /api/billing
            elif self.command == "POST":
                if len(parts) == 2 and parts[0] == "api" and parts[1] == "billing":
                    body = self._read_json()
                    patient_id = body.get("patient_id")
                    
                    # Verify patient exists
                    if not patients_col.find_one({"_id": patient_id}):
                        status, result = 400, {"error": "Invalid patient_id"}
                    else:
                        bid = "b" + str(billing_col.count_documents() + 1)
                        while billing_col.find_one({"_id": bid}):
                            bid = "b" + str(int(bid[1:]) + 1)
                        
                        bill = {
                            "_id": bid,
                            "id": bid,
                            "patient_id": patient_id,
                            "date": body.get("date", time.strftime("%Y-%m-%d")),
                            "description": body.get("description", "Medical Service"),
                            "amount": float(body.get("amount", 0.0)),
                            "status": body.get("status", "Unpaid")
                        }
                        billing_col.insert_one(bill)
                        status, result = 201, bill

            # PUT /api/billing/<id>
            elif self.command == "PUT":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "billing":
                    bill_id = parts[2]
                    body = self._read_json()
                    existing = billing_col.find_one({"_id": bill_id})
                    if existing:
                        body.pop("_id", None)
                        body.pop("id", None)
                        if "amount" in body:
                            body["amount"] = float(body["amount"])
                        billing_col.update_one({"_id": bill_id}, {"$set": body})
                        status, result = 200, billing_col.find_one({"_id": bill_id})
                    else:
                        status, result = 404, {"error": "Invoice not found"}

            # DELETE /api/billing/<id>
            elif self.command == "DELETE":
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "billing":
                    bill_id = parts[2]
                    existing = billing_col.find_one({"_id": bill_id})
                    if existing:
                        billing_col.delete_one({"_id": bill_id})
                        status, result = 200, {"deleted": existing}
                    else:
                        status, result = 404, {"error": "Invoice not found"}

        except Exception as e:
            status, result = 500, {"error": f"Billing service error: {str(e)}"}

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
        server = ThreadingHTTPServer(("", PORT), BillingHandler)
    except:
        server = HTTPServer(("", PORT), BillingHandler)
        
    print(f"Billing Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Billing Service.")
