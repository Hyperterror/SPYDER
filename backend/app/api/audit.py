from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.case import Case, CaseMember
from app.models.audit import AuditEvent, CaseNote
from app.services.audit_svc import create_audit_event

router = APIRouter(prefix="/api/v1/cases", tags=["audit"])


def _require_case_access(case_id: str, user, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role not in ("ADMIN", "SUPERVISOR"):
        member = db.query(CaseMember).filter(
            CaseMember.case_id == case_id, CaseMember.user_id == user.id
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    return case


@router.get("/{case_id}/audit")
def get_audit_log(
    case_id: str,
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)
    q = db.query(AuditEvent).filter(AuditEvent.case_id == case_id)
    if event_type:
        q = q.filter(AuditEvent.event_type == event_type.upper())
    total = q.count()
    events = q.order_by(AuditEvent.event_timestamp.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "event_timestamp": e.event_timestamp.isoformat(),
                "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
                "evidence_id": str(e.evidence_id) if e.evidence_id else None,
                "event_metadata": e.event_metadata,
                "event_hash": e.event_hash,
                "previous_event_hash": e.previous_event_hash,
            }
            for e in events
        ],
    }


class CreateNoteRequest(BaseModel):
    note_text: str
    evidence_id: Optional[str] = None
    graph_reference: Optional[dict] = None  # {node_id, edge_id, type}


@router.get("/{case_id}/notes")
def get_notes(
    case_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)
    q = db.query(CaseNote).filter(CaseNote.case_id == case_id)
    total = q.count()
    notes = q.order_by(CaseNote.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "notes": [
            {
                "id": str(n.id),
                "note_text": n.note_text,
                "evidence_id": str(n.evidence_id) if n.evidence_id else None,
                "graph_reference": n.graph_reference,
                "created_by": str(n.created_by) if n.created_by else None,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ],
    }


@router.post("/{case_id}/notes", status_code=201)
def create_note(
    case_id: str, body: CreateNoteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)
    note = CaseNote(
        case_id=case_id,
        evidence_id=body.evidence_id,
        graph_reference=body.graph_reference,
        note_text=body.note_text,
        created_by=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    create_audit_event(
        db=db, event_type="NOTE_ADDED", case_id=case_id,
        evidence_id=body.evidence_id, actor_user_id=str(current_user.id),
        metadata={"note_id": str(note.id), "graph_reference": body.graph_reference},
    )
    return {"id": str(note.id), "note_text": note.note_text, "created_at": note.created_at.isoformat()}
