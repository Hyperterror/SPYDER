# Changelog

## v2.0.0 — Production Readiness & Product Evolution

### Milestone 1 — Security, Access Control & Forensic Integrity
- Session-bound JWTs (`jti`, `sid`, `fid`), `UserSession` persistence, refresh rotation, family revocation on reuse, real `/logout`, `HttpOnly` refresh cookies + CSRF double-submit protection.
- Centralized case/organization authorization (`app/core/authz.py`) with strict full-case clearance (`all_cases_authorized`) closing cross-case lead & evidence-audit IDOR vectors.
- Fail-fast production config validation (`validate_security_configuration`), streaming bounded upload validation, immutable evidence versioning (`supersede`, `withdraw`, `download`), and concurrency-safe audit chain verification (`GET .../audit/verify`).

### Milestone 2 — Unified Evidence Processing & Durable Workers
- Celery + Redis worker (`app/worker/`) with bounded retries, job cancellation/retry endpoints, and eager fallback for dev/tests.
- Canonical orchestrator (`evidence_orchestrator.py`) supporting CSV, XLSX, JSON, PDF/PNG/JPG/TXT, idempotent `ParsedRecord` replacement, and atomic `GraphSnapshot` publication (`graph_publisher.py`) without mutating synthetic datasets.

### Milestone 3 — Intelligence Integration & Human Review
- Cross-case live Entity Resolution service (`er_live_service.py`) without self-comparison or auto-merge.
- Persistent review workflows and decision logs for leads, identity hypotheses, and statement-evidence claim corrections; centralized entity profile, case timeline, and model registry endpoints.

### Milestone 4 — ML & GraphSAGE Anti-Leakage Validation
- Added Edge-Disjoint and Temporal holdout splits with masked-graph adjacency, dynamically recomputed centralities, `audit_target_edge_leakage`, ranking (`Precision@10`, `Recall@20`, `MRR`), calibration (`Brier`, `ECE`), and calibrated `CosineDecoder` / `DotProductDecoder` bias parameters.
- Removed `GROUND_TRUTH_DIR` from production `entity_resolution/candidate_generation.py`; added 5-seed validation, bootstrap CIs, and 1,200-pair noisy stress validation.

### Milestone 5 — Investigator Workbench (Frontend)
- Removed dashboard/header/search mock fallbacks; added ESLint config and dark-themed pages for Lead Queue/Detail, Entity Resolution Workbench, Entity Profiles, Cross-Case Bridges, Statement Lab, Unified Timeline, and Decision History.

### Milestone 6 — Production Infrastructure, Observability & Docs
- Added redacted JSON logging (`X-Request-ID`), `/health/live`, `/health/ready`, non-root backend Dockerfile, `docker-compose.prod.yml`, GitHub Actions CI, backup/restore/benchmark scripts, and comprehensive `docs/`.
