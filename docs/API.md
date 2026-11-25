# SPYDER-DETECT API Reference

All endpoints require Bearer JWT authentication unless marked public, enforce role & case authorization via `app/core/authz.py`, and include `X-Request-ID` trace headers.

## Health & Observability
- `GET /health` — Service metadata (`status`, `app`, `version`, `environment`) [Public]
- `GET /health/live` — Liveness probe [Public]
- `GET /health/ready` — Dependency readiness (`database`, `neo4j` [optional], `storage`, `queue`) [Public]

## Authentication (`/api/v1/auth`)
- `POST /api/v1/auth/login` — Issues short-lived access JWT + sets `HttpOnly` refresh cookie + `spyder_csrf_token`
- `POST /api/v1/auth/refresh` — Rotates refresh token with reuse-detection (`X-CSRF-Token` required for cookie refresh)
- `POST /api/v1/auth/logout` — Revokes active `UserSession` and clears cookies
- `GET /api/v1/auth/me` — Returns current user profile

## Cases & Timeline (`/api/v1/cases`)
- `GET /api/v1/cases` · `POST /api/v1/cases` · `GET /{case_id}` · `PATCH /{case_id}` · `GET /{case_id}/summary`
- `POST /{case_id}/members` · `DELETE /{case_id}/members/{user_id}`
- `GET /{case_id}/timeline` — Unified chronology from ACTIVE parsed records (`modality`, `entity`, `limit` filters)

## Evidence Locker & Pipeline (`/api/v1/cases/{case_id}/evidence`)
- `GET /` · `POST /upload` (streaming size guard `MAX_UPLOAD_BYTES`) · `GET /{evidence_id}`
- `GET /{evidence_id}/download` — Streams original immutable bytes
- `POST /{evidence_id}/supersede` — Registers `v{N+1}` replacement while keeping original `v{N}` untouched
- `POST /{evidence_id}/withdraw` — Marks `WITHDRAWN` with rationale without deleting original bytes
- `POST /{evidence_id}/verify-integrity` — Recomputes SHA-256 against stored bytes
- `POST /{evidence_id}/process` (`?run_sync=true|false`) — Runs canonical ingestion + ER + graph snapshot pipeline
- `POST /{evidence_id}/parse` — Deprecated wrapper delegating to canonical pipeline (`Deprecation: true`)
- `POST /{evidence_id}/cancel` · `POST /{evidence_id}/retry` · `GET /{evidence_id}/status`
- `GET /{evidence_id}/parsed-records` · `GET /{evidence_id}/audit`

## Knowledge Graph (`/api/v1/cases/{case_id}/graph`)
- `GET /subgraph` (queries Neo4j when available, with multi-modality PostgreSQL fallback & time/entity filters)
- `GET /snapshot` — Returns active `GraphSnapshot` version & provenance
- `GET /entity-search` · `GET /nodes/{node_id}` · `GET /edges/{edge_id}` · `POST /path`

## Audit & Notes (`/api/v1/cases/{case_id}`)
- `GET /audit` · `GET /audit/verify` (verifies hash chain integrity) · `GET /notes` · `POST /notes`

## Intelligence, Entity Resolution & Consistency (`/api/v1/intelligence`)
- `GET /leads` · `GET /leads/{lead_id}` · `GET /leads/{lead_id}/evidence` · `POST /leads/{lead_id}/review`
- `GET /cross-case`
- `GET /identity-hypotheses` · `GET /identity-hypotheses/{hypothesis_id}` · `POST /identity-hypotheses/{hypothesis_id}/review`
- `GET /entities/{entity_id}`
- `GET /priorities` · `GET /priorities/{person_id}` · `GET /priorities/{person_id}/evidence`
- `POST /consistency/analyze` · `POST /consistency/claims` · `GET /consistency` · `GET /consistency/{result_id}`
- `PATCH /consistency/{result_id}/claim` · `POST /consistency/{result_id}/review`
- `GET /decisions` · `GET /models`
