import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models._compat import UUIDType


class Case(Base):
    __tablename__ = "cases"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_code = Column(String, unique=True, nullable=False, index=True)
    external_case_ref = Column(String, unique=True, nullable=True, index=True)
    title = Column(String, nullable=False)
    case_type = Column(String, nullable=False, default="HUMAN_TRAFFICKING")
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE")
    organization_id = Column(UUIDType, ForeignKey("organizations.id"), nullable=True, index=True)
    created_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="cases")
    members = relationship("CaseMember", back_populates="case", cascade="all, delete-orphan")
    evidence_items = relationship("EvidenceItem", back_populates="case", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="case")
    notes = relationship("CaseNote", back_populates="case")


class CaseMember(Base):
    __tablename__ = "case_members"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    case_role = Column(String, nullable=False, default="INVESTIGATOR")
    assigned_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_member"),)

    # Relationships
    case = relationship("Case", back_populates="members")
    user = relationship("User", back_populates="case_memberships", foreign_keys=[user_id])
