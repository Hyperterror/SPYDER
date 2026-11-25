import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from app.core.database import Base
from app.models._compat import UUIDType, JSONBType


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    version_number = Column(Integer, nullable=False, unique=True)
    version_tag = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="BUILDING")  # BUILDING, VALIDATED, ACTIVE, ROLLED_BACK, FAILED
    node_count = Column(Integer, default=0, nullable=False)
    edge_count = Column(Integer, default=0, nullable=False)
    artifact_dir = Column(String, nullable=True)
    manifest = Column(JSONBType, nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
