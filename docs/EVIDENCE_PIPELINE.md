# Unified Evidence Processing Pipeline

## 1. Supported Modalities & Formats
- **Formats**: `.csv`, `.xlsx` (`openpyxl`), `.json`, `.pdf` / `.png` / `.jpg` / `.jpeg` / `.txt` (`app/services/ocr.py` text & OCR extraction).
- **Modalities**: `CDR`, `TRANSACTION`, `TRAVEL`, `VEHICLE`, `DEVICE`, `CHAT`, `PERSONS`.

## 2. Canonical Pipeline Stages (`backend/app/services/evidence_orchestrator.py`)
Both `POST /api/v1/cases/{case_id}/evidence/{evidence_id}/process` and legacy `POST .../parse` (returns `Deprecation: true` header) execute the canonical orchestrator (`PIPELINE_VERSION = 2.0.0`):

1. **Cancellation Guard & Claim**: Transitions job to `PROCESSING`, updates `stage`.
2. **Retrieval & Hash Check**: Reads immutable original bytes from MinIO/LocalStorage and re-verifies SHA-256 before parsing.
3. **Security & Schema Classification**: Validates extensions, magic signatures, and maps modality columns (`app/services/evidence_validator.py`).
4. **Parsing & Normalization**: Produces normalized records and row-level parse errors (`app/parsers/unified.py`).
5. **Idempotent DB Persistence**: Replaces prior `ParsedRecord` rows for `evidence_id` cleanly in a transaction so re-runs never duplicate rows.
6. **Live Cross-Case Entity Resolution**: For `PERSONS` uploads, invokes `evaluate_live_entity_resolution()` against ACTIVE cross-case profiles (`app/services/er_live_service.py`).
7. **Atomic Graph Publication**: `publish_graph_snapshot()` builds a candidate snapshot in `output/graphsage/snapshots/<version_tag>/`, validates structure, atomically swaps pointers, marks `GraphSnapshot` `ACTIVE`, and performs best-effort Neo4j sync (`app/services/graph_publisher.py`). Failed validation preserves the last active snapshot.
8. **Intelligence Reload & Audit**: Refreshes repository caches and records `EVIDENCE_PIPELINE_COMPLETED`.

## 3. Lifecycle Operations
- **Supersede**: `POST .../supersede` uploads `v{N+1}` while marking `v{N}` `SUPERSEDED` without deleting bytes or audit history.
- **Withdraw**: `POST .../withdraw` sets `WITHDRAWN` with mandatory rationale; subsequent graph rebuilds exclude withdrawn records while retaining raw objects and custody logs.
- **Durable Queue Controls**: `POST .../cancel` and `POST .../retry` manage `EvidenceProcessingJob` state backed by Celery (`app/worker/tasks.py`).
