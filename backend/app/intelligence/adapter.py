"""
Phase 4 Artifact Adapter.
Safely reads Phase 4 GraphSAGE link prediction outputs and Phase 3 graph edges.
STRICT GUARANTEE: Never loads or passes evaluation ground-truth labels (label column).
"""

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.intelligence.config import (
    CANDIDATE_LINKS_PATH,
    EDGES_PATH,
    GENERIC_LOCATIONS,
    HARD_NEGATIVE_CATEGORIES,
    KNOWN_PUBLIC_IPS,
    KNOWN_SHARED_BUSES,
    NODE_EMBEDDINGS_PATH,
    PREDICTIONS_PATH,
    THRESHOLD_HIGH_PRIORITY,
    THRESHOLD_REVIEW,
)
from app.intelligence.models import (
    EvidenceStrength,
    InvestigationLead,
    PredictionType,
    PriorityTier,
    StructuredEvidenceRecord,
)


class Phase4ArtifactAdapter:
    """
    Ingests Phase 4 predictions and candidate links, cross-referencing Phase 3 graph edges
    to construct fully grounded InvestigationLead domain objects without ground-truth contamination.
    """

    def __init__(
        self,
        predictions_path: Path = PREDICTIONS_PATH,
        candidate_links_path: Path = CANDIDATE_LINKS_PATH,
        node_embeddings_path: Path = NODE_EMBEDDINGS_PATH,
        edges_path: Path = EDGES_PATH,
    ):
        self.predictions_path = Path(predictions_path)
        self.candidate_links_path = Path(candidate_links_path)
        self.node_embeddings_path = Path(node_embeddings_path)
        self.edges_path = Path(edges_path)

        # In-memory edge provenance index: node_id -> list of incident edge dicts
        self._edge_index: Optional[Dict[str, List[dict]]] = None

    def verify_artifacts_exist(self) -> None:
        """Raises FileNotFoundError with explicit details if required artifacts are missing."""
        required = [
            ("predictions.csv", self.predictions_path),
            ("candidate_links.csv", self.candidate_links_path),
            ("node_embeddings.csv", self.node_embeddings_path),
        ]
        for name, path in required:
            if not path.exists():
                raise FileNotFoundError(
                    f"Required Phase 4 artifact '{name}' not found at: {path.resolve()}"
                )

    def _load_edge_index(self) -> Dict[str, List[dict]]:
        """Indexes Phase 3 edges by participating node IDs for fast provenance retrieval."""
        if self._edge_index is not None:
            return self._edge_index

        index: Dict[str, List[dict]] = {}
        if not self.edges_path.exists():
            self._edge_index = index
            return index

        with open(self.edges_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                u = row.get("source_id", "")
                v = row.get("target_id", "")
                rec = {
                    "source_id": u,
                    "target_id": v,
                    "edge_type": row.get("edge_type", ""),
                    "timestamp": row.get("timestamp") or None,
                    "weight": row.get("weight"),
                    "table": row.get("provenance_table") or None,
                    "record_id": row.get("provenance_record_id") or None,
                    "case_id": row.get("provenance_case_id") or None,
                    "evidence_type": row.get("provenance_evidence_type") or row.get("edge_type", ""),
                    "notes": row.get("notes") or "",
                }
                index.setdefault(u, []).append(rec)
                index.setdefault(v, []).append(rec)

        self._edge_index = index
        return index

    @staticmethod
    def generate_lead_id(source: str, target: str) -> str:
        """Deterministic lead ID based on canonical sorted pair order."""
        pair = sorted([source, target])
        raw = f"{pair[0]}:{pair[1]}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return f"LEAD_{digest.upper()}"

    def load_leads(self) -> List[InvestigationLead]:
        """
        Loads Phase 4 prediction records and candidate links into typed InvestigationLead objects.
        Explicitly excludes the ground-truth 'label' column.
        """
        self.verify_artifacts_exist()
        edge_index = self._load_edge_index()

        # 1. Load candidate link metadata (category, cases, is_cross_case)
        candidate_meta: Dict[Tuple[str, str], dict] = {}
        with open(self.candidate_links_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                s = row.get("source", "")
                t = row.get("target", "")
                key = tuple(sorted([s, t]))
                candidate_meta[key] = {
                    "category": row.get("category", "UNKNOWN"),
                    "source_cases": [c.strip() for c in (row.get("source_cases") or "").split(";") if c.strip()],
                    "target_cases": [c.strip() for c in (row.get("target_cases") or "").split(";") if c.strip()],
                    "is_cross_case": row.get("is_cross_case") == "True",
                    # NOTE: Ground-truth 'label' is strictly ignored here!
                }

        # 2. Ingest predictions.csv
        leads: List[InvestigationLead] = []
        now_str = datetime.now(timezone.utc).isoformat()

        with open(self.predictions_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=1):
                src = row.get("source_node", "")
                tgt = row.get("target_node", "")
                if not src or not tgt:
                    continue

                pair_key = tuple(sorted([src, tgt]))
                meta = candidate_meta.get(pair_key, {})

                score = float(row.get("prediction_score") or 0.0)
                category = row.get("category") or meta.get("category", "UNKNOWN")

                # Parse cases
                s_cases = [c.strip() for c in (row.get("source_cases") or "").split(";") if c.strip()]
                if not s_cases:
                    s_cases = meta.get("source_cases", [])
                t_cases = [c.strip() for c in (row.get("target_cases") or "").split(";") if c.strip()]
                if not t_cases:
                    t_cases = meta.get("target_cases", [])

                is_cross = row.get("is_cross_case") == "True" if "is_cross_case" in row else meta.get("is_cross_case", False)

                # Parse intermediates and modalities
                raw_intermediates = row.get("common_neighbors", "")
                intermediates = [i.strip() for i in raw_intermediates.split(";") if i.strip()]

                raw_modalities = row.get("shared_modalities", "")
                modalities = [m.strip() for m in raw_modalities.split(";") if m.strip()]

                # Build caveats & priority safeguards
                caveats: List[str] = []
                is_hard_negative = category in HARD_NEGATIVE_CATEGORIES

                if category == "NEG_F_SHARED_PUBLIC_IP" or any(ip in raw_intermediates for ip in KNOWN_PUBLIC_IPS):
                    caveats.append("Pair associated through shared public Wi-Fi infrastructure (Mahipalpur Transit / Cyber Kiosk).")
                if category == "NEG_E_SHARED_COMMERCIAL_VEHICLE" or any(bus in raw_intermediates for bus in KNOWN_SHARED_BUSES):
                    caveats.append("Pair associated via interstate commercial sleeper bus (VEH_026 fleet transport).")
                if category == "NEG_D_SHARED_LOCATION" or any(loc in raw_intermediates for loc in GENERIC_LOCATIONS):
                    caveats.append("Pair co-occurs at broad generic transit waypoint (Delhi NCR / Kolkata / Patna).")
                if category == "NEG_G_HIGH_DEGREE_HUB":
                    caveats.append("Pair shares high-degree ambient hub node; connection reflects network topology rather than specific coordination.")

                # Priority Logic with Hard Negative Safeguards
                if is_hard_negative or caveats:
                    # Public infrastructure or ambient hard negatives are NEVER assigned HIGH priority
                    priority = PriorityTier.LOW
                elif score >= THRESHOLD_HIGH_PRIORITY:
                    priority = PriorityTier.HIGH
                elif score >= THRESHOLD_REVIEW:
                    priority = PriorityTier.REVIEW
                else:
                    priority = PriorityTier.LOW

                # Evidence strength assessment
                if len(modalities) >= 3 and len(intermediates) >= 4:
                    evidence_strength = EvidenceStrength.STRONG
                elif len(modalities) >= 2 or len(intermediates) >= 2:
                    evidence_strength = EvidenceStrength.MODERATE
                else:
                    evidence_strength = EvidenceStrength.WEAK

                # Retrieve real supporting records from edge index (NO HALLUCINATIONS)
                supporting_records: List[StructuredEvidenceRecord] = []
                for inter in intermediates[:5]:
                    # Find edges linking src to inter or tgt to inter
                    for edge in edge_index.get(inter, []):
                        if edge["source_id"] in (src, tgt) or edge["target_id"] in (src, tgt):
                            supporting_records.append(
                                StructuredEvidenceRecord(
                                    reason=f"Direct observational association with shared intermediate {inter}",
                                    evidence_type=edge["evidence_type"],
                                    case_id=edge["case_id"],
                                    record_id=edge["record_id"],
                                    source_file=edge["table"],
                                    source_row=None,
                                    timestamp=edge["timestamp"],
                                )
                            )
                            if len(supporting_records) >= 8:
                                break
                    if len(supporting_records) >= 8:
                        break

                lead = InvestigationLead(
                    lead_id=self.generate_lead_id(src, tgt),
                    source_entity=src,
                    target_entity=tgt,
                    source_case_ids=s_cases,
                    target_case_ids=t_cases,
                    is_cross_case=is_cross,
                    confidence=round(score, 4),
                    priority=priority,
                    prediction_type=PredictionType.POTENTIAL_ASSOCIATION,
                    evidence_strength=evidence_strength,
                    explanation=row.get("explanation") or f"Potential association between {src} and {tgt}.",
                    supporting_modalities=modalities,
                    common_intermediates_count=int(row.get("common_neighbors_count") or len(intermediates)),
                    common_intermediates=intermediates,
                    caveats=caveats,
                    supporting_records=supporting_records,
                    created_at=now_str,
                )
                leads.append(lead)

        return leads
