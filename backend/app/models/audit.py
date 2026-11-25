import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models._compat import UUIDType, JSONBType


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=True, index=True)
    evidence_id = Column(UUIDType, ForeignKey("evidence_items.id"), nullable=True, index=True)
    actor_user_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    sequence_number = Column(Integer, nullable=True)
    event_type = Column(String, nullable=False)
    event_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    event_metadata = Column(JSONBType, nullable=False, default=dict)
    previous_event_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=True)
    checkpoint_signature = Column(String(128), nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="audit_events")
    evidence = relationship("EvidenceItem", back_populates="audit_events", foreign_keys=[evidence_id])
    actor = relationship("User", back_populates="audit_events", foreign_keys=[actor_user_id])


class CaseNote(Base):
    __tablename__ = "case_notes"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    evidence_id = Column(UUIDType, ForeignKey("evidence_items.id"), nullable=True)
    graph_reference = Column(JSONBType, nullable=True)
    note_text = Column(Text, nullable=False)
    created_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="notes")
