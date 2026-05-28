import json
import time
import hashlib
import os
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from db_client import get_db_collection

PORT = 5007
users_col = get_db_collection("users")
sessions_col = get_db_collection("sessions")

def hash_password(password, salt=None):
    if not salt:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return hashed, salt

# Seed an initial admin/doctor/patient if empty
if users_col.count_documents() == 0:
    print("Seeding initial user credentials...")
    # Seed doctor user
    pwd_hash, salt = hash_password("SecurePass123!")
    users_col.insert_one({
        "_id": "d1",
        "username": "doctor",
        "password_hash": pwd_hash,
        "salt": salt,
        "role": "Doctor"
    })
    # Seed patient user
    pwd_hash, salt = hash_password("SecurePass123!")
    users_col.insert_one({
        "_id": "p1",
        "username": "patient",
        "password_hash": pwd_hash,
        "salt": salt,
        "role": "Patient"
    })

def report_metrics(status_code, elapsed_ms):
    try:
        metrics_url = os.environ.get("SERVICE_METRICS_URL", "http://127.0.0.1:5006")
        url = f"{metrics_url}/api/metrics/report"
        data = json.dumps({
            "service": "auth",
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

class AuthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] [Auth] {self.command} {self.path}  →  {args[1] if len(args)>1 else ''}")

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
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
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
            if self.command == "POST":
                # POST /api/auth/register
                if len(parts) == 3 and parts[0] == "api" and parts[1] == "auth" and parts[2] == "register":
                    body = self._read_json()
                    username = body.get("username", "").strip().lower()
                    password = body.get("password", "")
                    role = body.get("role", "Patient").strip()

                    if not username or not password:
                        status, result = 400, {"error": "Username and password required"}
                    elif users_col.find_one({"username": username}):
                        status, result = 400, {"error": "Username already exists"}
                    else:
                        pwd_hash, salt = hash_password(password)
                        user = {
                            "username": username,
                            "password_hash": pwd_hash,
                            "salt": salt,
                            "role": role,
                            "created_at": time.time()
                        }
                        users_col.insert_one(user)
                        status, result = 201, {"username": username, "role": role}

                # POST /api/auth/login
                elif len(parts) == 3 and parts[0] == "api" and parts[1] == "auth" and parts[2] == "login":
                    body = self._read_json()
                    username = body.get("username", "").strip().lower()
                    password = body.get("password", "")

                    user = users_col.find_one({"username": username})
                    if not user:
                        status, result = 401, {"error": "Invalid username or password"}
                    else:
                        test_hash, _ = hash_password(password, user["salt"])
                        if test_hash == user["password_hash"]:
                            # Create new session token
                            token = os.urandom(24).hex()
                            session = {
                                "_id": token,
                                "username": username,
                                "role": user["role"],
                                "created_at": time.time()
                            }
                            sessions_col.insert_one(session)
                            status, result = 200, {
                                "token": token,
                                "username": username,
                                "role": user["role"]
                            }
                        else:
                            status, result = 401, {"error": "Invalid username or password"}

                # POST /api/auth/verify
                elif len(parts) == 3 and parts[0] == "api" and parts[1] == "auth" and parts[2] == "verify":
                    body = self._read_json()
                    token = body.get("token", "")

                    session = sessions_col.find_one({"_id": token})
                    if session:
                        status, result = 200, {
                            "username": session["username"],
                            "role": session["role"]
                        }
                    else:
                        status, result = 401, {"error": "Invalid or expired token"}

        except Exception as e:
            status, result = 500, {"error": f"Auth service error: {str(e)}"}

        self._send_json(status, result)
        elapsed_ms = (time.time() - start_time) * 1000.0
        report_metrics(status, elapsed_ms)

    def do_POST(self):   self._handle()

if __name__ == "__main__":
    try:
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(("", PORT), AuthHandler)
    except:
        server = HTTPServer(("", PORT), AuthHandler)
        
    print(f"Auth Service listening on port {PORT}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Auth Service.")
