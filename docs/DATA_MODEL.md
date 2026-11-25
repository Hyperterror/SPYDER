# Data Model & Migrations

## 1. Core Relational Schema (PostgreSQL / SQLAlchemy 2.0)
Managed via Alembic migrations under `backend/alembic/versions/`:
- `0001_initial_schema.py`
- `0002_add_extracted_text_to_evidence.py`
- `0003_security_sessions_orgs_evidence_versions.py`
- `0004_pipeline_jobs_parsed_meta_graph_snapshots.py`
- `0005_intelligence_hypotheses_leads_consistency.py`

- **`organizations` (`app/models/organization.py`)**: Organizational tenancy boundaries (`code`, `name`, `is_active`).
- **`users` & `user_sessions` (`app/models/user.py`, `auth.py`)**: Investigator accounts, `organization_id`, active session families (`family_id`, `refresh_token_hash`, `revoked_at`).
- **`cases` & `case_members` (`app/models/case.py`)**: Dockets (`case_code`, `external_case_ref`, `organization_id`, `case_type`, `status`) and explicit member roles (`CASE_OWNER`, `INVESTIGATOR`, `LEAD_INVESTIGATOR`, `ANALYST`).
- **`evidence_items`, `evidence_processing_jobs`, `parsed_records` (`app/models/evidence.py`)**:
  - `evidence_items`: immutable SHA-256 original record metadata, `version_number`, `supersedes_evidence_id`, `lifecycle_status` (`ACTIVE` | `SUPERSEDED` | `WITHDRAWN`), `withdrawn_reason/by/at`, `extracted_text`.
  - `evidence_processing_jobs`: `status`, `stage`, `retry_count`, `max_retries`, `celery_task_id`, `idempotency_key`, `cancelled_by/at`.
  - `parsed_records`: normalized rows stamped with `evidence_version`, `extraction_method`, `parser_version`, `extracted_at`, `extraction_confidence`.
- **`graph_snapshots` (`app/models/graph.py`)**: Immutable staged/active graph build records (`version_tag`, `status`, `node_count`, `edge_count`, `manifest`).
- **`identity_hypotheses` & `identity_hypothesis_decision_logs` (`app/models/intelligence.py`)**: Cross-case ER matches (`hypothesis_key`, `match_probability`, `supporting_evidence`, `conflicting_evidence`, `profile_a_snapshot`, `profile_b_snapshot`, `status`).
- **`intelligence_lead_records` & `lead_decision_logs` (`app/models/intelligence.py`)**: Persisted candidate association leads & review history.
- **`consistency_analysis_records` & `model_artifact_registry`**: Persistent statement consistency claims (`original_claim` + `current_claim`) and versioned model metadata.
- **`audit_events` & `case_notes`**: Hash-chained forensic events (`sequence_number`, `event_hash`, `previous_event_hash`, `checkpoint_signature`) and investigator notes.

## 2. Database Migration Commands
```bash
cd backend
alembic upgrade head
```
