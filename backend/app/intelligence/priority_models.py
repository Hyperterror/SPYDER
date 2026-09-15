"""
Pydantic v2 data models for Phase 6A Investigation Priority Engine.
Enforces strictly neutral, non-prejudicial terminology and observable provenance.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from app.intelligence.models import PriorityTier


class PersonProvenanceRecord(BaseModel):
    """
    Direct observable evidence record linking a person to graph relationships.
    Missing attributes strictly default to 'Unavailable' to avoid fabrication.
    """
    case_id: str = Field(default="Unavailable", description="Case dossier identifier")
    evidence_type: str = Field(default="Unavailable", description="Type of evidence or modality")
    source_table: str = Field(default="Unavailable", description="Evidentiary source table or file")
    record_id: str = Field(default="Unavailable", description="Underlying record identifier")
    timestamp: str = Field(default="Unavailable", description="Observation timestamp if recorded")
    relationship: str = Field(default="Unavailable", description="Relationship or edge type")
    related_entity: str = Field(default="Unavailable", description="Identifier of the connected entity")
    notes: Optional[str] = Field(None, description="Investigative notes or procedural context")


class PriorityScoreBreakdown(BaseModel):
    """
    Transparent, explainable breakdown of the deterministic composite priority score.
    """
    cross_case_score: float = Field(..., ge=0.0, le=25.0, description="Cross-case presence contribution (0-25)")
    network_score: float = Field(..., ge=0.0, le=20.0, description="Network centrality contribution (0-20)")
    evidence_score: float = Field(..., ge=0.0, le=20.0, description="Evidence modality diversity contribution (0-20)")
    bridge_score: float = Field(..., ge=0.0, le=15.0, description="Cross-case bridge pathways contribution (0-15)")
    sage_score: float = Field(..., ge=0.0, le=20.0, description="GraphSAGE candidate predictions contribution (0-20)")
    infrastructure_penalty: float = Field(default=0.0, ge=0.0, le=10.0, description="Dampening penalty for public infrastructure reliance")
    total_score: float = Field(..., ge=0.0, le=100.0, description="Final deterministic priority score (0-100)")


class PersonInvestigationPriority(BaseModel):
    """
    Ranked Investigation Priority representation for a PERSON entity.
    Serves as an objective decision-support signal, NOT proof of guilt or identity.
    """
    person_id: str = Field(..., description="Unique entity identifier (e.g. CASE_007_PER_01 or PROV_RES_ENT_001)")
    label: str = Field(..., description="Entity display label or alias")
    entity_type: str = Field(default="PERSON", description="Graph entity category")
    is_provisional_resolved: bool = Field(default=False, description="True if provisional entity resolution cluster")
    resolved_entity_id: Optional[str] = Field(None, description="Provisional resolved cluster ID if applicable")
    score: float = Field(..., ge=0.0, le=100.0, description="Deterministic composite score (0-100)")
    priority: PriorityTier = Field(..., description="Priority classification (HIGH, MEDIUM, LOW)")
    cases_count: int = Field(..., ge=0, description="Number of authorized cases associated with entity")
    associated_cases: List[str] = Field(default_factory=list, description="Authorized case dossiers involving this entity")
    modalities_count: int = Field(..., ge=0, description="Count of distinct observable evidence modalities")
    modalities: List[str] = Field(default_factory=list, description="List of observed evidence modalities")
    network_degree: int = Field(..., ge=0, description="Raw degree in the projected evidence graph")
    betweenness_centrality: float = Field(..., ge=0.0, description="Betweenness centrality conduit metric")
    pagerank: float = Field(..., ge=0.0, description="PageRank centrality metric")
    score_breakdown: PriorityScoreBreakdown = Field(..., description="Component-level score attribution")
    reasons: List[str] = Field(default_factory=list, description="Calculated non-zero contributing evidence signals")
    caveats: List[str] = Field(default_factory=list, description="Investigative caveats and infrastructure warnings")
    top_candidate_link_score: Optional[float] = Field(None, description="Highest Phase 4 GraphSAGE link prediction score")
    cross_case_candidates_count: int = Field(0, description="Count of predicted cross-case candidate associations")
    provenance_count: int = Field(..., ge=0, description="Count of traceable supporting evidence records")


class PriorityListResponse(BaseModel):
    """
    Paginated priority ranking list response.
    """
    total: int = Field(..., description="Total matching persons meeting filter criteria")
    limit: int = Field(..., description="Page limit")
    offset: int = Field(..., description="Page offset")
    high_count: int = Field(..., description="Count of HIGH priority entities in matching set")
    medium_count: int = Field(..., description="Count of MEDIUM priority entities in matching set")
    low_count: int = Field(..., description="Count of LOW priority entities in matching set")
    priorities: List[PersonInvestigationPriority] = Field(default_factory=list, description="Ranked entity priorities")


class PersonEvidenceResponse(BaseModel):
    """
    Detailed provenance evidence report for a specific person entity.
    """
    person_id: str = Field(..., description="Entity identifier")
    label: str = Field(..., description="Entity display label")
    is_provisional_resolved: bool = Field(default=False, description="True if provisional resolved cluster")
    total_records: int = Field(..., ge=0, description="Total observable provenance records")
    records: List[PersonProvenanceRecord] = Field(default_factory=list, description="List of observable provenance records")
