"""
FastAPI Router for Intelligence Integration Layer.
Exposes investigator-facing potential-association leads, detail views,
concrete provenance records, and cross-case summaries.
"""

from typing import List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.intelligence.leads import LeadRepository
from app.intelligence.models import (
    CrossCaseResponse,
    InvestigationLead,
    LeadResponse,
    StructuredEvidenceRecord,
)
from app.intelligence.priority_engine import InvestigationPriorityEngine
from app.intelligence.priority_models import (
    PersonEvidenceResponse,
    PersonInvestigationPriority,
    PriorityListResponse,
)
from app.models.case import Case, CaseMember
from app.models.user import User

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


def _get_user_allowed_cases(current_user: User, db: Session) -> Optional[Set[str]]:
    """
    Returns the set of case codes/IDs the user is authorized to access.
    ADMIN and SUPERVISOR roles have global clearance (returns None).
    """
    if current_user.role in ("ADMIN", "SUPERVISOR"):
        return None  # Global access

    # Query cases where user is an active member
    member_cases = (
        db.query(Case.case_code, Case.id)
        .join(CaseMember, CaseMember.case_id == Case.id)
        .filter(CaseMember.user_id == current_user.id)
        .all()
    )
    allowed: Set[str] = set()
    for code, cid in member_cases:
        if code:
            allowed.add(str(code))
        if cid:
            allowed.add(str(cid))
    return allowed


@router.get("/leads", response_model=LeadResponse)
def get_leads(
    case_id: Optional[str] = Query(None, description="Filter leads by specific case dossier"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum prediction score threshold"),
    priority: Optional[str] = Query(None, description="Filter by priority tier (HIGH, REVIEW, LOW)"),
    is_cross_case: Optional[bool] = Query(None, description="Filter for cross-case leads only"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of leads to return"),
    offset: int = Query(0, ge=0, description="Pagination offset index"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve paginated candidate association leads.
    Enforces role-based case clearance and non-prejudicial terminology.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)

    # If specific case_id requested, enforce case-level access immediately
    if case_id and allowed_cases is not None:
        if case_id not in allowed_cases:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to case dossier: {case_id}",
            )

    repo = LeadRepository.get_instance()
    total, leads = repo.get_leads(
        case_id=case_id,
        min_confidence=min_confidence,
        priority=priority,
        is_cross_case=is_cross_case,
        limit=limit,
        offset=offset,
        user_allowed_cases=allowed_cases,
    )

    return LeadResponse(
        total=total,
        limit=limit,
        offset=offset,
        leads=leads,
    )


@router.get("/leads/{lead_id}", response_model=InvestigationLead)
def get_lead_by_id(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve full details for a single candidate association lead by ID.
    Enforces case authorization clearance.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    lead = repo.get_lead_by_id(lead_id, user_allowed_cases=allowed_cases)

    if not lead:
        # Also verify if the lead exists at all to distinguish 404 from 403
        raw_lead = repo.get_lead_by_id(lead_id, user_allowed_cases=None)
        if raw_lead and allowed_cases is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to one or more cases involved in this lead.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation lead '{lead_id}' not found.",
        )

    return lead


@router.get("/leads/{lead_id}/evidence", response_model=List[StructuredEvidenceRecord])
def get_lead_evidence(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve concrete supporting provenance records for a lead.
    All records map strictly to real observable evidentiary items.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    evidence_records = repo.get_lead_evidence(lead_id, user_allowed_cases=allowed_cases)

    if evidence_records is None:
        raw_lead = repo.get_lead_by_id(lead_id, user_allowed_cases=None)
        if raw_lead and allowed_cases is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to one or more cases involved in this lead.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation lead '{lead_id}' not found.",
        )

    return evidence_records


@router.get("/cross-case", response_model=CrossCaseResponse)
def get_cross_case_leads(
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence score threshold"),
    priority: Optional[str] = Query(None, description="Filter by priority tier"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of cross-case leads"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve candidate associations linking entities across distinct case dossiers.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    total, cross_leads = repo.get_cross_case_leads(
        min_confidence=min_confidence,
        priority=priority,
        limit=limit,
        offset=offset,
        user_allowed_cases=allowed_cases,
    )

    return CrossCaseResponse(
        total=total,
        cross_case_leads=cross_leads,
    )


@router.get("/priorities", response_model=PriorityListResponse)
def get_priorities(
    case_id: Optional[str] = Query(None, description="Filter priorities by specific case dossier"),
    priority: Optional[str] = Query(None, description="Filter by priority tier (HIGH, MEDIUM, LOW)"),
    min_score: Optional[float] = Query(None, ge=0.0, le=100.0, description="Minimum priority score threshold"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of entities to return"),
    offset: int = Query(0, ge=0, description="Pagination offset index"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve ranked Investigation Priorities for PERSON entities.
    Enforces role-based case clearance, data isolation, and strictly non-prejudicial terminology.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)

    # If specific case_id requested, enforce case-level access immediately
    if case_id and allowed_cases is not None:
        if case_id not in allowed_cases:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to case dossier: {case_id}",
            )

    engine = InvestigationPriorityEngine.get_instance()
    return engine.get_priorities(
        case_id=case_id,
        priority=priority,
        min_score=min_score,
        limit=limit,
        offset=offset,
        user_allowed_cases=allowed_cases,
    )


@router.get("/priorities/{person_id}", response_model=PersonInvestigationPriority)
def get_priority_by_id(
    person_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve detailed Investigation Priority breakdown for a specific person.
    Enforces RBAC case authorization and data isolation.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    engine = InvestigationPriorityEngine.get_instance()
    priority_obj, exists = engine.get_priority_by_id(person_id, user_allowed_cases=allowed_cases)

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person entity '{person_id}' not found in knowledge graph.",
        )
    if priority_obj is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to cases associated with this person entity.",
        )

    return priority_obj


@router.get("/priorities/{person_id}/evidence", response_model=PersonEvidenceResponse)
def get_person_evidence(
    person_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve concrete supporting provenance records for a person entity.
    All records map strictly to real observable graph edges and evidentiary tables.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    engine = InvestigationPriorityEngine.get_instance()
    evidence_resp, exists = engine.get_person_evidence(person_id, user_allowed_cases=allowed_cases)

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person entity '{person_id}' not found in knowledge graph.",
        )
    if evidence_resp is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to cases associated with this person entity.",
        )

    return evidence_resp

