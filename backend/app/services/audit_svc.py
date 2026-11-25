import hashlib
import hmac
import json
import threading
import uuid
import zlib
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.audit import AuditEvent


# In-process serialization lock for SQLite / single-process fallback.
# PostgreSQL deployments also acquire a transaction-scoped advisory lock per chain key.
_CHAIN_LOCKS: dict[str, threading.Lock] = {}
_CHAIN_LOCKS_GUARD = threading.Lock()


def _get_chain_lock(chain_key: str) -> threading.Lock:
    with _CHAIN_LOCKS_GUARD:
        lock = _CHAIN_LOCKS.get(chain_key)
        if lock is None:
            lock = threading.Lock()
            _CHAIN_LOCKS[chain_key] = lock
        return lock


def _canonical_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _chain_hash(
    previous_hash: Optional[str],
    event_id: str,
    case_id: Optional[str],
    evidence_id: Optional[str],
    actor_user_id: Optional[str],
    event_type: str,
    event_timestamp: str,
    metadata: dict,
) -> str:
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


def _sign_checkpoint(event_hash: str) -> Optional[str]:
    """Optional HMAC-SHA256 checkpoint signature when AUDIT_SIGNING_KEY is configured."""
    key = (settings.AUDIT_SIGNING_KEY or "").strip()
    if not key:
        return None
    return hmac.new(key.encode("utf-8"), event_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def _acquire_pg_chain_lock(db: Session, chain_key: str) -> None:
    try:
        bind = db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            lock_id = zlib.crc32(chain_key.encode("utf-8")) & 0x7FFFFFFF
            db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})
    except Exception:
        pass


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
    """
    Append a concurrency-safe, chain-hashed audit event to the audit log.

    Note: A hash chain stored in a mutable relational database provides tamper-evidence,
    not absolute immutability; pair with AUDIT_SIGNING_KEY checkpoints and external log shipping
    in production deployments.
    """
    if metadata is None:
        metadata = {}

    case_id_str = str(case_id) if case_id else None
    evidence_id_str = str(evidence_id) if evidence_id else None
    actor_id_str = str(actor_user_id) if actor_user_id else None
    chain_key = case_id_str or "GLOBAL"

    case_uuid = uuid.UUID(case_id_str) if case_id_str else None
    ev_uuid = uuid.UUID(evidence_id_str) if evidence_id_str else None
    actor_uuid = uuid.UUID(actor_id_str) if actor_id_str else None

    lock = _get_chain_lock(chain_key)
    with lock:
        _acquire_pg_chain_lock(db, chain_key)

        query = db.query(AuditEvent)
        if case_uuid is not None:
            query = query.filter(AuditEvent.case_id == case_uuid)
        else:
            query = query.filter(AuditEvent.case_id.is_(None))

        last_event = query.order_by(
            AuditEvent.sequence_number.desc(),
            AuditEvent.created_at.desc(),
            AuditEvent.id.desc(),
        ).first()

        previous_hash = last_event.event_hash if last_event else None
        next_seq = (last_event.sequence_number + 1) if (last_event and last_event.sequence_number is not None) else (
            (query.count() + 1)
        )

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        now_str = _canonical_ts(now)

        event_hash = _chain_hash(
            previous_hash=previous_hash,
            event_id=event_id,
            case_id=case_id_str,
            evidence_id=evidence_id_str,
            actor_user_id=actor_id_str,
            event_type=event_type,
            event_timestamp=now_str,
            metadata=metadata,
        )
        checkpoint_sig = _sign_checkpoint(event_hash)

        audit = AuditEvent(
            id=uuid.UUID(event_id),
            case_id=case_uuid,
            evidence_id=ev_uuid,
            actor_user_id=actor_uuid,
            sequence_number=next_seq,
            event_type=event_type,
            event_timestamp=now,
            event_metadata=metadata,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            checkpoint_signature=checkpoint_sig,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit


def verify_audit_chain(db: Session, case_id: Optional[str] = None) -> dict:
    """
    Recomputes canonical hashes sequentially across the chain for a case (or GLOBAL chain).
    Detects broken links, modified payloads/timestamps, or invalid checkpoint signatures.
    """
    query = db.query(AuditEvent)
    if case_id is not None:
        case_uuid = uuid.UUID(str(case_id))
        query = query.filter(AuditEvent.case_id == case_uuid)
    else:
        query = query.filter(AuditEvent.case_id.is_(None))

    events = query.order_by(
        AuditEvent.sequence_number.asc(),
        AuditEvent.created_at.asc(),
        AuditEvent.id.asc(),
    ).all()

    prev_hash: Optional[str] = None
    for idx, ev in enumerate(events):
        if (ev.previous_event_hash or None) != (prev_hash or None):
            return {
                "valid": False,
                "checked_events": idx + 1,
                "total_events": len(events),
                "broken_at_event_id": str(ev.id),
                "reason": "previous_event_hash mismatch",
                "tamper_evidence_note": "Database hash chain provides tamper-evidence, not absolute immutability.",
            }

        expected_hash = _chain_hash(
            previous_hash=ev.previous_event_hash,
            event_id=str(ev.id),
            case_id=str(ev.case_id) if ev.case_id else None,
            evidence_id=str(ev.evidence_id) if ev.evidence_id else None,
            actor_user_id=str(ev.actor_user_id) if ev.actor_user_id else None,
            event_type=ev.event_type,
            event_timestamp=_canonical_ts(ev.event_timestamp),
            metadata=ev.event_metadata or {},
        )
        if ev.event_hash != expected_hash:
            return {
                "valid": False,
                "checked_events": idx + 1,
                "total_events": len(events),
                "broken_at_event_id": str(ev.id),
                "reason": "event_hash mismatch (event content or timestamp altered)",
                "tamper_evidence_note": "Database hash chain provides tamper-evidence, not absolute immutability.",
            }

        if ev.checkpoint_signature and settings.AUDIT_SIGNING_KEY:
            expected_sig = _sign_checkpoint(ev.event_hash)
            if not hmac.compare_digest(ev.checkpoint_signature, expected_sig or ""):
                return {
                    "valid": False,
                    "checked_events": idx + 1,
                    "total_events": len(events),
                    "broken_at_event_id": str(ev.id),
                    "reason": "checkpoint_signature verification failed",
                    "tamper_evidence_note": "Database hash chain provides tamper-evidence, not absolute immutability.",
                }

        prev_hash = ev.event_hash

    return {
        "valid": True,
        "checked_events": len(events),
        "total_events": len(events),
        "latest_event_hash": prev_hash,
        "broken_at_event_id": None,
        "reason": None,
        "tamper_evidence_note": "Database hash chain provides tamper-evidence; external log anchoring is recommended in production.",
    }
