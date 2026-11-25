from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.authz import require_case_access, get_authorized_case_scope
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem, ParsedRecord
from app.services.audit_svc import create_audit_event
from fastapi import Query
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    title: str
    case_type: str = "HUMAN_TRAFFICKING"
    description: Optional[str] = None
    status: str = "ACTIVE"
    external_case_ref: Optional[str] = None


class UpdateCaseRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    external_case_ref: Optional[str] = None


class AddMemberRequest(BaseModel):
    user_id: str
    case_role: str = "INVESTIGATOR"


def _generate_case_code(db: Session) -> str:
    count = db.query(func.count(Case.id)).scalar() or 0
    return f"HT-{datetime.now(timezone.utc).year}-{str(count + 1).zfill(3)}"


@router.get("")
def list_cases(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    scope = get_authorized_case_scope(current_user, db)
    if scope.is_unrestricted:
        cases = db.query(Case).order_by(Case.updated_at.desc()).all()
    else:
        allowed_uuids = [uuid.UUID(cid) for cid in (scope.allowed_case_ids or set())]
        if not allowed_uuids:
            return []
        cases = db.query(Case).filter(Case.id.in_(allowed_uuids)).order_by(Case.updated_at.desc()).all()

    return [_case_to_dict(c) for c in cases]


@router.post("", status_code=201)
def create_case(body: CreateCaseRequest, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR", "INVESTIGATOR"):
        raise HTTPException(status_code=403, detail="Not authorized to create cases")

    case = Case(
        id=uuid.uuid4(),
        case_code=_generate_case_code(db),
        external_case_ref=body.external_case_ref,
        title=body.title,
        case_type=body.case_type,
        description=body.description,
        status=body.status,
        organization_id=getattr(current_user, "organization_id", None),
        created_by=current_user.id,
    )
    db.add(case)
    db.flush()

    member = CaseMember(
        case_id=case.id,
        user_id=current_user.id,
        case_role="CASE_OWNER",
        assigned_by=current_user.id,
    )
    db.add(member)
    db.commit()
    db.refresh(case)

    create_audit_event(
        db=db, event_type="CASE_CREATED", case_id=str(case.id),
        actor_user_id=str(current_user.id),
        metadata={"case_code": case.case_code, "title": case.title},
    )
    return _case_to_dict(case)


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    case = require_case_access(case_id, current_user, db)
    return _case_to_dict(case)


@router.patch("/{case_id}")
def update_case(case_id: str, body: UpdateCaseRequest, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    case = require_case_access(
        case_id, current_user, db, required_case_roles=["CASE_OWNER", "INVESTIGATOR", "LEAD_INVESTIGATOR"]
    )

    changed = {}
    if body.title is not None:
        case.title = body.title; changed["title"] = body.title
    if body.description is not None:
        case.description = body.description; changed["description"] = body.description
    if body.status is not None:
        case.status = body.status; changed["status"] = body.status
    if body.case_type is not None:
        case.case_type = body.case_type; changed["case_type"] = body.case_type
    if body.external_case_ref is not None:
        case.external_case_ref = body.external_case_ref; changed["external_case_ref"] = body.external_case_ref

    case.updated_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_event(db=db, event_type="CASE_UPDATED", case_id=str(case.id),
                       actor_user_id=str(current_user.id), metadata=changed)
    return _case_to_dict(case)


@router.post("/{case_id}/members", status_code=201)
def add_member(case_id: str, body: AddMemberRequest, db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Only supervisors/admins can assign members")
    case = require_case_access(case_id, current_user, db)

    target_user_id = uuid.UUID(str(body.user_id))
    existing = db.query(CaseMember).filter(
        CaseMember.case_id == case.id, CaseMember.user_id == target_user_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this case")

    member = CaseMember(case_id=case.id, user_id=target_user_id,
                        case_role=body.case_role, assigned_by=current_user.id)
    db.add(member)
    db.commit()

    create_audit_event(db=db, event_type="CASE_MEMBER_ADDED", case_id=str(case.id),
                       actor_user_id=str(current_user.id),
                       metadata={"added_user_id": body.user_id, "case_role": body.case_role})
    return {"message": "Member added", "case_id": str(case.id), "user_id": body.user_id}


@router.delete("/{case_id}/members/{user_id}")
def remove_member(case_id: str, user_id: str, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Only supervisors/admins can remove members")
    case = require_case_access(case_id, current_user, db)

    member = db.query(CaseMember).filter(
        CaseMember.case_id == case.id, CaseMember.user_id == uuid.UUID(str(user_id))
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()

    create_audit_event(db=db, event_type="CASE_MEMBER_REMOVED", case_id=str(case.id),
                       actor_user_id=str(current_user.id), metadata={"removed_user_id": user_id})
    return {"message": "Member removed"}


@router.get("/{case_id}/summary")
def case_summary(case_id: str, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    case = require_case_access(case_id, current_user, db)
    evidence_count = db.query(func.count(EvidenceItem.id)).filter(
        EvidenceItem.case_id == case.id).scalar()
    parsed_count = db.query(func.count(ParsedRecord.id)).filter(
        ParsedRecord.case_id == case.id, ParsedRecord.parse_status == "VALID").scalar()
    member_count = db.query(func.count(CaseMember.id)).filter(
        CaseMember.case_id == case.id).scalar()
    return {
        **_case_to_dict(case),
        "evidence_count": evidence_count,
        "parsed_event_count": parsed_count,
        "member_count": member_count,
    }


@router.get("/{case_id}/timeline")
def case_timeline(
    case_id: str,
    entity: Optional[str] = Query(None),
    modality: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Chronological timeline of observable events across active evidence for a case."""
    case = require_case_access(case_id, current_user, db)
    q = (
        db.query(ParsedRecord, EvidenceItem)
        .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
        .filter(
            ParsedRecord.case_id == case.id,
            ParsedRecord.parse_status == "VALID",
            EvidenceItem.lifecycle_status == "ACTIVE",
        )
    )
    if modality:
        q = q.filter(ParsedRecord.record_type == modality.strip().upper())

    events = []
    for rec, ev in q.all():
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        ts = (
            nr.get("start_time_utc")
            or nr.get("timestamp_utc")
            or nr.get("departure_time_utc")
            or ev.uploaded_at.isoformat()
        )
        participants = [
            str(nr.get(k))
            for k in (
                "calling_number", "called_number", "sender_identifier", "receiver_identifier",
                "person_id", "owner_person_id", "device_id", "vehicle_number", "sender_id", "recipient_id",
            )
            if nr.get(k)
        ]
        if entity and not any(entity.lower() in p.lower() for p in participants):
            continue
        events.append({
            "id": str(rec.id),
            "timestamp": ts,
            "modality": rec.record_type,
            "participants": participants,
            "summary": nr,
            "provenance": {
                "case_id": str(case.id),
                "case_code": case.case_code,
                "evidence_id": str(ev.id),
                "evidence_code": ev.evidence_code,
                "source_file": ev.sanitized_filename,
                "source_row": rec.source_row_number,
                "sha256_hash": ev.sha256_hash,
            },
        })

    events.sort(key=lambda x: str(x["timestamp"]), reverse=True)
    return {"case_id": str(case.id), "case_code": case.case_code, "total": len(events), "events": events[:limit]}


def _case_to_dict(case: Case) -> dict:
    return {
        "id": str(case.id),
        "case_code": case.case_code,
        "external_case_ref": getattr(case, "external_case_ref", None),
        "organization_id": str(case.organization_id) if getattr(case, "organization_id", None) else None,
        "title": case.title,
        "case_type": case.case_type,
        "description": case.description,
        "status": case.status,
        "created_by": str(case.created_by) if case.created_by else None,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "members": [
            {"user_id": str(m.user_id), "case_role": m.case_role}
            for m in (case.members or [])
        ],
    }
