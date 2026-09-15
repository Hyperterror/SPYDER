"""
Intelligence Integration Layer package for SPYDER-DETECT.
"""

from app.intelligence.models import (
    InvestigationLead,
    StructuredEvidenceRecord,
    PriorityTier,
    PredictionType,
    EvidenceStrength,
    LeadResponse,
    CrossCaseLeadSummary,
    CrossCaseResponse,
)
from app.intelligence.adapter import Phase4ArtifactAdapter
from app.intelligence.leads import LeadRepository
from app.intelligence.explanations import ExplanationEngine

__all__ = [
    "InvestigationLead",
    "StructuredEvidenceRecord",
    "PriorityTier",
    "PredictionType",
    "EvidenceStrength",
    "LeadResponse",
    "CrossCaseLeadSummary",
    "CrossCaseResponse",
    "Phase4ArtifactAdapter",
    "LeadRepository",
    "ExplanationEngine",
]
