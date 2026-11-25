"""
Milestone 3 Intelligence Integration, Live Entity Resolution, Human Review,
Entity Profile, Timeline, Consistency Claim Editing, and Part 17 End-to-End Tests.
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.case import Case, CaseMember
from app.models.intelligence import IdentityHypothesis, IntelligenceLeadRecord
from app.models.user import User


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
    monkeypatch.setattr("app.services.evidence_orchestrator.GRAPH_OUTPUT_DIR", tmp_path / "graph_out")
    return TestClient(app)


def _create_user(db, email: str, role: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Int!Pass123"),
        display_name=email.split("@")[0],
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_part17_end_to_end_cross_case_and_security_isolation(client, db):
    """
    Executes the full PRD Part 17 Scenario:
    1. Investigator A creates Case A and uploads PERSONS + CDR evidence.
    2. Investigator B creates Case B and uploads PERSONS evidence with matching phone/device/name.
    3. Pipeline runs -> generates IdentityHypothesis & cross-case IntelligenceLeadRecord (never self-comparison).
    4. Supervisor reviews & accepts the hypothesis and lead with rationale -> recorded in audit/decision history.
    5. Security check: Investigator A (Case A only) cannot access Case B via leads, hypotheses,
       entity profile, timeline, or decision history!
    """
    inv_a = _create_user(db, f"inva_{uuid.uuid4().hex[:5]}@spyder.gov", "INVESTIGATOR")
    inv_b = _create_user(db, f"invb_{uuid.uuid4().hex[:5]}@spyder.gov", "INVESTIGATOR")
    sup = _create_user(db, f"sup_{uuid.uuid4().hex[:5]}@spyder.gov", "SUPERVISOR")

    hdr_a = {"Authorization": f"Bearer {create_access_token(str(inv_a.id), inv_a.role)}"}
    hdr_b = {"Authorization": f"Bearer {create_access_token(str(inv_b.id), inv_b.role)}"}
    hdr_sup = {"Authorization": f"Bearer {create_access_token(str(sup.id), sup.role)}"}

    # 1. Create Case A and Case B
    ca = client.post("/api/v1/cases", json={"title": "Part17 Case Alpha", "case_type": "HUMAN_TRAFFICKING"}, headers=hdr_a).json()
    cb = client.post("/api/v1/cases", json={"title": "Part17 Case Beta", "case_type": "HUMAN_TRAFFICKING"}, headers=hdr_b).json()

    # 2. Upload matching PERSONS observations to Case A and Case B
    persons_a = (
        b"person_id,raw_name,alias,phone_id,device_id\n"
        b"PER_ALPHA_01,Vikram Malhotra,Vicky,+919876500011,DEV_SHARED_77\n"
    )
    persons_b = (
        b"person_id,raw_name,alias,phone_id,device_id\n"
        b"PER_BETA_01,Vikram Malhotra,Vicky,+919876500011,DEV_SHARED_77\n"
    )

    up_a = client.post(
        f"/api/v1/cases/{ca['id']}/evidence/upload",
        files={"file": ("persons_a.csv", io.BytesIO(persons_a), "text/csv")},
        headers=hdr_a,
    )
    assert up_a.status_code == 201
    proc_a = client.post(f"/api/v1/cases/{ca['id']}/evidence/{up_a.json()['id']}/process?run_sync=true", headers=hdr_a)
    assert proc_a.status_code == 200
    assert proc_a.json()["status"] == "COMPLETED"

    up_b = client.post(
        f"/api/v1/cases/{cb['id']}/evidence/upload",
        files={"file": ("persons_b.csv", io.BytesIO(persons_b), "text/csv")},
        headers=hdr_b,
    )
    assert up_b.status_code == 201
    proc_b = client.post(f"/api/v1/cases/{cb['id']}/evidence/{up_b.json()['id']}/process?run_sync=true", headers=hdr_b)
    assert proc_b.status_code == 200
    assert proc_b.json()["status"] == "COMPLETED"

    # 3. Verify IdentityHypothesis was created across Case A & Case B (not self-comparison!)
    hyps_sup = client.get("/api/v1/intelligence/identity-hypotheses", headers=hdr_sup)
    assert hyps_sup.status_code == 200
    matching_hyps = [
        h for h in hyps_sup.json()["hypotheses"]
        if {h["person_a_ref"], h["person_b_ref"]} == {"PER_ALPHA_01", "PER_BETA_01"}
    ]
    assert len(matching_hyps) == 1
    hyp = matching_hyps[0]
    assert hyp["case_a_ref"] != hyp["case_b_ref"]
    assert hyp["match_probability"] >= 0.70

    # 4. Supervisor inspects side-by-side detail and ACCEPTS hypothesis
    hyp_detail = client.get(f"/api/v1/intelligence/identity-hypotheses/{hyp['id']}", headers=hdr_sup)
    assert hyp_detail.status_code == 200
    assert "profile_a" in hyp_detail.json() and "profile_b" in hyp_detail.json()

    rev_hyp = client.post(
        f"/api/v1/intelligence/identity-hypotheses/{hyp['id']}/review",
        json={"status": "ACCEPTED", "rationale": "Verified shared phone +919876500011 and device DEV_SHARED_77 across dossiers"},
        headers=hdr_sup,
    )
    assert rev_hyp.status_code == 200
    assert rev_hyp.json()["status"] == "ACCEPTED"

    # 5. Cross-case lead exists and Supervisor reviews it
    leads_sup = client.get("/api/v1/intelligence/leads?is_cross_case=true&limit=200", headers=hdr_sup)
    assert leads_sup.status_code == 200
    er_lead = next((l for l in leads_sup.json()["leads"] if l["lead_id"].startswith("LEAD_ER_")), None)
    assert er_lead is not None

    rev_lead = client.post(
        f"/api/v1/intelligence/leads/{er_lead['lead_id']}/review",
        json={"status": "ACCEPTED_FOR_FURTHER_INVESTIGATION", "rationale": "Escalated to joint taskforce"},
        headers=hdr_sup,
    )
    assert rev_lead.status_code == 200
    assert rev_lead.json()["status"] == "ACCEPTED_FOR_FURTHER_INVESTIGATION"

    # 6. Decision History & Entity Profile & Timeline accessible to Supervisor
    decs = client.get("/api/v1/intelligence/decisions", headers=hdr_sup)
    assert decs.status_code == 200
    assert decs.json()["total"] >= 2

    ent_prof = client.get("/api/v1/intelligence/entities/PER_ALPHA_01", headers=hdr_sup)
    assert ent_prof.status_code == 200
    assert len(ent_prof.json()["identity_hypotheses"]) >= 1

    tl = client.get(f"/api/v1/cases/{ca['id']}/timeline", headers=hdr_a)
    assert tl.status_code == 200
    assert tl.json()["total"] >= 1

    # 7. SECURITY ACCEPTANCE SCENARIO: Investigator A (Case A only) cannot access Case B!
    assert client.get(f"/api/v1/intelligence/identity-hypotheses/{hyp['id']}", headers=hdr_a).status_code == 403
    assert client.get(f"/api/v1/intelligence/leads/{er_lead['lead_id']}", headers=hdr_a).status_code == 403
    assert client.get(f"/api/v1/cases/{cb['id']}/timeline", headers=hdr_a).status_code == 403
    assert client.get("/api/v1/intelligence/entities/PER_BETA_01", headers=hdr_a).status_code == 404

    hyps_a = client.get("/api/v1/intelligence/identity-hypotheses", headers=hdr_a).json()["hypotheses"]
    assert all(h["id"] != hyp["id"] for h in hyps_a)

    decs_a = client.get("/api/v1/intelligence/decisions", headers=hdr_a).json()["decisions"]
    assert all(d["target_id"] not in (hyp["id"], er_lead["lead_id"]) for d in decs_a)


def test_consistency_claim_correction_and_persistence(client, db):
    sup = _create_user(db, f"cons_sup_{uuid.uuid4().hex[:5]}@spyder.gov", "SUPERVISOR")
    hdr = {"Authorization": f"Bearer {create_access_token(str(sup.id), sup.role)}"}

    resp = client.post(
        "/api/v1/intelligence/consistency/analyze",
        json={
            "statement_text": "I called +918528419506 on June 3, 2025.",
            "case_id": "CASE_001",
            "subject_entity_id": "CASE_001_PER_01",
        },
        headers=hdr,
    )
    assert resp.status_code == 200
    res_id = resp.json()["results"][0]["result_id"]

    # Edit extracted claim to negated=True -> re-evaluates and preserves original_claim
    patch = client.patch(
        f"/api/v1/intelligence/consistency/{res_id}/claim",
        json={"negated": True, "reviewer_comment": "Investigator corrected negation flag"},
        headers=hdr,
    )
    assert patch.status_code == 200
    assert patch.json()["original_claim"]["negated"] is False
    assert patch.json()["current_claim"]["negated"] is True
    assert patch.json()["evaluation"]["status"] == "CONTRADICTED"
