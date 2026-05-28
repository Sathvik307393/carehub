import json
import time
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import os

PORT = int(os.environ.get("PORT", 5000))

SERVICES = {
    "patient": "http://127.0.0.1:5001",
    "doctor": "http://127.0.0.1:5002",
    "appointment": "http://127.0.0.1:5003",
    "prescription": "http://127.0.0.1:5004",
    "billing": "http://127.0.0.1:5005",
    "metrics": "http://127.0.0.1:5006",
    "auth": "http://127.0.0.1:5007",
}

def report_frontend_metrics(elapsed_ms):
    try:
        url = "http://127.0.0.1:5006/api/metrics/report"
        data = json.dumps({
            "service": "frontend",
            "status_code": 200,
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

class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Gateway] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

    def _proxy(self, target_url):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        headers = {}
        for header, val in self.headers.items():
            if header.lower() not in ("host", "content-length"):
                headers[header] = val

        if "Origin" not in headers:
            headers["Origin"] = "*"

        req = urllib.request.Request(
            target_url,
            data=body,
            headers=headers,
            method=self.command
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as res:
                response_body = res.read()
                self.send_response(res.status)
                for header, val in res.headers.items():
                    if header.lower() not in ("content-length", "transfer-encoding"):
                        self.send_header(header, val)
                self.send_header("Content-Length", str(len(response_body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as e:
            response_body = e.read()
            self.send_response(e.code)
            for header, val in e.headers.items():
                if header.lower() not in ("content-length", "transfer-encoding"):
                    self.send_header(header, val)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as e:
            err_msg = json.dumps({"error": f"Gateway proxy error: {str(e)}"}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_msg)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(err_msg)

    def _handle(self):
        start_time = time.time()
        parsed = urlparse(self.path)
        path = parsed.path
        parts = [p for p in path.split("/") if p]

        # Serve Frontend UI
        if path == "/" or path == "" or path == "/index.html":
            try:
                with open("index.html", "r", encoding="utf-8") as f:
                    html = f.read().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                elapsed_ms = (time.time() - start_time) * 1000.0
                report_frontend_metrics(elapsed_ms)
            except Exception as e:
                err = f"Error loading index.html: {str(e)}".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
            return

        # Route API to backend services
        if len(parts) >= 2 and parts[0] == "api":
            svc_name = parts[1]
            base_url = SERVICES.get(svc_name)
            if base_url:
                query_suffix = f"?{parsed.query}" if parsed.query else ""
                target_url = f"{base_url}{path}{query_suffix}"
                self._proxy(target_url)
                return
            else:
                err = json.dumps({"error": f"Unknown microservice: /api/{svc_name}"}).encode()
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(err)
                return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "22")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"error": "Not found"}')

    def do_GET(self):    self._handle()
    def do_POST(self):   self._handle()
    def do_PUT(self):    self._handle()
    def do_DELETE(self): self._handle()
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

if __name__ == "__main__":
    try:
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(("", PORT), GatewayHandler)
    except:
        server = HTTPServer(("", PORT), GatewayHandler)
        
    print(f"Gateway Server listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Gateway Server.")
