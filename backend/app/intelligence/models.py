"""
Pydantic v2 data models for Investigation Leads and Structured Provenance Records.
Enforces strictly neutral, non-prejudicial terminology.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PriorityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    REVIEW = "REVIEW"
    LOW = "LOW"


class PredictionType(str, Enum):
    POTENTIAL_ASSOCIATION = "Potential Association"
    CANDIDATE_LINK = "Candidate Link"


class EvidenceStrength(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class StructuredEvidenceRecord(BaseModel):
    """
    Concrete observable evidence record linking entities.
    Never contains hallucinated facts; all fields map directly to observable records.
    """
    reason: str = Field(..., description="Explanation of why this record links the entities")
    evidence_type: str = Field(..., description="Modality or record category (e.g. CDR, USED_DEVICE)")
    case_id: Optional[str] = Field(None, description="Case dossier identifier where record originated")
    record_id: Optional[str] = Field(None, description="Identifier of the specific evidence record")
    source_file: Optional[str] = Field(None, description="Source evidentiary table or log file")
    source_row: Optional[int] = Field(None, description="Source row index if recorded")
    timestamp: Optional[str] = Field(None, description="Observed timestamp if present, otherwise null")


class InvestigationLead(BaseModel):
    """
    Structured representation of a candidate association lead produced by GraphSAGE.
    Represents an investigative hypothesis lead, NOT factual proof of guilt or identity.
    """
    lead_id: str = Field(..., description="Deterministic unique identifier for the lead")
    source_entity: str = Field(..., description="Source observational entity identifier")
    target_entity: str = Field(..., description="Target observational entity identifier")
    source_case_ids: List[str] = Field(default_factory=list, description="Case dossiers containing source entity")
    target_case_ids: List[str] = Field(default_factory=list, description="Case dossiers containing target entity")
    is_cross_case: bool = Field(..., description="True if entities appear in separate case dossiers")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model prediction confidence score")
    priority: PriorityTier = Field(..., description="Deterministic priority classification (HIGH, REVIEW, LOW)")
    prediction_type: PredictionType = Field(
        default=PredictionType.POTENTIAL_ASSOCIATION,
        description="Neutral prediction classification"
    )
    evidence_strength: EvidenceStrength = Field(
        default=EvidenceStrength.MODERATE,
        description="Assessed evidence corroboration strength"
    )
    explanation: str = Field(..., description="Human-readable neutral narrative explanation")
    supporting_modalities: List[str] = Field(
        default_factory=list,
        description="Distinct evidence modalities corroborating the association"
    )
    common_intermediates_count: int = Field(0, description="Count of shared 2-hop structural intermediates")
    common_intermediates: List[str] = Field(
        default_factory=list,
        description="Representative shared intermediate entity identifiers"
    )
    caveats: List[str] = Field(
        default_factory=list,
        description="Investigative warnings or public infrastructure caveats"
    )
    supporting_records: List[StructuredEvidenceRecord] = Field(
        default_factory=list,
        description="Direct observable evidence records supporting the lead"
    )
    created_at: str = Field(..., description="Timestamp when lead was produced")


class LeadResponse(BaseModel):
    total: int
    limit: int
    offset: int
    leads: List[InvestigationLead]


class CrossCaseLeadSummary(BaseModel):
    """
    Summarized high-level view for cross-case association matrices.
    """
    lead_id: str
    source_entity: str
    target_entity: str
    source_cases: List[str]
    target_cases: List[str]
    confidence: float
    priority: PriorityTier
    supporting_modalities: List[str]
    common_intermediates_count: int
    caveats: List[str]


class CrossCaseResponse(BaseModel):
    total: int
    cross_case_leads: List[CrossCaseLeadSummary]
