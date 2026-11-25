import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models._compat import UUIDType, JSONBType


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    evidence_code = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    sanitized_filename = Column(String, nullable=False)
    file_extension = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    object_storage_bucket = Column(String, nullable=False)
    object_storage_key = Column(String, nullable=False)
    source_label = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    # Searchable text recovered from PDF / raster-image evidence (best-effort).
    # CSV/XLSX/JSON uploads leave this NULL because their rows are parsed instead.
    extracted_text = Column(Text, nullable=True)
    sha256_hash = Column(String(64), nullable=False)
    hash_algorithm = Column(String, default="SHA-256", nullable=False)
    integrity_status = Column(String, default="UNVERIFIED", nullable=False)
    uploaded_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    parsing_status = Column(String, default="PENDING", nullable=False)
    parsing_error = Column(Text, nullable=True)
    processing_status = Column(String, default="UPLOADED", nullable=False)
    is_original = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint("case_id", "evidence_code", name="uq_case_evidence_code"),)

    # Relationships
    case = relationship("Case", back_populates="evidence_items")
    uploader = relationship("User", back_populates="uploaded_evidence", foreign_keys=[uploaded_by])
    parsing_jobs = relationship("ParsingJob", back_populates="evidence", cascade="all, delete-orphan")
    processing_jobs = relationship("EvidenceProcessingJob", back_populates="evidence", cascade="all, delete-orphan")
    parsed_records = relationship("ParsedRecord", back_populates="evidence", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="evidence", foreign_keys="AuditEvent.evidence_id")


class EvidenceProcessingJob(Base):
    __tablename__ = "evidence_processing_jobs"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    evidence_id = Column(UUIDType, ForeignKey("evidence_items.id"), nullable=False)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    job_type = Column(String, nullable=False, default="EVIDENCE_INGESTION")
    status = Column(String, nullable=False, default="UPLOADED")  # UPLOADED, VALIDATING, PROCESSING, PROCESSED, FAILED
    pipeline_version = Column(String, nullable=False, default="7A.1.0")
    records_processed = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    result_summary = Column(JSONBType, nullable=True)
    initiated_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    evidence = relationship("EvidenceItem", back_populates="processing_jobs")
    case = relationship("Case")


class ParsingJob(Base):
    __tablename__ = "parsing_jobs"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    evidence_id = Column(UUIDType, ForeignKey("evidence_items.id"), nullable=False)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="QUEUED")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    initiated_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    result_summary = Column(JSONBType, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    evidence = relationship("EvidenceItem", back_populates="parsing_jobs")


class ParsedRecord(Base):
    __tablename__ = "parsed_records"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    case_id = Column(UUIDType, ForeignKey("cases.id"), nullable=False)
    evidence_id = Column(UUIDType, ForeignKey("evidence_items.id"), nullable=False)
    record_type = Column(String, nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_record = Column(JSONBType, nullable=False)
    normalized_record = Column(JSONBType, nullable=False)
    parse_status = Column(String, nullable=False)
    parse_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("evidence_id", "source_row_number", "record_type", name="uq_parsed_record"),
    )

    # Relationships
    evidence = relationship("EvidenceItem", back_populates="parsed_records")
