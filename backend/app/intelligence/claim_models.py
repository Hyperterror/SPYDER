"""
Pydantic v2 data models for Phase 6B: Statement-Evidence Consistency Engine.
Defines canonical predicates, consistency statuses, multidimensional confidence scores,
structured claims, matched evidence records, and API request/response payloads.
Enforces strictly non-prejudicial terminology and observable provenance.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClaimPredicate(str, Enum):
    """Controlled ontology of supported relational predicates."""
    CALLED = "CALLED"
    CONTACTED = "CONTACTED"
    LOCATED_AT = "LOCATED_AT"
    TRANSFERRED_TO = "TRANSFERRED_TO"
    TRAVELLED_TO = "TRAVELLED_TO"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"


class ConsistencyStatus(str, Enum):
    """
    Objective, non-prejudicial statement-evidence consistency classification.
    Never implies guilt, criminal culpability, or personal mendacity.
    """
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIABLE = "UNVERIFIABLE"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"


class EvidenceStrength(str, Enum):
    """Strength level of supporting or conflicting evidence."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StructuredClaim(BaseModel):
    """
    Normalized, structured representation of an investigative factual assertion.
    Extracted from text without subjective interpretations.
    """
    claim_id: str = Field(..., description="Deterministic unique identifier for the claim")
    case_id: str = Field(..., description="Associated case dossier identifier")
    source_document_id: str = Field(default="Unavailable", description="Dossier or statement document ID")
    subject_entity_id: str = Field(..., description="Normalized entity ID making or referenced by the assertion")
    predicate: Optional[ClaimPredicate] = Field(None, description="Controlled relational predicate (None if unparseable)")
    object_entity_id: Optional[str] = Field(None, description="Target entity, phone, or account identifier")
    time_start: Optional[str] = Field(None, description="Claimed interval start (ISO 8601 string)")
    time_end: Optional[str] = Field(None, description="Claimed interval end (ISO 8601 string)")
    location_id: Optional[str] = Field(None, description="Normalized location name or identifier")
    negated: bool = Field(default=False, description="True if assertion is explicitly negative (e.g. 'did not call')")
    raw_text: str = Field(..., description="Exact raw text snippet from which the claim was extracted")
    extraction_method: str = Field(default="RULE_BASED", description="Method utilized for extraction")
    claim_extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in claim parsing")
    entity_match_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in subject/object resolution")


class MatchedEvidenceRecord(BaseModel):
    """
    Traceable empirical evidence record matching a claim's entities, predicate, or time window.
    Strictly preserves provenance to underlying project tables without simulated facts.
    """
    record_id: str = Field(default="Unavailable", description="Underlying evidence table primary key")
    source_table: str = Field(default="Unavailable", description="CSV or graph table source")
    case_id: str = Field(default="Unavailable", description="Originating case dossier identifier")
    evidence_type: str = Field(default="Unavailable", description="Modality or record category")
    timestamp: str = Field(default="Unavailable", description="Observation timestamp if recorded")
    relation: str = Field(default="Unavailable", description="Empirical relation observed (e.g. CALLED, TRAVELLED_TO)")
    evidence_strength: EvidenceStrength = Field(default=EvidenceStrength.MEDIUM, description="Assessed evidence reliability")
    match_rationale: str = Field(..., description="Explainable reason this record supports or contradicts the claim")
    is_contradiction: bool = Field(default=False, description="True if record materially opposes the claim")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Observable metadata from record")


class ConfidenceBreakdown(BaseModel):
    """
    Transparent breakdown of confidence dimensions.
    Does NOT represent probability of guilt or truthfulness.
    """
    claim_extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Linguistic parsing certainty")
    entity_match_confidence: float = Field(..., ge=0.0, le=1.0, description="Identity resolution certainty")
    evidence_match_confidence: float = Field(..., ge=0.0, le=1.0, description="Relevance and temporal alignment of records")
    consistency_confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in consistency determination")


class ConsistencyAnalysisResult(BaseModel):
    """
    Complete statement-evidence consistency evaluation result with explanation and provenance.
    """
    result_id: str = Field(..., description="Unique deterministic identifier for the consistency assessment")
    claim: StructuredClaim = Field(..., description="The structured claim evaluated")
    status: ConsistencyStatus = Field(..., description="Consistency determination (SUPPORTED, CONTRADICTED, etc.)")
    confidence: ConfidenceBreakdown = Field(..., description="Multidimensional confidence breakdown")
    overall_evidence_strength: EvidenceStrength = Field(..., description="Aggregate strength of evaluated evidence")
    matched_evidence: List[MatchedEvidenceRecord] = Field(default_factory=list, description="Directly corroborating records")
    conflicting_evidence: List[MatchedEvidenceRecord] = Field(default_factory=list, description="Directly opposing records")
    explanation: str = Field(..., description="Human-readable neutral explanation grounded in matched records")
    caveats: List[str] = Field(default_factory=list, description="Methodological, infrastructure, and investigative caveats")
    recommended_action: str = Field(..., description="Next procedural step for investigator review")
    evaluated_at: str = Field(..., description="Timestamp of evaluation")


class AnalyzeStatementRequest(BaseModel):
    """Request payload to analyze a statement text against case evidence."""
    statement_text: str = Field(..., min_length=3, description="Raw statement or testimony text")
    case_id: str = Field(..., description="Target case dossier context")
    subject_entity_id: Optional[str] = Field(None, description="Explicit subject entity ID if pre-identified")
    source_document_id: Optional[str] = Field(None, description="Optional document or FIR identifier")


class AnalyzeStatementResponse(BaseModel):
    """Response payload containing all claims extracted and analyzed from statement."""
    statement_text: str
    case_id: str
    total_claims_extracted: int
    results: List[ConsistencyAnalysisResult]


class ConsistencyListResponse(BaseModel):
    """Paginated list of consistency analysis records."""
    total: int
    limit: int
    offset: int
    supported_count: int
    contradicted_count: int
    unverifiable_count: int
    conflict_count: int
    results: List[ConsistencyAnalysisResult]
