from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem, ParsedRecord
from app.services.audit_svc import create_audit_event
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    title: str
    case_type: str = "HUMAN_TRAFFICKING"
    description: Optional[str] = None
    status: str = "ACTIVE"


class UpdateCaseRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None


class AddMemberRequest(BaseModel):
    user_id: str
    case_role: str = "INVESTIGATOR"


def _is_case_member(case_id: str, user_id: str, db: Session) -> bool:
    return db.query(CaseMember).filter(
        CaseMember.case_id == case_id,
        CaseMember.user_id == user_id,
    ).first() is not None


def _require_case_access(case_id: str, current_user, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        if not _is_case_member(case_id, str(current_user.id), db):
            raise HTTPException(status_code=403, detail="Access denied to this case")
    return case


def _generate_case_code(db: Session) -> str:
    count = db.query(func.count(Case.id)).scalar() or 0
    return f"HT-{datetime.now(timezone.utc).year}-{str(count + 1).zfill(3)}"


@router.get("")
def list_cases(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.role in ("ADMIN", "SUPERVISOR"):
        cases = db.query(Case).order_by(Case.updated_at.desc()).all()
    else:
        memberships = db.query(CaseMember.case_id).filter(
            CaseMember.user_id == current_user.id
        ).subquery()
        cases = db.query(Case).filter(Case.id.in_(memberships)).order_by(Case.updated_at.desc()).all()

    return [_case_to_dict(c) for c in cases]


@router.post("", status_code=201)
def create_case(body: CreateCaseRequest, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR", "INVESTIGATOR"):
        raise HTTPException(status_code=403, detail="Not authorized to create cases")

    case = Case(
        id=uuid.uuid4(),
        case_code=_generate_case_code(db),
        title=body.title,
        case_type=body.case_type,
        description=body.description,
        status=body.status,
        created_by=current_user.id,
    )
    db.add(case)
    db.flush()

    # Auto-add creator as CASE_OWNER
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
    case = _require_case_access(case_id, current_user, db)
    return _case_to_dict(case)


@router.patch("/{case_id}")
def update_case(case_id: str, body: UpdateCaseRequest, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    case = _require_case_access(case_id, current_user, db)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        member = db.query(CaseMember).filter(
            CaseMember.case_id == case_id, CaseMember.user_id == current_user.id,
            CaseMember.case_role.in_(["CASE_OWNER", "INVESTIGATOR"]),
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Only case owners/investigators can edit")

    changed = {}
    if body.title is not None:
        case.title = body.title; changed["title"] = body.title
    if body.description is not None:
        case.description = body.description; changed["description"] = body.description
    if body.status is not None:
        case.status = body.status; changed["status"] = body.status
    if body.case_type is not None:
        case.case_type = body.case_type; changed["case_type"] = body.case_type

    case.updated_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_event(db=db, event_type="CASE_UPDATED", case_id=case_id,
                       actor_user_id=str(current_user.id), metadata=changed)
    return _case_to_dict(case)


@router.post("/{case_id}/members", status_code=201)
def add_member(case_id: str, body: AddMemberRequest, db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Only supervisors/admins can assign members")
    _require_case_access(case_id, current_user, db)

    existing = db.query(CaseMember).filter(
        CaseMember.case_id == case_id, CaseMember.user_id == body.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this case")

    member = CaseMember(case_id=case_id, user_id=body.user_id,
                        case_role=body.case_role, assigned_by=current_user.id)
    db.add(member)
    db.commit()

    create_audit_event(db=db, event_type="CASE_MEMBER_ADDED", case_id=case_id,
                       actor_user_id=str(current_user.id),
                       metadata={"added_user_id": body.user_id, "case_role": body.case_role})
    return {"message": "Member added", "case_id": case_id, "user_id": body.user_id}


@router.delete("/{case_id}/members/{user_id}")
def remove_member(case_id: str, user_id: str, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        raise HTTPException(status_code=403, detail="Only supervisors/admins can remove members")

    member = db.query(CaseMember).filter(
        CaseMember.case_id == case_id, CaseMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()

    create_audit_event(db=db, event_type="CASE_MEMBER_REMOVED", case_id=case_id,
                       actor_user_id=str(current_user.id), metadata={"removed_user_id": user_id})
    return {"message": "Member removed"}


@router.get("/{case_id}/summary")
def case_summary(case_id: str, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    case = _require_case_access(case_id, current_user, db)
    evidence_count = db.query(func.count(EvidenceItem.id)).filter(
        EvidenceItem.case_id == case_id).scalar()
    parsed_count = db.query(func.count(ParsedRecord.id)).filter(
        ParsedRecord.case_id == case_id, ParsedRecord.parse_status == "VALID").scalar()
    member_count = db.query(func.count(CaseMember.id)).filter(
        CaseMember.case_id == case_id).scalar()
    return {
        **_case_to_dict(case),
        "evidence_count": evidence_count,
        "parsed_event_count": parsed_count,
        "member_count": member_count,
    }


def _case_to_dict(case: Case) -> dict:
    return {
        "id": str(case.id),
        "case_code": case.case_code,
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
