# Order-to-Audit-System

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1.4-092E20.svg)](https://www.djangoproject.com/)
[![Tests](https://img.shields.io/badge/Tests-25%20Passed-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](docker-compose.yml)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An enterprise-grade, audit-compliant ERP and manufacturing tracking system tailored for food processing and FMCG manufacturing units (benchmarked for a South Indian snack manufacturing facility). 

The platform tracks the complete lifecycle from **Procurement (P2P)**, **Inventory Valuation (Weighted Average)**, **BOM & Production Yield Variance Auditing**, to **Order-to-Cash (O2C)** with statutory **Indian GST Compliance** and immutable stock ledgers.

---

## 🌟 Key Features

### 1. Dual-Entry Stock Ledger & Valuation
- **Weighted-Average Cost (WAC)** computed per item automatically across batch inward movements.
- **Negative Balance Prevention**: Strict database-level and service-layer validation preventing stock from dropping below zero.
- **Multi-Unit Normalization**: Automated unit conversion between transaction units (e.g., Cartons, Pouches, Grams) and inventory base units (kg, L, packets).

### 2. BOM & Production Run Auditing
- **Bill of Materials (BOM)**: Standard formulation definition per finished product (e.g., Murukku 200g).
- **Yield & Variance Flagging**: Compares theoretical consumption against actual issue. Variations exceeding **> 3%** trigger automated audit flags.
- **Finished Goods Cost Roll-up**: Automatically calculates manufactured unit cost including raw materials, packaging, and operational overheads.

### 3. Order-to-Cash (O2C) with Indian GST
- **Sales Orders & Approvals**: Role-based order booking for field salesmen.
- **Dispatch & Invoicing**: Supports partial fulfillment, automated dispatch creation, and invoice generation.
- **GST Calculation Engine**:
  - **Intrastate (Tamil Nadu to Tamil Nadu)**: CGST (6%) + SGST (6%) with odd-paise allocation to CGST.
  - **Interstate (e.g., TN to Kerala/Karnataka)**: IGST (12%).
  - Zero-rated items and fractional paise handling.
- **PDF Invoice Generation**: Powered by WeasyPrint for printable tax invoices.

### 4. Role-Based Access Control (RBAC)
Dedicated views, dashboards, and action permissions for:
- **Owner**: Full oversight, P&L, KPI dashboard, variance reports.
- **Accountant**: Invoices, credit notes, payments, customer ledgers, tax reports.
- **Production Supervisor**: BOMs, production run logs, scrap and variance entry.
- **Salesman**: Field sales orders and customer balance lookups.
- **Admin**: Master data configuration, items, units, and system settings.

---

## 🏗️ Architecture & Project Structure

```text
order_to_audit/
├── apps/
│   ├── core/           # Custom User model, auth views, audit logs, seed commands
│   ├── inventory/      # Items, StockMovements, unit conversions, stock ledger
│   ├── production/     # BOMs, ProductionRuns, scrap logs, variance audit
│   ├── purchasing/     # Suppliers, purchase orders, GRN inward movements
│   ├── reports/        # Executive dashboard, stock summary, GST registers
│   └── sales/          # Customers, price lists, orders, dispatches, invoices
├── config/             # Django settings (base, dev, prod), WSGI, ASGI, URLs
├── services/           # Decoupled business logic (GST, Stock, Unit Conversion)
│   ├── gst.py          # Indian GST computation engine
│   ├── sales.py        # Outstanding calculations and customer ledgers
│   ├── stock.py        # Weighted average cost and movement engine
│   └── units.py        # Multi-unit conversion and normalization
├── templates/          # Responsive HTMX + Tailwind CSS styled UI templates
├── tests/              # Pytest suite (25 automated integration & unit tests)
├── docker-compose.yml  # Multi-container orchestration (PostgreSQL 16 + Web)
├── Dockerfile          # Production-ready Python 3.11 container image
├── manage.py           # Django management CLI
├── pytest.ini          # Pytest configuration
└── requirements.txt    # Project dependencies
```

---

## 🚀 Getting Started

You can run the application using **Docker Compose** or directly in a **local Python virtual environment**.

### Method 1: Using Docker Compose (Quickest)

1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/Order-to-Audit-System.git
   cd Order-to-Audit-System
   ```
2. Build and launch containers:
   ```bash
   docker compose up --build
   ```
   *This automatically provisions PostgreSQL 16, runs database migrations, seeds benchmark master data, and starts the server on port 8000.*

3. Open your browser: [http://localhost:8000/](http://localhost:8000/)

---

### Method 2: Local Python Environment

#### 1. Prerequisites
- Python 3.11 or higher
- Git

#### 2. Virtual Environment Setup

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 3. Database Migrations & Benchmark Seed
*(Uses local SQLite by default. Set `DATABASE_URL` in `.env` to connect to PostgreSQL).*

```bash
python manage.py migrate
python manage.py seed
```

#### 4. Run Development Server
```bash
python manage.py runserver
```
Access the application at [http://localhost:8000/login/](http://localhost:8000/login/).

---

## 👥 Seeded Benchmark Credentials

Running `python manage.py seed` automatically provisions benchmark accounts:

| Username | Password | Role | Access Scope |
| :--- | :--- | :--- | :--- |
| `admin_user` | `admin123` | `admin` | Full system & master data management |
| `owner` | `pass123` | `owner` | Executive dashboard, reports, audit flags |
| `accountant` | `pass123` | `accountant` | Invoices, payments, financial ledgers |
| `production` | `pass123` | `production` | Production runs, BOMs, material issue |
| `salesman_a` | `pass123` | `salesman` | Sales order entry, customer ledger |
| `salesman_b` | `pass123` | `salesman` | Sales order entry |

---

## 🧪 Test Suite

The test suite validates compliance with business specifications and Section 5 benchmark data:

```bash
pytest
```

**Coverage includes:**
- Intrastate & Interstate GST calculations with odd-paise rounding
- Zero negative stock invariant validation
- Weighted average inventory cost calculations
- Unit normalization across conversions
- Full Section 5 end-to-end benchmark workflow

```text
============================= 25 passed in 4.45s ==============================
```

---

