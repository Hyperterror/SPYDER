import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models._compat import UUIDType
import enum


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    INVESTIGATOR = "INVESTIGATOR"
    ANALYST = "ANALYST"


class User(Base):
    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False, default=UserRole.INVESTIGATOR)
    organization_id = Column(UUIDType, ForeignKey("organizations.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    case_memberships = relationship("CaseMember", back_populates="user", foreign_keys="CaseMember.user_id")
    uploaded_evidence = relationship("EvidenceItem", back_populates="uploader", foreign_keys="EvidenceItem.uploaded_by")
    audit_events = relationship("AuditEvent", back_populates="actor", foreign_keys="AuditEvent.actor_user_id")

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"
