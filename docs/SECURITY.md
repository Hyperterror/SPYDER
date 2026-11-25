# Security & Access Control

## 1. Authentication & Session Lifecycle
- **Access & Refresh Tokens (`backend/app/core/security.py`, `backend/app/api/auth.py`)**:
  - JWT claims carry `sub`, `role`, `jti`, `sid` (session ID), and `fid` (token family ID).
  - Refresh tokens are persisted hashed in `user_sessions` and rotated on every `/api/v1/auth/refresh` call.
  - Presenting a previously rotated refresh token triggers automatic family revocation (`SECURITY_TOKEN_REUSE_DETECTED` audit event) and HTTP `401`.
  - `/api/v1/auth/logout` revokes the active `UserSession` immediately and clears browser cookies.
- **Browser Credential Handling (`frontend/src/lib/api.ts`, `auth.ts`)**:
  - Refresh token is stored in an `HttpOnly; SameSite=Lax` cookie (`COOKIE_SECURE=true` in production).
  - Double-submit CSRF protection requires matching `X-CSRF-Token` header (`spyder_csrf_token` cookie) on cookie refresh requests (`ALLOW_BODY_REFRESH=false` in production compose).
  - Access token is kept in memory / `sessionStorage` — never `localStorage`.

## 2. Role & Case-Level Authorization (`backend/app/core/authz.py`)
- Roles preserved: `ADMIN`, `SUPERVISOR`, `INVESTIGATOR`, `ANALYST`.
- `ADMIN`: system-wide access.
- `SUPERVISOR`: organization-scoped (`users.organization_id == cases.organization_id`) when `organization_id` is assigned.
- `INVESTIGATOR` & `ANALYST`: restricted strictly to assigned `CaseMember` cases (or creator for single-case views).
- **Strict Cross-Case Lead Gate (`all_cases_authorized`)**: Investigation leads, cross-case bridges, identity hypotheses, entity profiles, timelines, and review decision histories are returned **only** when the caller holds permission for **every** case in `source_case_ids | target_case_ids` (or `case_a | case_b`).

## 3. Forensic Audit Integrity & Production Guardrails
- **Tamper-Evident Audit Chain (`backend/app/services/audit_svc.py`)**: Concurrency-safe `sequence_number`, SHA-256 chain (`previous_event_hash -> event_hash`), optional HMAC `checkpoint_signature` (`AUDIT_SIGNING_KEY`), and `GET /api/v1/cases/{case_id}/audit/verify`.
- **Fail-Fast Production Startup (`validate_security_configuration`)**: Rejects default `JWT_SECRET_KEY`, empty `AUDIT_SIGNING_KEY`, and wildcard CORS when `ENVIRONMENT=production`.
- **Log Redaction (`backend/app/core/logging.py`)**: Structured JSON logs strip bearer tokens, passwords, secrets, cookies, and `raw_record` payloads.
- **Upload Bounds**: Streaming bounded chunk reader enforces `MAX_UPLOAD_BYTES` (default 50 MB, HTTP `413`), filename sanitization, magic-byte validation, and XLSX zip-bomb/XXE checks.
