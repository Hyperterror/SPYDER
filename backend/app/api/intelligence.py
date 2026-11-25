"""
FastAPI Router for Intelligence Integration Layer (Milestones 1 & 3).
Exposes investigator-facing potential-association leads, lead review lifecycle,
identity hypotheses & human review, centralized entity profiles, consistency
persistence & claim editing, unified decision history, and model registry provenance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authz import all_cases_authorized, get_authorized_case_scope, resolve_case_by_identifier
from app.core.database import get_db
from app.core.security import get_current_user
from app.intelligence.claim_models import (
    AnalyzeStatementRequest,
    AnalyzeStatementResponse,
    ConsistencyAnalysisResult,
    ConsistencyListResponse,
    ConsistencyStatus,
    StructuredClaim,
)
from app.intelligence.consistency_engine import ConsistencyEngine
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
from app.models.audit import CaseNote
from app.models.case import Case
from app.models.evidence import EvidenceItem, ParsedRecord
from app.models.intelligence import (
    ConsistencyAnalysisRecord,
    IdentityHypothesis,
    IdentityHypothesisDecisionLog,
    IntelligenceLeadRecord,
    LeadDecisionLog,
    ModelArtifactRegistry,
)
from app.models.user import User
from app.services.audit_svc import create_audit_event

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])

VALID_LEAD_STATUSES = {
    "NEW",
    "UNDER_REVIEW",
    "REQUIRES_MORE_EVIDENCE",
    "ACCEPTED_FOR_FURTHER_INVESTIGATION",
    "REJECTED",
    "CLOSED",
}

VALID_HYPOTHESIS_STATUSES = {
    "CANDIDATE",
    "PENDING_REVIEW",
    "ACCEPTED",
    "REJECTED",
    "DISPUTED",
    "SUPERSEDED",
}


class ReviewLeadRequest(BaseModel):
    status: str = Field(..., description="NEW | UNDER_REVIEW | REQUIRES_MORE_EVIDENCE | ACCEPTED_FOR_FURTHER_INVESTIGATION | REJECTED | CLOSED")
    rationale: str = Field(..., min_length=3)


class ReviewHypothesisRequest(BaseModel):
    status: str = Field(..., description="ACCEPTED | REJECTED | DISPUTED | PENDING_REVIEW")
    rationale: str = Field(..., min_length=3)


class UpdateClaimRequest(BaseModel):
    predicate: Optional[str] = None
    object_entity_id: Optional[str] = None
    location_id: Optional[str] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    negated: Optional[bool] = None
    reviewer_comment: Optional[str] = None


class ReviewConsistencyRequest(BaseModel):
    comment: str = Field(..., min_length=2)


def _get_user_allowed_cases(current_user: User, db: Session) -> Optional[Set[str]]:
    scope = get_authorized_case_scope(current_user, db)
    return scope.allowed_canonical_refs


def _persist_consistency_result(res: ConsistencyAnalysisResult, statement_text: str, db: Session) -> None:
    case_obj = resolve_case_by_identifier(res.claim.case_id, db)
    existing = db.query(ConsistencyAnalysisRecord).filter(
        ConsistencyAnalysisRecord.result_id == res.result_id
    ).first()
    payload = dict(
        case_id=case_obj.id if case_obj else None,
        case_ref=res.claim.case_id,
        subject_entity_id=res.claim.subject_entity_id,
        statement_text=statement_text,
        source_document_id=res.claim.source_document_id,
        current_claim=res.claim.model_dump(),
        status=res.status.value,
        confidence_breakdown=res.confidence.model_dump(),
        matched_evidence=[m.model_dump() for m in res.matched_evidence],
        conflicting_evidence=[c.model_dump() for c in res.conflicting_evidence],
        caveats=res.caveats,
        explanation=res.explanation,
        recommended_action=res.recommended_action,
    )
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
    else:
        db.add(ConsistencyAnalysisRecord(
            id=uuid.uuid4(),
            result_id=res.result_id,
            original_claim=res.claim.model_dump(),
            **payload,
        ))
    db.commit()


# =============================================================================
# Leads & Cross-Case Intelligence
# =============================================================================

@router.get("/leads", response_model=LeadResponse)
def get_leads(
    case_id: Optional[str] = Query(None, description="Filter leads by specific case dossier"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum prediction score threshold"),
    priority: Optional[str] = Query(None, description="Filter by priority tier (HIGH, REVIEW, LOW)"),
    is_cross_case: Optional[bool] = Query(None, description="Filter for cross-case leads only"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by review status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of leads to return"),
    offset: int = Query(0, ge=0, description="Pagination offset index"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)

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
        status_filter=status_filter,
        limit=limit,
        offset=offset,
        user_allowed_cases=allowed_cases,
        db=db,
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
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    lead = repo.get_lead_by_id(lead_id, user_allowed_cases=allowed_cases, db=db)

    if not lead:
        raw_lead = repo.get_lead_by_id(lead_id, user_allowed_cases=None, db=db)
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
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    evidence_records = repo.get_lead_evidence(lead_id, user_allowed_cases=allowed_cases, db=db)

    if evidence_records is None:
        raw_lead = repo.get_lead_by_id(lead_id, user_allowed_cases=None, db=db)
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


@router.post("/leads/{lead_id}/review")
def review_lead(
    lead_id: str,
    body: ReviewLeadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in ("ADMIN", "SUPERVISOR", "INVESTIGATOR", "ANALYST"):
        raise HTTPException(status_code=403, detail="Not authorized to review leads")

    new_status = body.status.strip().upper()
    if new_status not in VALID_LEAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid lead status '{new_status}'")

    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    lead = repo.get_lead_by_id(lead_id, user_allowed_cases=allowed_cases, db=db)
    if not lead:
        raw_lead = repo.get_lead_by_id(lead_id, user_allowed_cases=None, db=db)
        if raw_lead and allowed_cases is not None:
            raise HTTPException(status_code=403, detail="Access denied to one or more cases involved in this lead.")
        raise HTTPException(status_code=404, detail=f"Investigation lead '{lead_id}' not found.")

    now = datetime.now(timezone.utc)
    rec = db.query(IntelligenceLeadRecord).filter(IntelligenceLeadRecord.lead_code == lead_id).first()
    if not rec:
        rec = IntelligenceLeadRecord(
            id=uuid.uuid4(),
            lead_code=lead.lead_id,
            source_entity=lead.source_entity,
            target_entity=lead.target_entity,
            source_case_ids=lead.source_case_ids,
            target_case_ids=lead.target_case_ids,
            is_cross_case=lead.is_cross_case,
            candidate_relationship_type=lead.prediction_type.value,
            model_version=lead.model_version,
            prediction_score=lead.confidence,
            priority_tier=lead.priority.value,
            evidence_strength=lead.evidence_strength.value,
            explanation=lead.explanation,
            supporting_modalities=lead.supporting_modalities,
            common_intermediates=lead.common_intermediates,
            caveats=lead.caveats,
            supporting_records=[r.model_dump() for r in lead.supporting_records],
            conflicting_records=[r.model_dump() for r in lead.conflicting_records],
            status="NEW",
        )
        db.add(rec)
        db.flush()

    prev_status = rec.status
    rec.status = new_status
    rec.reviewed_by = current_user.id
    rec.reviewed_at = now
    rec.decision_rationale = body.rationale
    rec.updated_at = now

    db.add(LeadDecisionLog(
        id=uuid.uuid4(),
        lead_id=rec.id,
        previous_status=prev_status,
        new_status=new_status,
        reviewer_id=current_user.id,
        rationale=body.rationale,
    ))
    db.commit()

    first_case_obj = resolve_case_by_identifier((lead.source_case_ids or lead.target_case_ids or [None])[0], db)
    create_audit_event(
        db=db,
        event_type="INTELLIGENCE_LEAD_REVIEWED",
        case_id=str(first_case_obj.id) if first_case_obj else None,
        actor_user_id=str(current_user.id),
        metadata={
            "lead_id": lead_id,
            "previous_status": prev_status,
            "new_status": new_status,
            "rationale": body.rationale,
        },
    )
    return {
        "lead_id": lead_id,
        "previous_status": prev_status,
        "status": new_status,
        "reviewed_by": str(current_user.id),
        "reviewed_at": now.isoformat(),
        "rationale": body.rationale,
    }


@router.get("/cross-case", response_model=CrossCaseResponse)
def get_cross_case_leads(
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    repo = LeadRepository.get_instance()
    total, cross_leads = repo.get_cross_case_leads(
        min_confidence=min_confidence,
        priority=priority,
        limit=limit,
        offset=offset,
        user_allowed_cases=allowed_cases,
        db=db,
    )
    return CrossCaseResponse(total=total, cross_case_leads=cross_leads)


# =============================================================================
# Entity Resolution Hypotheses & Investigator Review
# =============================================================================

def _hypothesis_to_dict(h: IdentityHypothesis, include_profiles: bool = False) -> dict:
    d = {
        "id": str(h.id),
        "hypothesis_key": h.hypothesis_key,
        "person_a_ref": h.person_a_ref,
        "person_b_ref": h.person_b_ref,
        "person_a_name": h.person_a_name,
        "person_b_name": h.person_b_name,
        "case_a_id": str(h.case_a_id) if h.case_a_id else None,
        "case_b_id": str(h.case_b_id) if h.case_b_id else None,
        "case_a_ref": h.case_a_ref,
        "case_b_ref": h.case_b_ref,
        "match_probability": round(float(h.match_probability), 4),
        "confidence_tier": h.confidence_tier,
        "model_version": h.model_version,
        "supporting_evidence": h.supporting_evidence or [],
        "conflicting_evidence": h.conflicting_evidence or [],
        "blocking_reasons": h.blocking_reasons or [],
        "status": h.status,
        "reviewed_by": str(h.reviewed_by) if h.reviewed_by else None,
        "reviewed_at": h.reviewed_at.isoformat() if h.reviewed_at else None,
        "decision_rationale": h.decision_rationale,
        "created_at": h.created_at.isoformat(),
        "updated_at": h.updated_at.isoformat(),
    }
    if include_profiles:
        d["profile_a"] = h.profile_a_snapshot or {}
        d["profile_b"] = h.profile_b_snapshot or {}
        d["feature_explanation"] = h.feature_explanation or {}
        d["decisions"] = [
            {
                "id": str(dec.id),
                "previous_status": dec.previous_status,
                "new_status": dec.new_status,
                "reviewer_id": str(dec.reviewer_id) if dec.reviewer_id else None,
                "rationale": dec.rationale,
                "created_at": dec.created_at.isoformat(),
            }
            for dec in (h.decisions or [])
        ]
    return d


@router.get("/identity-hypotheses")
def list_identity_hypotheses(
    status_filter: Optional[str] = Query(None, alias="status"),
    min_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    q = db.query(IdentityHypothesis).order_by(IdentityHypothesis.match_probability.desc())
    if status_filter:
        q = q.filter(IdentityHypothesis.status == status_filter.strip().upper())
    if min_probability is not None:
        q = q.filter(IdentityHypothesis.match_probability >= min_probability)

    items = []
    for h in q.all():
        refs = [str(h.case_a_id or h.case_a_ref), str(h.case_b_id or h.case_b_ref)]
        if all_cases_authorized(refs, allowed_cases):
            items.append(_hypothesis_to_dict(h, include_profiles=False))

    total = len(items)
    return {"total": total, "limit": limit, "offset": offset, "hypotheses": items[offset : offset + limit]}


@router.get("/identity-hypotheses/{hypothesis_id}")
def get_identity_hypothesis(
    hypothesis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        hid = uuid.UUID(str(hypothesis_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Identity hypothesis not found")
    h = db.query(IdentityHypothesis).filter(IdentityHypothesis.id == hid).first()
    if not h:
        raise HTTPException(status_code=404, detail="Identity hypothesis not found")

    allowed_cases = _get_user_allowed_cases(current_user, db)
    if not all_cases_authorized([str(h.case_a_id or h.case_a_ref), str(h.case_b_id or h.case_b_ref)], allowed_cases):
        raise HTTPException(status_code=403, detail="Access denied to one or more cases in this identity hypothesis")

    return _hypothesis_to_dict(h, include_profiles=True)


@router.post("/identity-hypotheses/{hypothesis_id}/review")
def review_identity_hypothesis(
    hypothesis_id: str,
    body: ReviewHypothesisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_status = body.status.strip().upper()
    if new_status not in VALID_HYPOTHESIS_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid hypothesis status '{new_status}'")

    try:
        hid = uuid.UUID(str(hypothesis_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Identity hypothesis not found")
    h = db.query(IdentityHypothesis).filter(IdentityHypothesis.id == hid).first()
    if not h:
        raise HTTPException(status_code=404, detail="Identity hypothesis not found")

    allowed_cases = _get_user_allowed_cases(current_user, db)
    if not all_cases_authorized([str(h.case_a_id or h.case_a_ref), str(h.case_b_id or h.case_b_ref)], allowed_cases):
        raise HTTPException(status_code=403, detail="Access denied to one or more cases in this identity hypothesis")

    now = datetime.now(timezone.utc)
    prev_status = h.status
    h.status = new_status
    h.reviewed_by = current_user.id
    h.reviewed_at = now
    h.decision_rationale = body.rationale
    h.updated_at = now

    db.add(IdentityHypothesisDecisionLog(
        id=uuid.uuid4(),
        hypothesis_id=h.id,
        previous_status=prev_status,
        new_status=new_status,
        reviewer_id=current_user.id,
        rationale=body.rationale,
    ))
    db.commit()

    create_audit_event(
        db=db,
        event_type="IDENTITY_HYPOTHESIS_REVIEWED",
        case_id=str(h.case_a_id) if h.case_a_id else None,
        actor_user_id=str(current_user.id),
        metadata={
            "hypothesis_id": str(h.id),
            "person_a": h.person_a_ref,
            "person_b": h.person_b_ref,
            "previous_status": prev_status,
            "new_status": new_status,
            "rationale": body.rationale,
        },
    )
    return _hypothesis_to_dict(h, include_profiles=True)


# =============================================================================
# Centralized Authorized Entity Profile
# =============================================================================

@router.get("/entities/{entity_id}")
def get_entity_profile(
    entity_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Centralized observational profile for an entity across authorized cases only.
    Separates directly observed attributes from provisional identity hypotheses.
    """
    allowed_cases = _get_user_allowed_cases(current_user, db)
    rows = (
        db.query(ParsedRecord, EvidenceItem, Case)
        .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
        .join(Case, ParsedRecord.case_id == Case.id)
        .filter(
            ParsedRecord.parse_status == "VALID",
            EvidenceItem.lifecycle_status == "ACTIVE",
        )
        .all()
    )

    observed_records = []
    associated_cases: Dict[str, str] = {}
    identifiers: Set[str] = set()
    devices: Set[str] = set()
    phones: Set[str] = set()
    vehicles: Set[str] = set()
    locations: Set[str] = set()
    communications: List[dict] = []
    financials: List[dict] = []
    travel: List[dict] = []
    timeline: List[dict] = []

    for rec, ev, case in rows:
        cid_str = str(case.id)
        if allowed_cases is not None and cid_str not in allowed_cases and case.case_code not in allowed_cases:
            continue
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        vals = [str(v) for v in nr.values() if v is not None]
        if entity_id not in vals:
            continue

        associated_cases[cid_str] = case.case_code
        observed_records.append({
            "record_id": str(rec.id),
            "record_type": rec.record_type,
            "case_id": cid_str,
            "case_code": case.case_code,
            "evidence_id": str(ev.id),
            "evidence_code": ev.evidence_code,
            "source_file": ev.sanitized_filename,
            "source_row": rec.source_row_number,
            "normalized_record": nr,
        })
        ts = nr.get("start_time_utc") or nr.get("timestamp_utc") or nr.get("departure_time_utc") or ""
        timeline.append({"timestamp": ts, "modality": rec.record_type, "case_code": case.case_code, "detail": nr})

        if nr.get("calling_number"):
            phones.add(nr["calling_number"])
        if nr.get("called_number"):
            phones.add(nr["called_number"])
        if nr.get("phone_id"):
            phones.add(nr["phone_id"])
        if nr.get("device_id"):
            devices.add(nr["device_id"])
        if nr.get("imei"):
            devices.add(nr["imei"])
        if nr.get("vehicle_number"):
            vehicles.add(nr["vehicle_number"])
        for loc_k in ("origin", "destination", "sighting_location", "tower_id"):
            if nr.get(loc_k):
                locations.add(str(nr[loc_k]))

        if rec.record_type in ("CDR", "CHAT"):
            communications.append(nr)
        elif rec.record_type == "TRANSACTION":
            financials.append(nr)
        elif rec.record_type == "TRAVEL":
            travel.append(nr)
        if nr.get("raw_name"):
            identifiers.add(nr["raw_name"])

    # Also check offline PriorityEngine if entity exists there and user is authorized
    engine = InvestigationPriorityEngine.get_instance()
    prio_obj, prio_exists = engine.get_priority_by_id(entity_id, user_allowed_cases=allowed_cases)

    if not observed_records and prio_obj is None:
        if prio_exists:
            raise HTTPException(status_code=403, detail="Access denied to cases associated with this entity.")
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found in authorized records.")

    # Authorized identity hypotheses involving this entity
    hyps = db.query(IdentityHypothesis).filter(
        (IdentityHypothesis.person_a_ref == entity_id) | (IdentityHypothesis.person_b_ref == entity_id)
    ).all()
    authorized_hyps = [
        _hypothesis_to_dict(h, include_profiles=False)
        for h in hyps
        if all_cases_authorized([str(h.case_a_id or h.case_a_ref), str(h.case_b_id or h.case_b_ref)], allowed_cases)
    ]

    timeline.sort(key=lambda x: str(x["timestamp"]), reverse=True)
    return {
        "entity_id": entity_id,
        "identifiers": sorted(list(identifiers)),
        "associated_cases": [
            {"case_id": k, "case_code": v} for k, v in associated_cases.items()
        ],
        "phones": sorted(list(phones)),
        "devices": sorted(list(devices)),
        "vehicles": sorted(list(vehicles)),
        "locations": sorted(list(locations)),
        "communications": communications[:100],
        "financial_associations": financials[:100],
        "travel_observations": travel[:100],
        "evidence_references": observed_records[:100],
        "timeline": timeline[:100],
        "identity_hypotheses": authorized_hyps,
        "priority_summary": prio_obj.model_dump() if prio_obj else None,
        "disclaimer": "Provisional identity hypotheses are separated from directly observed attributes and require human verification.",
    }


# =============================================================================
# Investigation Priority Engine
# =============================================================================

@router.get("/priorities", response_model=PriorityListResponse)
def get_priorities(
    case_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0.0, le=100.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    if case_id and allowed_cases is not None and case_id not in allowed_cases:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied to case dossier: {case_id}")

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
    allowed_cases = _get_user_allowed_cases(current_user, db)
    engine = InvestigationPriorityEngine.get_instance()
    priority_obj, exists = engine.get_priority_by_id(person_id, user_allowed_cases=allowed_cases)

    if not exists:
        raise HTTPException(status_code=404, detail=f"Person entity '{person_id}' not found in knowledge graph.")
    if priority_obj is None:
        raise HTTPException(status_code=403, detail="Access denied to cases associated with this person entity.")
    return priority_obj


@router.get("/priorities/{person_id}/evidence", response_model=PersonEvidenceResponse)
def get_person_evidence(
    person_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    engine = InvestigationPriorityEngine.get_instance()
    evidence_resp, exists = engine.get_person_evidence(person_id, user_allowed_cases=allowed_cases)

    if not exists:
        raise HTTPException(status_code=404, detail=f"Person entity '{person_id}' not found in knowledge graph.")
    if evidence_resp is None:
        raise HTTPException(status_code=403, detail="Access denied to cases associated with this person entity.")
    return evidence_resp


# =============================================================================
# Statement-Evidence Consistency Verification (with DB Persistence & Claim Edit)
# =============================================================================

@router.post("/consistency/analyze", response_model=AnalyzeStatementResponse)
def analyze_statement(
    request: AnalyzeStatementRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    if allowed_cases is not None and request.case_id not in allowed_cases:
        raise HTTPException(status_code=403, detail=f"Access denied to case dossier: {request.case_id}")

    engine = ConsistencyEngine.get_instance()
    auth_list = list(allowed_cases) if allowed_cases is not None else None
    resp = engine.analyze_statement(request, authorized_cases=auth_list)
    for res in resp.results:
        _persist_consistency_result(res, request.statement_text, db)
    return resp


@router.post("/consistency/claims", response_model=ConsistencyAnalysisResult)
def evaluate_claim(
    claim: StructuredClaim,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    if allowed_cases is not None and claim.case_id not in allowed_cases:
        raise HTTPException(status_code=403, detail=f"Access denied to case dossier: {claim.case_id}")

    engine = ConsistencyEngine.get_instance()
    auth_list = list(allowed_cases) if allowed_cases is not None else None
    res = engine.evaluate_claim(claim, authorized_cases=auth_list)
    with engine._lock:
        engine._results_cache[res.result_id] = res
    _persist_consistency_result(res, claim.raw_text, db)
    return res


@router.patch("/consistency/{result_id}/claim")
def correct_consistency_claim(
    result_id: str,
    body: UpdateClaimRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow investigator correction of an extracted claim while preserving original extraction."""
    rec = db.query(ConsistencyAnalysisRecord).filter(ConsistencyAnalysisRecord.result_id == result_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Consistency analysis result not found")

    allowed_cases = _get_user_allowed_cases(current_user, db)
    if allowed_cases is not None and rec.case_ref not in allowed_cases:
        raise HTTPException(status_code=403, detail="Access denied to this case dossier")

    updated_claim_dict = dict(rec.current_claim)
    for field in ("predicate", "object_entity_id", "location_id", "time_start", "time_end", "negated"):
        val = getattr(body, field)
        if val is not None:
            updated_claim_dict[field] = val

    claim = StructuredClaim(**updated_claim_dict)
    engine = ConsistencyEngine.get_instance()
    auth_list = list(allowed_cases) if allowed_cases is not None else None
    new_res = engine.evaluate_claim(claim, authorized_cases=auth_list)
    with engine._lock:
        engine._results_cache[result_id] = new_res

    rec.current_claim = claim.model_dump()
    rec.status = new_res.status.value
    rec.confidence_breakdown = new_res.confidence.model_dump()
    rec.matched_evidence = [m.model_dump() for m in new_res.matched_evidence]
    rec.conflicting_evidence = [c.model_dump() for c in new_res.conflicting_evidence]
    rec.caveats = new_res.caveats
    rec.explanation = new_res.explanation
    rec.recommended_action = new_res.recommended_action
    if body.reviewer_comment:
        rec.reviewer_comment = body.reviewer_comment
    rec.reviewed_by = current_user.id
    rec.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_event(
        db=db,
        event_type="CONSISTENCY_CLAIM_CORRECTED",
        case_id=str(rec.case_id) if rec.case_id else None,
        actor_user_id=str(current_user.id),
        metadata={"result_id": result_id, "new_status": rec.status},
    )
    return {
        "result_id": result_id,
        "original_claim": rec.original_claim,
        "current_claim": rec.current_claim,
        "evaluation": new_res.model_dump(),
    }


@router.post("/consistency/{result_id}/review")
def review_consistency_result(
    result_id: str,
    body: ReviewConsistencyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rec = db.query(ConsistencyAnalysisRecord).filter(ConsistencyAnalysisRecord.result_id == result_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Consistency analysis result not found")

    allowed_cases = _get_user_allowed_cases(current_user, db)
    if allowed_cases is not None and rec.case_ref not in allowed_cases:
        raise HTTPException(status_code=403, detail="Access denied to this case dossier")

    rec.reviewer_comment = body.comment
    rec.reviewed_by = current_user.id
    rec.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_event(
        db=db,
        event_type="CONSISTENCY_REVIEWED",
        case_id=str(rec.case_id) if rec.case_id else None,
        actor_user_id=str(current_user.id),
        metadata={"result_id": result_id, "comment": body.comment},
    )
    return {"result_id": result_id, "reviewer_comment": rec.reviewer_comment, "reviewed_at": rec.reviewed_at.isoformat()}


@router.get("/consistency/{result_id}", response_model=ConsistencyAnalysisResult)
def get_consistency_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    auth_list = list(allowed_cases) if allowed_cases is not None else None
    engine = ConsistencyEngine.get_instance()
    result = engine.get_result(result_id, authorized_cases=auth_list)

    if not result:
        rec = db.query(ConsistencyAnalysisRecord).filter(ConsistencyAnalysisRecord.result_id == result_id).first()
        if rec and (allowed_cases is None or rec.case_ref in allowed_cases):
            return ConsistencyAnalysisResult(
                result_id=rec.result_id,
                claim=StructuredClaim(**rec.current_claim),
                status=ConsistencyStatus(rec.status),
                confidence=rec.confidence_breakdown,
                matched_evidence=rec.matched_evidence,
                conflicting_evidence=rec.conflicting_evidence,
                explanation=rec.explanation,
                caveats=rec.caveats,
                recommended_action=rec.recommended_action,
                evaluated_at=rec.updated_at.isoformat(),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consistency analysis result '{result_id}' not found or unauthorized.",
        )
    return result


@router.get("/consistency/{result_id}/evidence")
def get_consistency_evidence(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = get_consistency_result(result_id, current_user=current_user, db=db)
    return {
        "result_id": result.result_id,
        "claim_id": result.claim.claim_id,
        "case_id": result.claim.case_id,
        "status": result.status,
        "confidence": result.confidence,
        "matched_evidence": result.matched_evidence,
        "conflicting_evidence": result.conflicting_evidence,
        "caveats": result.caveats,
    }


@router.get("/consistency", response_model=ConsistencyListResponse)
def list_consistency_results(
    case_id: Optional[str] = Query(None),
    status_filter: Optional[ConsistencyStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_cases = _get_user_allowed_cases(current_user, db)
    if case_id and allowed_cases is not None and case_id not in allowed_cases:
        raise HTTPException(status_code=403, detail=f"Access denied to case dossier: {case_id}")

    auth_list = list(allowed_cases) if allowed_cases is not None else None
    engine = ConsistencyEngine.get_instance()
    return engine.list_results(
        case_id=case_id,
        status=status_filter,
        limit=limit,
        offset=offset,
        authorized_cases=auth_list,
    )


# =============================================================================
# Unified Review & Decision History + Model Registry
# =============================================================================

@router.get("/decisions")
def list_review_decisions(
    limit: int = Query(100, ge=1, le=300),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unified Review & Decision History scoped strictly to authorized cases."""
    allowed_cases = _get_user_allowed_cases(current_user, db)
    entries: List[dict] = []

    for dec in db.query(IdentityHypothesisDecisionLog).order_by(IdentityHypothesisDecisionLog.created_at.desc()).limit(100).all():
        h = dec.hypothesis
        if h and all_cases_authorized([str(h.case_a_id or h.case_a_ref), str(h.case_b_id or h.case_b_ref)], allowed_cases):
            entries.append({
                "id": str(dec.id),
                "category": "IDENTITY_HYPOTHESIS",
                "target_id": str(h.id),
                "summary": f"{h.person_a_ref} <-> {h.person_b_ref} ({dec.previous_status} -> {dec.new_status})",
                "rationale": dec.rationale,
                "reviewer_id": str(dec.reviewer_id) if dec.reviewer_id else None,
                "cases": [h.case_a_ref, h.case_b_ref],
                "created_at": dec.created_at.isoformat(),
            })

    for dec in db.query(LeadDecisionLog).order_by(LeadDecisionLog.created_at.desc()).limit(100).all():
        lead = dec.lead
        if lead and all_cases_authorized(list(lead.source_case_ids or []) + list(lead.target_case_ids or []), allowed_cases):
            entries.append({
                "id": str(dec.id),
                "category": "INVESTIGATION_LEAD",
                "target_id": lead.lead_code,
                "summary": f"{lead.source_entity} <-> {lead.target_entity} ({dec.previous_status} -> {dec.new_status})",
                "rationale": dec.rationale,
                "reviewer_id": str(dec.reviewer_id) if dec.reviewer_id else None,
                "cases": list(set((lead.source_case_ids or []) + (lead.target_case_ids or []))),
                "created_at": dec.created_at.isoformat(),
            })

    for note in db.query(CaseNote).order_by(CaseNote.created_at.desc()).limit(100).all():
        if allowed_cases is None or str(note.case_id) in allowed_cases:
            entries.append({
                "id": str(note.id),
                "category": "ANALYST_NOTE",
                "target_id": str(note.case_id),
                "summary": note.note_text[:120],
                "rationale": note.note_text,
                "reviewer_id": str(note.created_by) if note.created_by else None,
                "cases": [str(note.case_id)],
                "created_at": note.created_at.isoformat(),
            })

    entries.sort(key=lambda x: x["created_at"], reverse=True)
    return {"total": len(entries), "decisions": entries[:limit]}


@router.get("/models")
def list_registered_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return active ML model artifacts and feature schema provenance."""
    rows = db.query(ModelArtifactRegistry).order_by(ModelArtifactRegistry.created_at.desc()).all()
    if not rows:
        return {
            "models": [
                {
                    "model_name": "entity_resolution_xgb",
                    "version": "er-xgb-1.0.0",
                    "feature_schema_version": "28f-v1",
                    "artifact_uri": "output/entity_resolution/model/xgboost_entity_resolution.json",
                    "is_active": True,
                },
                {
                    "model_name": "graphsage_link_pred",
                    "version": "graphsage-1.0.0",
                    "feature_schema_version": "gs-35f-v1",
                    "artifact_uri": "output/graphsage/model/graphsage_model.pt",
                    "is_active": True,
                },
            ]
        }
    return {
        "models": [
            {
                "id": str(m.id),
                "model_name": m.model_name,
                "version": m.version,
                "feature_schema_version": m.feature_schema_version,
                "artifact_uri": m.artifact_uri,
                "training_snapshot_id": m.training_snapshot_id,
                "evaluation_report": m.evaluation_report,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ]
    }
