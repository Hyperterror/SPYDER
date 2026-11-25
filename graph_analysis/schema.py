"""
Schema definitions for the Global Case Knowledge Graph.
Defines node types, edge types, provenance records, clustering metadata, and cross-case leads.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set, Any, Optional

class NodeType(str, Enum):
    PERSON = "PERSON"
    VICTIM = "VICTIM"
    CASE = "CASE"
    PHONE = "PHONE"
    DEVICE = "DEVICE"
    VEHICLE = "VEHICLE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    SOCIAL_ACCOUNT = "SOCIAL_ACCOUNT"
    LOCATION = "LOCATION"
    EVIDENCE = "EVIDENCE"
    ORGANIZATION = "ORGANIZATION"

class EdgeType(str, Enum):
    APPEARS_IN = "APPEARS_IN"
    CALLED = "CALLED"
    MESSAGED = "MESSAGED"
    USED_PHONE = "USED_PHONE"
    USED_DEVICE = "USED_DEVICE"
    USED_VEHICLE = "USED_VEHICLE"
    TRANSFERRED_MONEY = "TRANSFERRED_MONEY"
    TRAVELLED_TO = "TRAVELLED_TO"
    HAS_SOCIAL_ACCOUNT = "HAS_SOCIAL_ACCOUNT"
    ASSOCIATED_WITH_EVIDENCE = "ASSOCIATED_WITH_EVIDENCE"
    AFFILIATED_WITH = "AFFILIATED_WITH"
    OPERATES_IN = "OPERATES_IN"
    INVESTIGATED_BY = "INVESTIGATED_BY"
    PROCESSED_BY = "PROCESSED_BY"
    CONNECTED_TO = "CONNECTED_TO"
    OBSERVES_ENTITY = "OBSERVES_ENTITY"

@dataclass
class ProvenanceRecord:
    source_table: str
    source_id: str
    case_id: str
    timestamp: Optional[str] = None
    evidence_type: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_table": self.source_table,
            "source_id": self.source_id,
            "case_id": self.case_id,
            "timestamp": self.timestamp,
            "evidence_type": self.evidence_type,
            "confidence": round(self.confidence, 4),
            "notes": self.notes
        }

@dataclass
class GraphNode:
    node_id: str
    node_type: NodeType
    label: str
    case_ids: Set[str] = field(default_factory=set)
    resolved_entity_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "case_ids": sorted(list(self.case_ids)),
            "resolved_entity_id": self.resolved_entity_id,
            **self.attributes
        }

@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    provenance: ProvenanceRecord
    timestamp: Optional[str] = None
    weight: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "timestamp": self.timestamp,
            "weight": round(self.weight, 4),
            "provenance_table": self.provenance.source_table,
            "provenance_record_id": self.provenance.source_id,
            "provenance_case_id": self.provenance.case_id,
            "provenance_evidence_type": self.provenance.evidence_type,
            "provenance_confidence": round(self.provenance.confidence, 4),
            "notes": self.provenance.notes,
            **self.attributes
        }

@dataclass
class ResolvedClusterMetadata:
    cluster_id: str
    member_person_ids: List[str]
    member_cases: List[str]
    pairwise_links: List[Dict[str, Any]]
    cohesion_score: float
    min_pair_probability: float
    is_transitive: bool
    cluster_diameter: int
    flagged_for_review: bool
    review_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "member_person_ids": self.member_person_ids,
            "member_cases": self.member_cases,
            "pairwise_links_count": len(self.pairwise_links),
            "cohesion_score": round(self.cohesion_score, 4),
            "min_pair_probability": round(self.min_pair_probability, 4),
            "is_transitive": self.is_transitive,
            "cluster_diameter": self.cluster_diameter,
            "flagged_for_review": self.flagged_for_review,
            "review_reasons": self.review_reasons
        }

@dataclass
class CrossCaseConnection:
    source_case: str
    target_case: str
    path: List[str]
    connecting_entities: List[str]
    path_length: int
    relationship_types: List[str]
    supporting_evidence: List[Dict[str, Any]]
    timestamps: List[str]
    score: float
    tier: str
    reasons: List[str]
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_case": self.source_case,
            "target_case": self.target_case,
            "path": " -> ".join(self.path),
            "connecting_entities": "; ".join(self.connecting_entities),
            "path_length": self.path_length,
            "relationship_types": "; ".join(self.relationship_types),
            "supporting_evidence_count": len(self.supporting_evidence),
            "earliest_timestamp": min(self.timestamps) if self.timestamps else None,
            "latest_timestamp": max(self.timestamps) if self.timestamps else None,
            "score": round(self.score, 4),
            "tier": self.tier,
            "reasons": "; ".join(self.reasons),
            "explanation": self.explanation
        }
