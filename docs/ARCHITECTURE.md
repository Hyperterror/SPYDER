# SPYDER-DETECT — System Architecture

## 1. Platform Overview
SPYDER-DETECT is an evidence-centric criminal intelligence and investigation platform designed to ingest multi-modal evidence, preserve original evidentiary chain-of-custody, construct an auditable knowledge graph, and surface explainable investigative leads and provisional cross-case entity resolution hypotheses under strict human-in-the-loop review and case isolation.

## 2. Source-of-Truth Data Ownership

| Layer | Technology | Authoritative Ownership | Notes |
| :--- | :--- | :--- | :--- |
| **Application & Investigation Records** | PostgreSQL (`SQLAlchemy 2.0` + `Alembic`) | Users, Organizations, Sessions, Cases, CaseMembers, Evidence metadata, Processing Jobs, ParsedRecords, IdentityHypotheses, Leads & Review Logs, Consistency Results, Audit Events, GraphSnapshots, ModelArtifactRegistry | Authoritative transactional state |
| **Original Evidence & Snapshots** | MinIO (with LocalDisk fallback in dev) | Original uploaded files (CSV, XLSX, JSON, PDF, PNG/JPG/JPEG, TXT) keyed immutably per version | Never overwritten on reprocess/supersede/withdraw |
| **Derived Knowledge Graph** | Neo4j (`5-community`) + Versioned Snapshots (`output/graphsage/snapshots/`) | Derived entity nodes, evidence-derived relationships, provisional entity-resolution links | Non-authoritative projection reconstructible from PostgreSQL + active evidence |
| **Async Workers** | Celery + Redis (`backend/app/worker/`) | Durable evidence processing tasks (`process_evidence_job_task`) with bounded retries & cancellation | `CELERY_TASK_ALWAYS_EAGER=true` fallback for dev/CI |
| **Frontend Workbench** | Next.js 14 + TypeScript + Tailwind + Cytoscape.js | Investigator workbench across 16 App Router routes | Access token in memory/`sessionStorage`; refresh cookie `HttpOnly` + CSRF |

## 3. Core Service Boundaries
- **FastAPI Backend (`backend/app/`)**: Centralized RBAC/case isolation (`app/core/authz.py`), session/CSRF JWT auth (`app/core/security.py`), tamper-evident audit hash chain (`app/services/audit_svc.py`), canonical ingestion (`app/services/evidence_orchestrator.py`), versioned graph publisher (`app/services/graph_publisher.py`), live ER bridge (`app/services/er_live_service.py`), structured JSON logging with redaction (`app/core/logging.py`), and health probes (`/health`, `/health/live`, `/health/ready`).
- **ML & Graph Modules (`entity_resolution/`, `graph_analysis/`, `phase4/`)**: Keep zero hidden ground-truth references in production inference paths; `ground_truth/` is isolated strictly to offline evaluation modules.
