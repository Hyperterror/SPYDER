"""
Milestone 2 Unified Pipeline, Idempotency, Atomic Graph Publication, and Worker Tests.
"""
from __future__ import annotations

import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem, EvidenceProcessingJob, ParsedRecord
from app.models.graph import GraphSnapshot
from app.models.user import User
from app.services.evidence_orchestrator import get_orchestrator
from app.services.graph_publisher import publish_graph_snapshot


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


@pytest.fixture
def auth_case(db):
    user = User(
        id=uuid.uuid4(),
        email=f"pipe_{uuid.uuid4().hex[:6]}@spyder.gov",
        password_hash=hash_password("Pipe!Pass123"),
        display_name="Pipeline Tester",
        role="INVESTIGATOR",
        is_active=True,
    )
    case = Case(
        id=uuid.uuid4(),
        case_code=f"PIPE-{uuid.uuid4().hex[:6].upper()}",
        title="Pipeline Test Case",
        case_type="CYBER_CRIME",
        status="ACTIVE",
    )
    db.add_all([user, case])
    db.flush()
    db.add(CaseMember(case_id=case.id, user_id=user.id, case_role="CASE_OWNER"))
    db.commit()
    hdr = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    return user, case, hdr


def test_idempotent_reprocessing_creates_no_duplicates(client, db, auth_case):
    _, case, hdr = auth_case
    csv_bytes = (
        b"calling_number,called_number,start_time,duration_seconds,tower_id\n"
        b"+919811100001,+919811100002,2026-02-01 10:00:00,45,TWR_A\n"
        b"+919811100002,+919811100003,2026-02-01 10:05:00,30,TWR_B\n"
    )
    up = client.post(
        f"/api/v1/cases/{case.id}/evidence/upload",
        files={"file": ("idem_cdr.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=hdr,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # Process first time
    r1 = client.post(f"/api/v1/cases/{case.id}/evidence/{ev_id}/process?run_sync=true", headers=hdr)
    assert r1.status_code == 200
    assert r1.json()["status"] == "COMPLETED"
    snap1 = r1.json()["graph_snapshot_version"]

    count1 = db.query(ParsedRecord).filter(ParsedRecord.evidence_id == uuid.UUID(ev_id)).count()
    assert count1 == 2

    # Process second time (idempotent re-run)
    r2 = client.post(f"/api/v1/cases/{case.id}/evidence/{ev_id}/process?run_sync=true", headers=hdr)
    assert r2.status_code == 200
    assert r2.json()["status"] == "COMPLETED"
    snap2 = r2.json()["graph_snapshot_version"]
    assert snap2 != snap1

    count2 = db.query(ParsedRecord).filter(ParsedRecord.evidence_id == uuid.UUID(ev_id)).count()
    assert count2 == 2, "Reprocessing duplicated ParsedRecord rows!"

    # Active graph snapshot count must be exactly 1
    active_snaps = db.query(GraphSnapshot).filter(GraphSnapshot.status == "ACTIVE").all()
    assert len(active_snaps) == 1
    assert active_snaps[0].version_tag == snap2

    # Synthetic authoritative CSV must NOT have been modified
    from graph_analysis.config import EVIDENCE_DIR
    cdr_csv = EVIDENCE_DIR / "cdr.csv"
    if cdr_csv.exists():
        assert "+919811100001" not in cdr_csv.read_text(encoding="utf-8")


def test_failed_graph_publication_preserves_previous_active_snapshot(db, tmp_path):
    valid_snap = publish_graph_snapshot(
        db=db,
        output_dir=tmp_path / "graph_snap",
        include_baseline_dataset=True,
    )
    assert valid_snap.status == "ACTIVE"
    assert (tmp_path / "graph_snap" / "active_snapshot.json").exists()
    active_before = (tmp_path / "graph_snap" / "active_snapshot.json").read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="Simulated graph structural validation failure"):
        publish_graph_snapshot(
            db=db,
            output_dir=tmp_path / "graph_snap",
            include_baseline_dataset=True,
            simulate_validation_failure=True,
        )

    db.refresh(valid_snap)
    assert valid_snap.status == "ACTIVE"
    assert (tmp_path / "graph_snap" / "active_snapshot.json").read_text(encoding="utf-8") == active_before


def test_legacy_parse_delegates_with_deprecation_and_xlsx_works(client, db, auth_case):
    _, case, hdr = auth_case

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["sender_account", "receiver_account", "amount", "timestamp", "transaction_type"])
    ws.append(["ACC_XLSX_1", "ACC_XLSX_2", 1500, "2026-02-02 12:00:00", "UPI"])
    buf = io.BytesIO()
    wb.save(buf)

    up = client.post(
        f"/api/v1/cases/{case.id}/evidence/upload",
        files={"file": ("txns.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=hdr,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    parse_resp = client.post(
        f"/api/v1/cases/{case.id}/evidence/{ev_id}/parse?run_sync=true",
        headers=hdr,
    )
    assert parse_resp.status_code == 200
    assert parse_resp.headers.get("deprecation") == "true"
    assert parse_resp.json()["status"] == "COMPLETED"
    assert parse_resp.json()["deprecated"] is True


def test_job_cancel_and_retry_lifecycle(client, db, auth_case):
    user, case, hdr = auth_case
    csv_bytes = b"calling_number,called_number,start_time\n+919822200001,+919822200002,2026-02-01 10:00:00\n"
    up = client.post(
        f"/api/v1/cases/{case.id}/evidence/upload",
        files={"file": ("cancel_test.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=hdr,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # Create a QUEUED job directly and cancel it
    job = get_orchestrator().create_processing_job(ev_id, str(case.id), str(user.id), db)
    assert job.status == "QUEUED"

    c_resp = client.post(f"/api/v1/cases/{case.id}/evidence/{ev_id}/cancel", headers=hdr)
    assert c_resp.status_code == 200
    assert c_resp.json()["status"] == "CANCELLED"

    # Retry succeeds
    r_resp = client.post(f"/api/v1/cases/{case.id}/evidence/{ev_id}/retry?run_sync=true", headers=hdr)
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "COMPLETED"
