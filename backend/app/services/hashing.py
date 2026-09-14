import hashlib
import io
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.evidence import EvidenceItem
from app.services.storage import get_storage
from app.services.audit_svc import create_audit_event
import uuid


def calculate_sha256(file_bytes: bytes) -> str:
    """Compute SHA-256 of raw bytes. Used during upload before storage."""
    return hashlib.sha256(file_bytes).hexdigest()


def verify_integrity(
    evidence: EvidenceItem,
    db: Session,
    actor_user_id: str | None = None,
) -> dict:
    """
    Re-download original file from MinIO, recompute SHA-256, compare.
    Returns dict with status and both hashes.
    """
    storage = get_storage()
    try:
        file_bytes = storage.download(evidence.object_storage_bucket, evidence.object_storage_key)
        computed_hash = calculate_sha256(file_bytes)
        matches = computed_hash == evidence.sha256_hash

        if matches:
            new_status = "VERIFIED"
        else:
            new_status = "MISMATCH"

        evidence.integrity_status = new_status
        evidence.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Record audit event
        create_audit_event(
            db=db,
            case_id=str(evidence.case_id),
            evidence_id=str(evidence.id),
            actor_user_id=actor_user_id,
            event_type="EVIDENCE_HASH_VERIFIED",
            metadata={
                "ingestion_hash": evidence.sha256_hash,
                "computed_hash": computed_hash,
                "result": new_status,
            },
        )

        return {
            "status": new_status,
            "ingestion_hash": evidence.sha256_hash,
            "computed_hash": computed_hash,
            "match": matches,
        }
    except Exception as e:
        evidence.integrity_status = "VERIFICATION_FAILED"
        db.commit()
        create_audit_event(
            db=db,
            case_id=str(evidence.case_id),
            evidence_id=str(evidence.id),
            actor_user_id=actor_user_id,
            event_type="EVIDENCE_HASH_VERIFIED",
            metadata={"result": "VERIFICATION_FAILED", "error": str(e)},
        )
        return {
            "status": "VERIFICATION_FAILED",
            "ingestion_hash": evidence.sha256_hash,
            "computed_hash": None,
            "match": False,
            "error": str(e),
        }
