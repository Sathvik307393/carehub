# AutoHub & CareHub Microservices Platform

This repository contains two complete microservices-based platforms configured to use **PostgreSQL** and fully optimized for seamless deployment on **Azure App Services**.

## 1. CareHub — Telemedicine Platform
A clinical digital health platform.
- **Directory**: `carehub/`
- **Services**:
  - `gateway.py` (Central Gateway / Dashboard - dynamically routes traffic via `PORT`)
  - `patient_service.py` (Patient Records CRUD - Port 5001)
  - `doctor_service.py` (Clinician Directory - Port 5002)
  - `appointment_service.py` (Appointment Scheduling - Port 5003)
  - `prescription_service.py` (Medication Prescriptions - Port 5004)
  - `billing_service.py` (Billing & Invoices - Port 5005)
  - `metrics_service.py` (Performance Telemetry - Port 5006)
- **Local Launch**:
  ```bash
  cd carehub
  python run_all.py
  ```

---

## 2. AutoHub — Automobile Management Platform
An automobile fleet and inventory dashboard.
- **Services**:
  - `gateway_server.py` (Central Gateway / Dashboard - Port dynamic)
  - `inventory_service.py` (Car Inventory CRUD - Port 5002)
  - `maintenance_service.py` (Maintenance Tracker - Port 5004)
  - `valuation_service.py` (Car Valuation calculations - Port 5006)
  - `fuel_service.py` (Fuel logging - Port 5007)
  - `insurance_service.py` (Insurance manager - Port 5008)
  - `metrics_service.py` (System statistics - Port 5009)
- **Local Launch**:
  ```bash
  python run_all.py
  ```

---

## Azure App Service Configuration
Both projects include:
- `requirements.txt`: Specifying deployment dependencies (`psycopg2-binary`, `psutil`).
- `startup.sh`: Entry point execution script for Azure.
- Dynamic `PORT` binding on their respective API Gateway servers.
- `DATABASE_URL` dynamic PostgreSQL connection parsing.
