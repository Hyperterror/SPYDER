import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.audit import AuditEvent


def _chain_hash(previous_hash: Optional[str], event_id: str, case_id: Optional[str],
                evidence_id: Optional[str], actor_user_id: Optional[str],
                event_type: str, event_timestamp: str, metadata: dict) -> str:
    """Produce deterministic SHA-256 chain hash for an audit event."""
    canonical = json.dumps({
        "previous_event_hash": previous_hash or "",
        "event_id": event_id,
        "case_id": case_id or "",
        "evidence_id": evidence_id or "",
        "actor_user_id": actor_user_id or "",
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "event_metadata": metadata,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_audit_event(
    db: Session,
    event_type: str,
    case_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditEvent:
    """Append a chain-hashed audit event to the audit log."""
    if metadata is None:
        metadata = {}

    # Fetch the last audit event for this case to chain hashes
    query = db.query(AuditEvent).order_by(AuditEvent.created_at.desc())
    if case_id:
        query = query.filter(AuditEvent.case_id == case_id)
    last_event = query.first()
    previous_hash = last_event.event_hash if last_event else None

    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    event_hash = _chain_hash(
        previous_hash=previous_hash,
        event_id=event_id,
        case_id=case_id,
        evidence_id=evidence_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        event_timestamp=now_str,
        metadata=metadata,
    )

    audit = AuditEvent(
        id=event_id,
        case_id=case_id,
        evidence_id=evidence_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        event_timestamp=now,
        event_metadata=metadata,
        previous_event_hash=previous_hash,
        event_hash=event_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit
