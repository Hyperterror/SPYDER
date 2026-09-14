"""
Seed script — idempotent.
Creates users, one case, uploads 3 CSV evidence files, and parses them.

Usage (from backend/ directory):
    python -m app.scripts.seed
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.core.security import hash_password
from app.models.user import User
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem, ParsedRecord
from app.services.storage import get_storage
from app.services.hashing import calculate_sha256
from app.services.audit_svc import create_audit_event
from app.parsers.cdr import parse_cdr_csv
from app.parsers.transaction import parse_transaction_csv

# ── Locate synthetic data ─────────────────────────────────────────────────────
_here = Path(__file__).resolve()
SYNTHETIC_DATA_DIR = _here.parents[4] / "synthetic_data"
if not SYNTHETIC_DATA_DIR.exists():
    SYNTHETIC_DATA_DIR = Path.cwd().parent / "synthetic_data"
if not SYNTHETIC_DATA_DIR.exists():
    SYNTHETIC_DATA_DIR = Path.cwd() / "synthetic_data"

print(f"[seed] Synthetic data dir: {SYNTHETIC_DATA_DIR}")

# ── Config ────────────────────────────────────────────────────────────────────
USERS = [
    {"email": "admin@spyder.gov",        "password": "Admin@1234",      "display_name": "System Admin",    "role": "ADMIN"},
    {"email": "supervisor@spyder.gov",   "password": "Supervisor@1234", "display_name": "Raj Sharma",      "role": "SUPERVISOR"},
    {"email": "investigator@spyder.gov", "password": "Invest@1234",     "display_name": "Samridhi Gupta",  "role": "INVESTIGATOR"},
]

EVIDENCE_FILES = [
    {"file": "cdr_operator_a.csv",  "source_label": "CDR Operator A",   "job_type": "CDR"},
    {"file": "cdr_operator_b.csv",  "source_label": "CDR Operator B",   "job_type": "CDR"},
    {"file": "upi_transactions.csv","source_label": "UPI Transactions",  "job_type": "TRANSACTION"},
]


def get_session():
    engine = create_engine(
        settings.DATABASE_URL,
        **({"connect_args": {"check_same_thread": False}} if settings.DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True})
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_users(db):
    created = []
    for u in USERS:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if existing:
            print(f"  [skip] {u['email']}")
            created.append(existing)
            continue
        user = User(id=uuid.uuid4(), email=u["email"],
                    password_hash=hash_password(u["password"]),
                    display_name=u["display_name"], role=u["role"], is_active=True)
        db.add(user)
        print(f"  [+] {u['email']} ({u['role']})")
        created.append(user)
    db.commit()
    return created


def seed_case(db, admin, investigator):
    existing = db.query(Case).filter(Case.title == "Operation Falcon").first()
    if existing:
        print(f"  [skip] case already exists: {existing.case_code}")
        return existing

    year = datetime.now(timezone.utc).year
    count = db.query(Case).count()
    case_code = f"HT-{year}-{str(count + 1).zfill(3)}"
    case = Case(id=uuid.uuid4(), case_code=case_code, title="Operation Falcon",
                case_type="CYBER_CRIME",
                description="Cyber fraud network — phishing, money mule accounts, cross-border laundering.",
                status="ACTIVE", created_by=admin.id)
    db.add(case)
    db.flush()
    db.add(CaseMember(case_id=case.id, user_id=admin.id, case_role="CASE_OWNER", assigned_by=admin.id))
    db.add(CaseMember(case_id=case.id, user_id=investigator.id, case_role="INVESTIGATOR", assigned_by=admin.id))
    db.commit()
    db.refresh(case)
    print(f"  [+] case {case.case_code}")
    return case


def seed_evidence(db, case, uploader):
    storage = get_storage()
    items = []
    count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case.id).count()

    for idx, ef in enumerate(EVIDENCE_FILES):
        fp = SYNTHETIC_DATA_DIR / ef["file"]
        if not fp.exists():
            print(f"  [warn] {ef['file']} not found at {fp}")
            continue

        file_bytes = fp.read_bytes()
        sha256 = calculate_sha256(file_bytes)

        existing = db.query(EvidenceItem).filter(
            EvidenceItem.case_id == case.id, EvidenceItem.sha256_hash == sha256
        ).first()
        if existing:
            print(f"  [skip] {ef['file']} ({existing.evidence_code})")
            items.append(existing)
            continue

        eid = uuid.uuid4()
        code = f"EVD-{str(count + idx + 1).zfill(3)}"
        key = f"cases/{case.id}/evidence/{eid}/original/{ef['file']}"

        try:
            storage.upload(key, file_bytes, "text/csv")
        except Exception as e:
            print(f"  [warn] storage upload failed: {e}")

        ev = EvidenceItem(
            id=eid, case_id=case.id, evidence_code=code,
            original_filename=ef["file"], sanitized_filename=ef["file"],
            file_extension=".csv", mime_type="text/csv",
            file_size_bytes=len(file_bytes),
            object_storage_bucket=storage.bucket, object_storage_key=key,
            source_label=ef["source_label"], sha256_hash=sha256,
            hash_algorithm="SHA-256", integrity_status="VERIFIED",
            uploaded_by=uploader.id, parsing_status="PENDING", is_original=True,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        print(f"  [+] {code} — {ef['file']}")
        items.append(ev)

    return items


def parse_evidence(db, evidence_items, case_id):
    storage = get_storage()
    for ev in evidence_items:
        existing = db.query(ParsedRecord).filter(
            ParsedRecord.evidence_id == str(ev.id)
        ).count()
        if existing > 0:
            print(f"  [skip] {ev.original_filename} ({existing} records)")
            ev.parsing_status = "COMPLETED"
            db.commit()
            continue

        try:
            file_bytes = storage.download(ev.object_storage_bucket, ev.object_storage_key)
        except Exception:
            fp = SYNTHETIC_DATA_DIR / ev.original_filename
            if fp.exists():
                file_bytes = fp.read_bytes()
            else:
                print(f"  [warn] cannot read {ev.original_filename}")
                continue

        prov = dict(
            evidence_id=str(ev.id), case_id=str(ev.case_id),
            source_file_name=ev.original_filename, source_hash=ev.sha256_hash,
            verification_status="VERIFIED", relationship_status="DIRECT_RECORD",
            confidence_label="DIRECT_SOURCE_RECORD",
        )

        is_txn = any(kw in ev.original_filename.lower() for kw in ["transaction", "upi", "bank"])

        if is_txn:
            result = parse_transaction_csv(file_bytes, {}, str(ev.case_id), str(ev.id), ev.original_filename, ev.sha256_hash)
            for rec in result["records"]:
                nr = rec["normalized_record"]
                db.add(ParsedRecord(
                    case_id=str(ev.case_id), evidence_id=str(ev.id), record_type="TRANSACTION",
                    source_row_number=rec["source_row_number"],
                    raw_record=rec["raw_record"], normalized_record=nr, parse_status="VALID",
                ))
        else:
            result = parse_cdr_csv(file_bytes, {}, str(ev.case_id), str(ev.id), ev.original_filename, ev.sha256_hash)
            for rec in result["records"]:
                nr = rec["normalized_record"]
                db.add(ParsedRecord(
                    case_id=str(ev.case_id), evidence_id=str(ev.id), record_type="CDR",
                    source_row_number=rec["source_row_number"],
                    raw_record=rec["raw_record"], normalized_record=nr, parse_status="VALID",
                ))

        db.commit()
        ev.parsing_status = "COMPLETED"
        db.commit()
        print(f"  [+] parsed {ev.original_filename}: {result['valid_rows']} valid, {result['invalid_rows']} invalid")


def main():
    print("\n=== SPYDER-DETECT Seed Script ===\n")
    db = get_session()

    print("[1] Seeding users...")
    users = seed_users(db)
    admin = next(u for u in users if u.role == "ADMIN")
    investigator = next(u for u in users if u.role == "INVESTIGATOR")

    print("\n[2] Seeding case...")
    case = seed_case(db, admin, investigator)

    print("\n[3] Seeding evidence...")
    evidence_items = seed_evidence(db, case, investigator)

    print("\n[4] Parsing evidence...")
    parse_evidence(db, evidence_items, str(case.id))

    db.close()
    print("\n=== Seed complete ===\n")


if __name__ == "__main__":
    main()
