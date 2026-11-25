import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models._compat import JSONBType, UUIDType


class IdentityHypothesis(Base):
    __tablename__ = "identity_hypotheses"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    hypothesis_key = Column(String(64), unique=True, nullable=False, index=True)
    person_a_ref = Column(String, nullable=False, index=True)
    person_b_ref = Column(String, nullable=False, index=True)
    person_a_name = Column(String, nullable=True)
    person_b_name = Column(String, nullable=True)
    case_a_id = Column(UUIDType, ForeignKey("cases.id"), nullable=True, index=True)
    case_b_id = Column(UUIDType, ForeignKey("cases.id"), nullable=True, index=True)
    case_a_ref = Column(String, nullable=False, index=True)
    case_b_ref = Column(String, nullable=False, index=True)
    match_probability = Column(Float, nullable=False)
    confidence_tier = Column(String, nullable=False)
    model_version = Column(String, nullable=False, default="er-xgb-1.0.0")
    feature_explanation = Column(JSONBType, nullable=False, default=dict)
    supporting_evidence = Column(JSONBType, nullable=False, default=list)
    conflicting_evidence = Column(JSONBType, nullable=False, default=list)
    blocking_reasons = Column(JSONBType, nullable=False, default=list)
    profile_a_snapshot = Column(JSONBType, nullable=False, default=dict)
    profile_b_snapshot = Column(JSONBType, nullable=False, default=dict)
    status = Column(String, nullable=False, default="PENDING_REVIEW")  # CANDIDATE, PENDING_REVIEW, ACCEPTED, REJECTED, DISPUTED, SUPERSEDED
    reviewed_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    decision_rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    decisions = relationship("IdentityHypothesisDecisionLog", back_populates="hypothesis", cascade="all, delete-orphan")


class IdentityHypothesisDecisionLog(Base):
    __tablename__ = "identity_hypothesis_decisions"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    hypothesis_id = Column(UUIDType, ForeignKey("identity_hypotheses.id"), nullable=False, index=True)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    reviewer_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    hypothesis = relationship("IdentityHypothesis", back_populates="decisions")


class IntelligenceLeadRecord(Base):
    __tablename__ = "intelligence_leads"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    lead_code = Column(String(64), unique=True, nullable=False, index=True)
    source_entity = Column(String, nullable=False, index=True)
    target_entity = Column(String, nullable=False, index=True)
    source_case_ids = Column(JSONBType, nullable=False, default=list)
    target_case_ids = Column(JSONBType, nullable=False, default=list)
    is_cross_case = Column(Boolean, default=False, nullable=False)
    candidate_relationship_type = Column(String, nullable=False, default="Potential Association")
    model_version = Column(String, nullable=False, default="graphsage-1.0.0")
    graph_snapshot_version = Column(String, nullable=True)
    prediction_score = Column(Float, nullable=False)
    priority_tier = Column(String, nullable=False, default="REVIEW")
    evidence_strength = Column(String, nullable=False, default="MODERATE")
    explanation = Column(Text, nullable=False)
    supporting_modalities = Column(JSONBType, nullable=False, default=list)
    common_intermediates = Column(JSONBType, nullable=False, default=list)
    caveats = Column(JSONBType, nullable=False, default=list)
    supporting_records = Column(JSONBType, nullable=False, default=list)
    conflicting_records = Column(JSONBType, nullable=False, default=list)
    status = Column(String, nullable=False, default="NEW")  # NEW, UNDER_REVIEW, REQUIRES_MORE_EVIDENCE, ACCEPTED_FOR_FURTHER_INVESTIGATION, REJECTED, CLOSED
    reviewed_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    decision_rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    decisions = relationship("LeadDecisionLog", back_populates="lead", cascade="all, delete-orphan")


class LeadDecisionLog(Base):
    __tablename__ = "lead_decisions"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUIDType, ForeignKey("intelligence_leads.id"), nullable=False, index=True)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    reviewer_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    lead = relationship("IntelligenceLeadRecord", back_populates="decisions")


class ConsistencyAnalysisRecord(Base):
    __tablename__ = "consistency_analyses"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    result_id = Column(String(128), unique=True, nullable=False, index=True)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=True, index=True)
    case_ref = Column(String, nullable=False, index=True)
    subject_entity_id = Column(String, nullable=False)
    statement_text = Column(Text, nullable=False)
    source_document_id = Column(String, nullable=True)
    original_claim = Column(JSONBType, nullable=False)
    current_claim = Column(JSONBType, nullable=False)
    status = Column(String, nullable=False)
    confidence_breakdown = Column(JSONBType, nullable=False)
    matched_evidence = Column(JSONBType, nullable=False, default=list)
    conflicting_evidence = Column(JSONBType, nullable=False, default=list)
    caveats = Column(JSONBType, nullable=False, default=list)
    explanation = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    reviewer_comment = Column(Text, nullable=True)
    reviewed_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ModelArtifactRegistry(Base):
    __tablename__ = "model_artifact_registry"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    model_name = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    feature_schema_version = Column(String, nullable=False)
    artifact_uri = Column(String, nullable=False)
    training_snapshot_id = Column(String, nullable=True)
    evaluation_report = Column(JSONBType, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
