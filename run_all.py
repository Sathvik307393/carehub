import subprocess
import sys
import threading
import time
import os

SERVICES = [
    ("Metrics", "metrics_service.py"),
    ("Patient", "patient_service.py"),
    ("Doctor", "doctor_service.py"),
    ("Appointment", "appointment_service.py"),
    ("Prescription", "prescription_service.py"),
    ("Billing", "billing_service.py"),
    ("Auth", "auth_service.py"),
    ("Gateway", "gateway.py")
]

processes = []

def stream_logs(name, proc):
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            print(f"[{name}] {line.decode('utf-8', errors='ignore').strip()}")
            sys.stdout.flush()
    except Exception as e:
        print(f"[{name}] Log stream error: {e}")

def shutdown():
    print("\nStopping all CareHub microservices...")
    for name, proc in processes:
        if proc.poll() is None:
            print(f"  Killing {name} (PID: {proc.pid})...")
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception as e:
                print(f"Error stopping {name}: {e}")
    print("All services stopped. CareHub offline.\n")

def main():
    print("====================================================")
    print("      CareHub Telemedicine Platform Launcher        ")
    print("====================================================")
    
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        print("Database Mode: Connected to Remote PostgreSQL via DATABASE_URL")
    else:
        print("Database Mode: Connected to Local PostgreSQL (Port 5432)")
        
    print("\nStarting services...")

    # Start each service in sequence
    for name, script in SERVICES:
        print(f"  -> Starting {name} ({script})...")
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(
                [sys.executable, "-u", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                env=env
            )
            processes.append((name, proc))
            
            t = threading.Thread(target=stream_logs, args=(name, proc), daemon=True)
            t.start()
            
            time.sleep(0.5)
        except Exception as e:
            print(f"Failed to start {name}: {e}")
            shutdown()
            sys.exit(1)

    port = os.environ.get("PORT", "5000")
    print("\nAll microservices initialized successfully.")
    print(f"Central Access Endpoint: http://localhost:{port}")
    print("Press Ctrl+C to terminate all services.\n")

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
            for name, proc in processes:
                poll = proc.poll()
                if poll is not None:
                    print(f"\n[Warning] {name} service terminated with exit code {poll}!")
                    shutdown()
                    sys.exit(1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Initiating graceful shutdown...")
        shutdown()

if __name__ == "__main__":
    main()
