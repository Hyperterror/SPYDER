# SPYDER-DETECT

**Criminal Intelligence Analysis Platform — Phase 1**

A secure, evidence-driven investigation platform for law enforcement. Upload CDR and financial transaction data, parse it into a knowledge graph, and visually explore entity connections across cases.

---

## Tech Stack

### Backend
| Component | Technology |
|---|---|
| API Framework | Python FastAPI 0.128 |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 15 (prod) / SQLite (local dev) |
| Graph Database | Neo4j 5 Community |
| Object Storage | MinIO |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Parsing | pandas, phonenumbers, python-dateutil |
| Hashing | hashlib SHA-256 |

### Frontend
| Component | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v3 |
| Graph Visualisation | Cytoscape.js + fcose layout |
| HTTP Client | axios |
| Animation | HTML5 Canvas (spider matrix) |

### Infrastructure
| Component | Technology |
|---|---|
| Containerisation | Docker + Docker Compose |
| Services | postgres, neo4j, minio, backend, frontend |

---

## Features Implemented

### Authentication
- JWT login / logout / token refresh
- Role-based access: ADMIN, SUPERVISOR, INVESTIGATOR, ANALYST
- Protected routes — all pages redirect to `/login` if unauthenticated

### Case Management
- Create, list, and view investigation cases
- Case types: HUMAN_TRAFFICKING, CYBER_CRIME, FINANCIAL_CRIME, ORGANIZED_CRIME
- Status tracking: ACTIVE, ON_HOLD, CLOSED, DRAFT
- Member assignment per case

### Evidence Ingestion
- Drag-and-drop or browse file upload (CSV, XLSX, JSON)
- SHA-256 hash computed before upload — duplicate detection
- MinIO object storage (falls back to local filesystem in dev mode)
- Integrity re-verification on demand
- Full audit trail per evidence file (chain-hashed)

### Evidence Parsing
- CDR (Call Detail Record) parser — phone normalisation (E.164), UTC timestamp conversion, IMEI / tower extraction
- UPI / Financial Transaction parser — account normalisation, amount parsing, currency handling
- Background parse jobs — row-level error handling, partial completion support

### Knowledge Graph
- Graph built directly from parsed records (no Neo4j required for local dev)
- Node types: Phone (green), Account (amber), Device (cyan), Tower (grey), Document (purple)
- Edge types: CALLED, TRANSFERRED_TO, USED_DEVICE, CONNECTED_TO_TOWER
- Cytoscape.js canvas with fcose force-directed layout
- Click node → inspector panel (identifier, first/last seen, IMEI, tower ID)
- Click edge → provenance panel (source file, row number, SHA-256, integrity status)
- Left rail filters: entity search, radial hops (1–3), relationship type toggles
- Graph never reloads on inspector open — canvas is stable

### Mission Control
- Full-screen animated spider-matrix canvas (grid nodes + mouse-tracking nexus)
- Radar pulse rings, organic breathing nodes, smooth mouse lerp
- Matches the Stitch design exactly

### Dashboard
- 4 KPI cards: Active Cases, Pending Reviews, Contradictions, Cross-Case Links
- Active Investigations table with status badges
- Priority Action Queue (colour-coded left borders)
- Recent Evidence Ingestion table
- Case detail modal on row click

### Audit Trail
- Every action (upload, parse, login, logout, verify) creates an audit event
- Events are chain-hashed — each event embeds the hash of the previous one
- Audit log visible per evidence item in the Evidence Locker

---

## Running Locally (No Docker Required)

This is the recommended approach for local development and presentations.

### Prerequisites

- Python 3.11+ (`python --version`)
- Node.js 18+ (`node --version`)

### Step 1 — Install backend dependencies

```powershell
cd d:\College\Programming\SPYDER\backend
pip install -r requirements.txt
```

### Step 2 — Start the backend

Open a terminal and run:

```powershell
cd d:\College\Programming\SPYDER\backend

$env:DATABASE_URL    = "sqlite:///./spyder_local.db"
$env:JWT_SECRET_KEY  = "local_dev_secret_key_change_in_production_32c"
$env:CORS_ORIGINS    = "http://localhost:3000"
$env:NEO4J_URI       = "bolt://localhost:7687"
$env:NEO4J_USER      = "neo4j"
$env:NEO4J_PASSWORD  = "spyder_neo4j"
$env:MINIO_ENDPOINT  = "localhost:9000"
$env:MINIO_ACCESS_KEY = "spyder_minio"
$env:MINIO_SECRET_KEY = "spyder_minio_secret"

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

You will see:

```
[OK] PostgreSQL tables verified
[WARN] Neo4j not reachable at startup: ...   ← expected, ignore
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

Neo4j and MinIO warnings are expected — the app runs fully on SQLite + local filesystem storage.

### Step 3 — Seed the database (run once)

Open a second terminal:

```powershell
cd d:\College\Programming\SPYDER\backend

$env:DATABASE_URL    = "sqlite:///./spyder_local.db"
$env:JWT_SECRET_KEY  = "local_dev_secret_key_change_in_production_32c"
$env:MINIO_ENDPOINT  = "localhost:9000"
$env:MINIO_ACCESS_KEY = "spyder_minio"
$env:MINIO_SECRET_KEY = "spyder_minio_secret"

python -m app.scripts.seed
```

Expected output:

```
=== SPYDER-DETECT Seed Script ===

[1] Seeding users...
  [+] admin@spyder.gov (ADMIN)
  [+] supervisor@spyder.gov (SUPERVISOR)
  [+] investigator@spyder.gov (INVESTIGATOR)

[2] Seeding case...
  [+] case HT-2026-001

[3] Seeding evidence...
  [+] EVD-001 — cdr_operator_a.csv
  [+] EVD-002 — cdr_operator_b.csv
  [+] EVD-003 — upi_transactions.csv

[4] Parsing evidence...
  [+] parsed cdr_operator_a.csv: 30 valid, 0 invalid
  [+] parsed cdr_operator_b.csv: 25 valid, 0 invalid
  [+] parsed upi_transactions.csv: 26 valid, 0 invalid

=== Seed complete ===
```

### Step 4 — Start the frontend

Open a third terminal:

```powershell
cd d:\College\Programming\SPYDER\frontend
npm install        # first time only — takes ~1 minute
npm run dev
```

### Step 5 — Open in browser

| URL | Purpose |
|---|---|
| http://localhost:3000 | Main application |
| http://localhost:8000/docs | FastAPI Swagger UI (all endpoints) |
| http://localhost:8000/health | Backend health check |

---

## Login Credentials

| Email | Password | Role |
|---|---|---|
| `admin@spyder.gov` | `Admin@1234` | ADMIN |
| `supervisor@spyder.gov` | `Supervisor@1234` | SUPERVISOR |
| `investigator@spyder.gov` | `Invest@1234` | INVESTIGATOR |

---

## How to Check Each Feature

### 1. Login
- Go to http://localhost:3000
- Login with `investigator@spyder.gov` / `Invest@1234`
- You are redirected to the Dashboard

### 2. Dashboard
- See 4 KPI cards at top (Active Cases, Pending Reviews, etc.)
- Active Investigations table shows your seeded case `HT-2026-001`
- Click any row to open the Case Detail modal
- Priority Action Queue shows 4 colour-coded items on the right

### 3. Cases
- Click **Cases** in the sidebar
- You will see `HT-2026-001 — Operation Falcon`
- Click **+ New Case** to create a case via the modal form

### 4. Import Evidence
- Click **Import Evidence** in the sidebar or the top header button
- Drop a CSV file onto the drag-and-drop zone (or browse)
- The file appears in the upload queue with a progress bar
- SHA-256 hash is shown once upload completes

### 5. Evidence Locker
- Navigate to **Cases → HT-2026-001 → Evidence** (or go to http://localhost:3000/cases/{id}/evidence)
- Three evidence files are shown: CDR Operator A, CDR Operator B, UPI Transactions
- Click **Verify Integrity** on any file — the status updates to VERIFIED
- Click **Audit Trail** to see the chain-hashed event log for that file

### 6. Knowledge Graph
- Navigate to **Cases → HT-2026-001 → Graph** (or click **Graph →** from Cases page)
- The graph loads with **33 nodes and 128 edges** from the parsed CDR/UPI data
- Node colours: Phone = green, Account = amber, Device = cyan, Tower = grey
- Click any node to open the Node Inspector panel on the right
- Click any edge to open the Edge Inspector (shows source file, row number, SHA-256)
- Use the left rail to filter by relationship type or change radial hops
- Click **Apply Filters** to reload with new parameters
- The graph does **not** refresh when you click nodes — the canvas is stable

### 7. Mission Control
- Click **Mission Control** in the sidebar
- Full-screen spider-matrix animation plays in the background
- Move your mouse — the glowing nexus follows it, drawing spider-web lines to nearby grid nodes
- Stat cards, capability cards, and active case cards are shown on top

### 8. API Documentation
- Go to http://localhost:8000/docs
- All endpoints are listed and can be tested interactively
- Use the **Authorize** button with a JWT token from the `/api/v1/auth/login` endpoint

---

## Running with Docker (Full Stack)

If Docker Desktop is running and you have internet access to pull images:

```powershell
cd d:\College\Programming\SPYDER

# Copy environment file
Copy-Item .env.example .env

# Build and start all 5 services
docker compose up --build

# Once healthy (~60 seconds), seed in a new terminal:
docker exec spyder_backend python -m app.scripts.seed
```

Services started:

| Service | URL | Credentials |
|---|---|---|
| Frontend | http://localhost:3000 | — |
| Backend API | http://localhost:8000/docs | — |
| Neo4j Browser | http://localhost:7474 | neo4j / spyder_neo4j |
| MinIO Console | http://localhost:9001 | spyder_minio / spyder_minio_secret |
| PostgreSQL | localhost:5432 | spyder / spyder_secret |

---

## Project Structure

```
SPYDER/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routers (auth, cases, evidence, graph, audit)
│   │   ├── core/          # Config, database, Neo4j driver, security
│   │   ├── models/        # SQLAlchemy models (user, case, evidence, audit)
│   │   ├── parsers/       # CDR and transaction CSV parsers
│   │   ├── scripts/       # seed.py
│   │   └── services/      # storage, hashing, audit_svc, graph_upsert
│   ├── alembic/           # Database migrations
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/           # Next.js pages (dashboard, login, import, cases, graph, mission-control)
│       ├── components/
│       │   ├── graph/     # CytoscapeCanvas, NodeInspector, EdgeInspector, GraphFilters
│       │   ├── layout/    # AppShell, TopHeader, SideNav
│       │   └── ui/        # KpiCard, StatusBadge, ToastNotification, Modal, SearchDropdown, ActionQueueItem
│       ├── lib/           # api.ts (axios + JWT), auth.ts
│       └── types/         # TypeScript interfaces
├── synthetic_data/        # cdr_operator_a.csv, cdr_operator_b.csv, upi_transactions.csv
├── docker-compose.yml
├── .env.example
└── task.md
```

---

## Synthetic Data

The seed script loads three CSV files from `synthetic_data/`:

| File | Type | Rows | Contents |
|---|---|---|---|
| `cdr_operator_a.csv` | CDR | 30 | Phone calls between 6 numbers across Delhi/Mumbai/UP towers |
| `cdr_operator_b.csv` | CDR | 25 | Additional CDR data from a second telecom operator |
| `upi_transactions.csv` | Financial | 26 | UPI/RTGS transfers between 5 accounts incl. cross-border flows |

After parsing, the graph contains:
- **8 Phone nodes**, **8 Device nodes**, **10 Tower nodes**, **7 Account nodes**
- **55 CALLED edges**, **35 CONNECTED_TO_TOWER edges**, **12 USED_DEVICE edges**, **26 TRANSFERRED_TO edges**
