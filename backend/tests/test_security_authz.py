"""
Milestone 1 Security, Authorization, Session Lifecycle, and Forensic Data Integrity Tests.

Covers:
- Unauthorized case access & organization isolation
- Evidence ownership verification (anti-IDOR on audit, parsed-records, download, verify, notes)
- Cross-case lead leakage prevention (Case A investigator cannot see Case B via leads/priorities/graph)
- JWT expiration, refresh rotation, reuse family revocation, logout session revocation, CSRF
- Production startup secret validation
- Bounded streaming upload size limit
- Evidence versioning (supersede / withdraw preserving originals)
- Concurrency-safe audit hash chain & tamper-detection verification
"""
from __future__ import annotations

import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, validate_security_configuration
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.intelligence.leads import LeadRepository
from app.main import app
from app.models.audit import AuditEvent
from app.models.auth import UserSession
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_svc import create_audit_event, verify_audit_chain


test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=test_engine)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db():
    session = TestSession()
    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()


@pytest.fixture
def client(db, monkeypatch, tmp_path):
    import app.services.storage as storage_mod
    inst = storage_mod.StorageService.__new__(storage_mod.StorageService)
    inst.bucket = "evidence"
    inst._local_mode = True
    inst._client = None
    inst._local_root = tmp_path / "storage"
    inst._local_root.mkdir(parents=True, exist_ok=True)
    storage_mod._storage_instance = inst
    monkeypatch.setattr("app.api.evidence.upsert_document_node", lambda *a, **kw: {})
    return TestClient(app)


def _make_user(db, email: str, role: str = "INVESTIGATOR", org_id=None, password: str = "StrongPass!23") -> User:
    u = db.query(User).filter(User.email == email).first()
    if u:
        return u
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        display_name=email.split("@")[0],
        role=role,
        organization_id=org_id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_case(db, case_code: str, title: str, org_id=None, ext_ref: str | None = None) -> Case:
    c = db.query(Case).filter(Case.case_code == case_code).first()
    if c:
        return c
    c = Case(
        id=uuid.uuid4(),
        case_code=case_code,
        external_case_ref=ext_ref,
        title=title,
        case_type="HUMAN_TRAFFICKING",
        status="ACTIVE",
        organization_id=org_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _add_member(db, case_id, user_id, role: str = "INVESTIGATOR"):
    m = db.query(CaseMember).filter(CaseMember.case_id == case_id, CaseMember.user_id == user_id).first()
    if not m:
        db.add(CaseMember(case_id=case_id, user_id=user_id, case_role=role))
        db.commit()


# =========================================================================
# 1. EVIDENCE OWNERSHIP & CASE ISOLATION TESTS
# =========================================================================

def test_evidence_ownership_prevents_cross_case_idor(client, db):
    inv_a = _make_user(db, "inv_a_sec@spyder.gov", "INVESTIGATOR")
    inv_b = _make_user(db, "inv_b_sec@spyder.gov", "INVESTIGATOR")
    case_a = _make_case(db, "SEC-CASE-A", "Case Alpha")
    case_b = _make_case(db, "SEC-CASE-B", "Case Beta")
    _add_member(db, case_a.id, inv_a.id)
    _add_member(db, case_b.id, inv_b.id)

    hdr_a = {"Authorization": f"Bearer {create_access_token(str(inv_a.id), inv_a.role)}"}
    hdr_b = {"Authorization": f"Bearer {create_access_token(str(inv_b.id), inv_b.role)}"}

    csv_b = b"calling_number,called_number,start_time\n+919800000001,+919800000002,2026-01-01 10:00:00\n"
    up = client.post(
        f"/api/v1/cases/{case_b.id}/evidence/upload",
        files={"file": ("secret_b.csv", io.BytesIO(csv_b), "text/csv")},
        headers=hdr_b,
    )
    assert up.status_code == 201
    ev_b_id = up.json()["id"]

    # Investigator A owns Case A, tries to probe Case B's evidence_id via Case A's URL
    for suffix in ["", "/audit", "/parsed-records", "/download", "/status"]:
        r = client.get(f"/api/v1/cases/{case_a.id}/evidence/{ev_b_id}{suffix}", headers=hdr_a)
        assert r.status_code == 404, f"Expected 404 for suffix '{suffix}', got {r.status_code}"

    r_verify = client.post(f"/api/v1/cases/{case_a.id}/evidence/{ev_b_id}/verify-integrity", headers=hdr_a)
    assert r_verify.status_code == 404

    # Attaching Case B's evidence_id to a note in Case A must fail
    r_note = client.post(
        f"/api/v1/cases/{case_a.id}/notes",
        json={"note_text": "Cross-case probe", "evidence_id": ev_b_id},
        headers=hdr_a,
    )
    assert r_note.status_code == 404


def test_organization_isolation_for_supervisors(client, db):
    org_1 = Organization(id=uuid.uuid4(), code="ORG_NORTH", name="North Unit")
    org_2 = Organization(id=uuid.uuid4(), code="ORG_SOUTH", name="South Unit")
    db.add_all([org_1, org_2])
    db.commit()

    sup_1 = _make_user(db, "sup1@spyder.gov", "SUPERVISOR", org_id=org_1.id)
    case_2 = _make_case(db, "ORG2-CASE-01", "South Confidential", org_id=org_2.id)

    hdr_sup1 = {"Authorization": f"Bearer {create_access_token(str(sup_1.id), sup_1.role)}"}
    resp = client.get(f"/api/v1/cases/{case_2.id}", headers=hdr_sup1)
    assert resp.status_code == 403


# =========================================================================
# 2. CROSS-CASE INTELLIGENCE LEAKAGE TESTS
# =========================================================================

def test_cross_case_leads_strictly_isolated(client, db):
    """
    PRD Section 8.2 & 30: An investigator authorized ONLY for CASE_001 must NEVER see
    cross-case leads linking CASE_001 to CASE_002 (or any other unauthorized case),
    nor retrieve them via /leads/{id}, /leads/{id}/evidence, or /cross-case.
    """
    inv_c1 = _make_user(db, "inv_case001_only@spyder.gov", "INVESTIGATOR")
    c1 = _make_case(db, "CASE_001", "Case 001")
    _add_member(db, c1.id, inv_c1.id)

    hdr = {"Authorization": f"Bearer {create_access_token(str(inv_c1.id), inv_c1.role)}"}

    # Find an actual cross-case lead touching CASE_001 from the repo
    repo = LeadRepository.get_instance()
    repo.load_if_needed()
    _, all_cross = repo.get_leads(is_cross_case=True, limit=500)
    c1_cross = next(
        (l for l in all_cross if "CASE_001" in (l.source_case_ids + l.target_case_ids)),
        None,
    )
    assert c1_cross is not None, "Expected cross-case lead touching CASE_001 in dataset"

    # 1. /leads must not expose any lead with unauthorized case IDs
    r_list = client.get("/api/v1/intelligence/leads?limit=200", headers=hdr)
    assert r_list.status_code == 200
    for lead in r_list.json()["leads"]:
        all_c = set(lead["source_case_ids"]) | set(lead["target_case_ids"])
        assert all_c <= {"CASE_001"}, f"Unauthorized case leaked in /leads: {all_c}"

    # 2. /cross-case must return 0 leads for a single-case investigator
    r_cc = client.get("/api/v1/intelligence/cross-case?limit=200", headers=hdr)
    assert r_cc.status_code == 200
    assert r_cc.json()["total"] == 0

    # 3. Direct /leads/{id} and /leads/{id}/evidence must reject with 403
    r_detail = client.get(f"/api/v1/intelligence/leads/{c1_cross.lead_id}", headers=hdr)
    assert r_detail.status_code == 403
    r_ev = client.get(f"/api/v1/intelligence/leads/{c1_cross.lead_id}/evidence", headers=hdr)
    assert r_ev.status_code == 403

    # 4. When user IS authorized for all cases in that lead, full lead is accessible
    for cid_code in set(c1_cross.source_case_ids) | set(c1_cross.target_case_ids):
        c_obj = _make_case(db, cid_code, f"Case {cid_code}")
        _add_member(db, c_obj.id, inv_c1.id)
    r_detail_ok = client.get(f"/api/v1/intelligence/leads/{c1_cross.lead_id}", headers=hdr)
    assert r_detail_ok.status_code == 200


# =========================================================================
# 3. JWT ROTATION, REUSE DETECTION, EXPIRATION & LOGOUT REVOCATION
# =========================================================================

def test_jwt_session_lifecycle_and_reuse_detection(client, db):
    user = _make_user(db, "jwt_lifecycle@spyder.gov", "INVESTIGATOR", password="Complex!Password9")

    # 1. Login sets cookies & returns session-bound tokens
    login_resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Complex!Password9"})
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    access_1 = tokens["access_token"]
    refresh_1 = tokens["refresh_token"]
    assert "spyder_refresh_token" in login_resp.cookies
    assert "spyder_csrf_token" in login_resp.cookies

    # Access works
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_1}"}).status_code == 200

    # 2. Refresh rotates refresh token (without CSRF cookie check when JSON body passed, or with CSRF for cookie)
    ref_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert ref_resp.status_code == 200
    access_2 = ref_resp.json()["access_token"]
    refresh_2 = ref_resp.json()["refresh_token"]
    assert refresh_2 != refresh_1

    # 3. Reusing already-rotated refresh_1 triggers family-wide revocation
    reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert reuse_resp.status_code == 401
    assert "reuse detected" in reuse_resp.json()["detail"].lower()

    # Subsequent use of refresh_2 AND access_2 must be rejected because family was revoked
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_2}"}).status_code == 401


def test_logout_invalidates_session_and_expired_token_rejected(client, db):
    user = _make_user(db, "logout_user@spyder.gov", "INVESTIGATOR", password="Logout!Pass99")
    login_resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Logout!Pass99"})
    assert login_resp.status_code == 200
    access = login_resp.json()["access_token"]
    hdr = {"Authorization": f"Bearer {access}"}

    # Logout
    out_resp = client.post("/api/v1/auth/logout", headers=hdr)
    assert out_resp.status_code == 200
    assert out_resp.json()["revoked_sessions"] >= 1

    # Access token from logged-out session is now rejected
    assert client.get("/api/v1/auth/me", headers=hdr).status_code == 401

    # Expired access token is rejected
    expired_token = create_access_token(str(user.id), user.role, expires_minutes=-5)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}).status_code == 401


def test_cookie_refresh_requires_csrf_header(client, db):
    user = _make_user(db, "csrf_user@spyder.gov", "INVESTIGATOR", password="Csrf!Pass99")
    login_resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Csrf!Pass99"})
    assert login_resp.status_code == 200
    csrf = login_resp.cookies.get("spyder_csrf_token")
    assert csrf

    # Cookie-based refresh without X-CSRF-Token header must fail 403
    r_no_csrf = client.post("/api/v1/auth/refresh")
    assert r_no_csrf.status_code == 403

    # With matching X-CSRF-Token header it succeeds
    r_ok = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert r_ok.status_code == 200


# =========================================================================
# 4. PRODUCTION CONFIG VALIDATION & BOUNDED UPLOAD & EVIDENCE VERSIONING
# =========================================================================

def test_production_startup_rejects_default_secrets():
    bad = Settings(ENVIRONMENT="production", DEBUG=False)
    with pytest.raises(RuntimeError, match="Production security configuration check failed"):
        validate_security_configuration(bad)

    good = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET_KEY="x" * 40,
        DATABASE_URL="postgresql://produser:StrongProdDbPass123@db:5432/spyder",
        NEO4J_PASSWORD="StrongNeo4jPassword123",
        MINIO_SECRET_KEY="StrongMinioSecretKey123",
        COOKIE_SECURE=True,
        CORS_ORIGINS="https://spyder.internal",
    )
    validate_security_configuration(good)


def test_bounded_upload_rejects_oversized_payload(client, db, monkeypatch):
    user = _make_user(db, "upload_limit@spyder.gov", "INVESTIGATOR")
    case = _make_case(db, "LIM-CASE-01", "Limit Test")
    _add_member(db, case.id, user.id)
    hdr = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}

    monkeypatch.setattr("app.api.evidence.MAX_FILE_SIZE", 64)
    big_csv = b"calling_number,called_number,start_time\n" + b"+919800000001,+919800000002,2026-01-01\n" * 5
    resp = client.post(
        f"/api/v1/cases/{case.id}/evidence/upload",
        files={"file": ("too_big.csv", io.BytesIO(big_csv), "text/csv")},
        headers=hdr,
    )
    assert resp.status_code == 413


def test_evidence_supersede_and_withdraw_preserve_originals(client, db):
    user = _make_user(db, "ev_ver@spyder.gov", "INVESTIGATOR")
    case = _make_case(db, "VER-CASE-01", "Versioning Test")
    _add_member(db, case.id, user.id, role="CASE_OWNER")
    hdr = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}

    v1_bytes = b"calling_number,called_number,start_time\n+919800000010,+919800000011,2026-01-01 10:00:00\n"
    r1 = client.post(
        f"/api/v1/cases/{case.id}/evidence/upload",
        files={"file": ("cdr_v1.csv", io.BytesIO(v1_bytes), "text/csv")},
        headers=hdr,
    )
    assert r1.status_code == 201
    ev1_id = r1.json()["id"]
    ev1_hash = r1.json()["sha256_hash"]

    v2_bytes = b"calling_number,called_number,start_time\n+919800000010,+919800000012,2026-01-01 11:00:00\n"
    r2 = client.post(
        f"/api/v1/cases/{case.id}/evidence/{ev1_id}/supersede",
        files={"file": ("cdr_v2.csv", io.BytesIO(v2_bytes), "text/csv")},
        data={"reason": "Corrected operator export"},
        headers=hdr,
    )
    assert r2.status_code == 201
    assert r2.json()["version_number"] == 2
    assert r2.json()["supersedes_evidence_id"] == ev1_id

    # Original v1 remains preserved & downloadable with original hash
    dl1 = client.get(f"/api/v1/cases/{case.id}/evidence/{ev1_id}/download", headers=hdr)
    assert dl1.status_code == 200
    assert dl1.content == v1_bytes
    assert dl1.headers["x-content-sha256"] == ev1_hash

    # Withdraw v2
    wd = client.post(
        f"/api/v1/cases/{case.id}/evidence/{r2.json()['id']}/withdraw",
        json={"reason": "Entered under wrong warrant"},
        headers=hdr,
    )
    assert wd.status_code == 200
    assert wd.json()["lifecycle_status"] == "WITHDRAWN"


# =========================================================================
# 5. AUDIT CHAIN CONCURRENCY & TAMPER VERIFICATION
# =========================================================================

def test_concurrent_audit_chain_and_tamper_detection(client, db):
    user = _make_user(db, "audit_user@spyder.gov", "INVESTIGATOR")
    case = _make_case(db, "AUD-CASE-01", "Audit Chain Test")
    _add_member(db, case.id, user.id)
    hdr = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}

    def _write_event(i: int):
        s = TestSession()
        try:
            create_audit_event(
                db=s,
                event_type="CONCURRENT_ACTION",
                case_id=str(case.id),
                actor_user_id=str(user.id),
                metadata={"seq": i},
            )
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_write_event, range(10)))

    verify_res = client.get(f"/api/v1/cases/{case.id}/audit/verify", headers=hdr)
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True
    assert verify_res.json()["checked_events"] == 10

    # Tamper with an event metadata payload directly in DB -> chain verification must fail
    ev = db.query(AuditEvent).filter(AuditEvent.case_id == case.id).first()
    ev.event_metadata = {"tampered": True}
    db.commit()

    check = verify_audit_chain(db, case_id=str(case.id))
    assert check["valid"] is False
    assert check["broken_at_event_id"] == str(ev.id)
