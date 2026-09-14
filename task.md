# SPYDER-DETECT Phase 1 — Task List

## Infrastructure
- [x] docker-compose.yml (postgres, neo4j, minio, backend, frontend)
- [x] .env.example
- [x] backend/Dockerfile
- [x] frontend/Dockerfile

## Backend — Foundation
- [x] backend/requirements.txt
- [x] backend/app/main.py (FastAPI app, CORS, routers)
- [x] backend/app/core/config.py (Pydantic Settings)
- [x] backend/app/core/database.py (SQLAlchemy engine + session)
- [x] backend/app/core/neo4j.py (Neo4j driver)
- [x] backend/app/core/security.py (JWT + bcrypt)
- [x] backend/alembic/ (migrations setup)

## Backend — Models
- [x] backend/app/models/user.py
- [x] backend/app/models/case.py (cases + case_members)
- [x] backend/app/models/evidence.py (evidence_items + parsing_jobs + parsed_records)
- [x] backend/app/models/audit.py (audit_events + case_notes)

## Backend — APIs
- [x] backend/app/api/auth.py (login, refresh, logout, me)
- [x] backend/app/api/cases.py (CRUD + members + summary)
- [x] backend/app/api/evidence.py (upload, verify, parse, records)
- [x] backend/app/api/graph.py (subgraph, search, node, edge, path)
- [x] backend/app/api/audit.py (audit log + notes)

## Backend — Services
- [x] backend/app/services/storage.py (MinIO)
- [x] backend/app/services/hashing.py (SHA-256)
- [x] backend/app/services/audit_svc.py (chain-hashed audit events)
- [x] backend/app/services/graph_upsert.py (Neo4j nodes/edges)
- [x] backend/app/parsers/cdr.py
- [x] backend/app/parsers/transaction.py

## Backend — Synthetic Data
- [x] synthetic_data/cdr_operator_a.csv
- [x] synthetic_data/cdr_operator_b.csv
- [x] synthetic_data/upi_transactions.csv
- [x] backend/app/scripts/seed.py (seed DB + Neo4j with synthetic data)

## Frontend — Foundation
- [x] Scaffold Next.js 14 app in frontend/
- [x] frontend/src/app/globals.css (Tailwind + all Stitch custom CSS)
- [x] frontend/src/lib/api.ts (axios + JWT interceptor)
- [x] frontend/tailwind.config.ts (brand color tokens from Stitch)

## Frontend — Layout
- [x] frontend/src/components/layout/AppShell.tsx
- [x] frontend/src/components/layout/TopHeader.tsx
- [x] frontend/src/components/layout/SideNav.tsx

## Frontend — Shared UI
- [x] frontend/src/components/ui/KpiCard.tsx
- [x] frontend/src/components/ui/StatusBadge.tsx
- [x] frontend/src/components/ui/ToastNotification.tsx
- [x] frontend/src/components/ui/SearchDropdown.tsx
- [x] frontend/src/components/ui/ActionQueueItem.tsx
- [x] frontend/src/components/ui/Modal.tsx
- [x] frontend/src/components/SpiderCanvas.tsx

## Frontend — Pages
- [x] frontend/src/app/page.tsx (Dashboard)
- [x] frontend/src/app/login/page.tsx
- [x] frontend/src/app/import/page.tsx (Import Evidence)
- [x] frontend/src/app/cases/page.tsx (Cases list)
- [x] frontend/src/app/cases/[caseId]/evidence/page.tsx (Evidence Locker)
- [x] frontend/src/app/cases/[caseId]/graph/page.tsx (Knowledge Graph)
- [x] frontend/src/app/mission-control/page.tsx

## Frontend — Graph Components
- [x] frontend/src/components/graph/CytoscapeCanvas.tsx
- [x] frontend/src/components/graph/NodeInspector.tsx
- [x] frontend/src/components/graph/EdgeInspector.tsx
- [x] frontend/src/components/graph/GraphFilters.tsx

## Frontend — Additional Files Created
- [x] frontend/src/app/layout.tsx (root layout + ToastProvider)
- [x] frontend/src/lib/auth.ts (login/logout/session helpers)
- [x] frontend/src/types/index.ts (TypeScript interfaces)
- [x] frontend/.env.local (NEXT_PUBLIC_API_URL)

## Graphify Updates
- [x] Run graphify after infrastructure scaffold
- [x] Run graphify after backend complete
- [x] Run graphify after frontend complete (453 nodes, 936 edges, 36 communities)
