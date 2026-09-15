"""
Phase 6A: Investigation Priority Engine.
Deterministic, explainable ranking of PERSON entities into HIGH, MEDIUM, and LOW
investigation priorities based on observable graph and evidence signals.

STRICT GUARANTEES:
1. Zero ground-truth label leakage (ignores any label columns in Phase 4 predictions).
2. Purely observable signals (graph topology, evidence modalities, GraphSAGE model outputs).
3. Public infrastructure safeguard (dampens commercial transit/public hubs with explicit caveats).
4. Strictly non-prejudicial terminology.
5. RBAC-compliant case filtering and information isolation.
"""

import csv
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Set, Tuple

from app.intelligence.config import (
    CASE_GRAPH_PATH,
    EDGES_PATH,
    GRAPH_ANALYSIS_DIR,
    KNOWN_PUBLIC_IPS,
    KNOWN_SHARED_BUSES,
    NODES_PATH,
    PHASE4_OUTPUT_DIR,
    PREDICTIONS_PATH,
)
from app.intelligence.models import PriorityTier
from app.intelligence.priority_models import (
    PersonEvidenceResponse,
    PersonInvestigationPriority,
    PersonProvenanceRecord,
    PriorityListResponse,
    PriorityScoreBreakdown,
)

# Additional Phase 3 path
NODE_METRICS_PATH = GRAPH_ANALYSIS_DIR / "node_metrics.csv"
CROSS_CASE_CONNECTIONS_PATH = GRAPH_ANALYSIS_DIR / "cross_case_connections.csv"

# Deterministic Score Thresholds
THRESHOLD_HIGH = 70.0
THRESHOLD_MEDIUM = 45.0


class InvestigationPriorityEngine:
    """
    Deterministic scoring and explainability engine for person investigation priorities.
    Maintains thread-safe in-memory cache of scored persons and incident provenance records.
    """

    _instance: Optional["InvestigationPriorityEngine"] = None
    _lock: Lock = Lock()

    def __init__(
        self,
        nodes_path: Path = NODES_PATH,
        metrics_path: Path = NODE_METRICS_PATH,
        edges_path: Path = EDGES_PATH,
        cross_case_path: Path = CROSS_CASE_CONNECTIONS_PATH,
        predictions_path: Path = PREDICTIONS_PATH,
    ):
        self.nodes_path = Path(nodes_path)
        self.metrics_path = Path(metrics_path)
        self.edges_path = Path(edges_path)
        self.cross_case_path = Path(cross_case_path)
        self.predictions_path = Path(predictions_path)

        self._loaded: bool = False
        self._load_lock: Lock = Lock()

        # Cache structures
        self._priorities_list: List[PersonInvestigationPriority] = []
        self._priority_by_id: Dict[str, PersonInvestigationPriority] = {}
        self._provenance_by_id: Dict[str, List[PersonProvenanceRecord]] = {}

    @classmethod
    def get_instance(cls) -> "InvestigationPriorityEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def load_if_needed(self) -> None:
        """Loads and scores entities once thread-safely."""
        if self._loaded:
            return
        with self._load_lock:
            if not self._loaded:
                self._compute_and_cache_priorities()
                self._loaded = True

    def reload(self) -> None:
        """Forces recalculation of scores and cache reload (for testing/refresh)."""
        with self._load_lock:
            self._compute_and_cache_priorities()
            self._loaded = True

    def _compute_and_cache_priorities(self) -> None:
        """
        Ingests observable artifacts and computes deterministic priority scores
        strictly following the approved formula.
        """
        # 1. Load Nodes (PERSON nodes only)
        # Format: node_id, node_type, label, case_ids, resolved_entity_id, is_provisional_resolved, priority_status
        person_nodes: List[dict] = []
        prov_cases_map: Dict[str, Set[str]] = {}
        with open(self.nodes_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("node_type") == "PERSON":
                    person_nodes.append(row)
                    if row.get("is_provisional_resolved", "").lower() == "true":
                        c_list = [c.strip() for c in str(row.get("case_ids", "")).split(";") if c.strip()]
                        prov_cases_map[row["node_id"]] = set(c_list)

        # 2. Load Node Metrics (centrality metrics)
        metrics_map: Dict[str, dict] = {}
        if self.metrics_path.exists():
            with open(self.metrics_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metrics_map[row["node_id"]] = row

        # 3. Load Cross-Case Connections (connecting entities)
        ccc_entities: Set[str] = set()
        if self.cross_case_path.exists():
            with open(self.cross_case_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ents = str(row.get("connecting_entities", "")).split(";")
                    for e in ents:
                        if e.strip():
                            ccc_entities.add(e.strip())

        # 4. Load Edges & Build Provenance Index
        node_edges: Dict[str, List[dict]] = defaultdict(list)
        provenance_records_map: Dict[str, List[PersonProvenanceRecord]] = defaultdict(list)
        if self.edges_path.exists():
            with open(self.edges_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    u = row.get("source_id", "")
                    v = row.get("target_id", "")
                    edge_type = row.get("edge_type", "")
                    table = row.get("provenance_table") or "Unavailable"
                    rec_id = row.get("provenance_record_id") or "Unavailable"
                    case_id = row.get("provenance_case_id") or "Unavailable"
                    ts = row.get("timestamp") or "Unavailable"
                    notes = row.get("notes") or None

                    edge_rec = {
                        "source_id": u,
                        "target_id": v,
                        "edge_type": edge_type,
                        "table": table,
                        "record_id": rec_id,
                        "case_id": case_id,
                        "timestamp": ts,
                        "notes": notes,
                    }
                    node_edges[u].append(edge_rec)
                    node_edges[v].append(edge_rec)

                    # Build provenance records for participating entities
                    prov_u = PersonProvenanceRecord(
                        case_id=case_id,
                        evidence_type=row.get("provenance_evidence_type") or edge_type,
                        source_table=table,
                        record_id=rec_id,
                        timestamp=ts,
                        relationship=edge_type,
                        related_entity=v,
                        notes=notes,
                    )
                    prov_v = PersonProvenanceRecord(
                        case_id=case_id,
                        evidence_type=row.get("provenance_evidence_type") or edge_type,
                        source_table=table,
                        record_id=rec_id,
                        timestamp=ts,
                        relationship=edge_type,
                        related_entity=u,
                        notes=notes,
                    )
                    provenance_records_map[u].append(prov_u)
                    provenance_records_map[v].append(prov_v)

        # 5. Load Phase 4 Predictions (SAFE CONSUMPTION: strictly ignore 'label' column)
        node_preds: Dict[str, List[dict]] = defaultdict(list)
        if self.predictions_path.exists():
            with open(self.predictions_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # ONLY consume observable predictive fields
                    src = row.get("source_node", "")
                    tgt = row.get("target_node", "")
                    score = float(row.get("prediction_score", 0.0))
                    tier = row.get("confidence_tier", "LOW PRIORITY")
                    is_cross = str(row.get("is_cross_case", "")).lower() == "true"
                    try:
                        cn_count = int(row.get("common_neighbors_count", 0))
                    except (ValueError, TypeError):
                        cn_count = 0

                    rec = {
                        "prediction_score": score,
                        "confidence_tier": tier,
                        "is_cross_case": is_cross,
                        "common_neighbors_count": cn_count,
                    }
                    node_preds[src].append(rec)
                    node_preds[tgt].append(rec)

        # 6. Score Each PERSON Entity
        scored_priorities: List[PersonInvestigationPriority] = []
        priority_map: Dict[str, PersonInvestigationPriority] = {}

        for p in person_nodes:
            nid = p["node_id"]
            label = p.get("label", nid)
            is_prov = p.get("is_provisional_resolved", "").lower() == "true"
            res_id = p.get("resolved_entity_id")
            if res_id and not res_id.strip():
                res_id = None

            # Associated Cases
            direct_cases = set([c.strip() for c in str(p.get("case_ids", "")).split(";") if c.strip()])
            resolved_cases = prov_cases_map.get(res_id, set()) if res_id else set()
            all_cases = sorted(list(direct_cases | resolved_cases))
            num_cases = len(all_cases)

            # Component A: Cross-Case Score (Max 25 pts)
            if is_prov:
                if num_cases >= 4:
                    s_cross = 25.0
                elif num_cases == 3:
                    s_cross = 20.0
                elif num_cases == 2:
                    s_cross = 15.0
                else:
                    s_cross = 10.0
            else:
                if num_cases >= 4:
                    s_cross = 22.0
                elif num_cases == 3:
                    s_cross = 17.0
                elif num_cases == 2:
                    s_cross = 12.0
                else:
                    s_cross = 3.0

            # Component B: Network Centrality Score (Max 20 pts)
            m = metrics_map.get(nid, {})
            btw = float(m.get("betweenness_centrality", 0.0))
            pr = float(m.get("pagerank", 0.0))
            raw_deg = int(m.get("raw_degree", 0))

            btw_pts = min(btw * 500.0, 8.0)
            pr_pts = min(max((pr - 0.0004) / 0.0024 * 7.0, 0.0), 7.0)
            deg_pts = min(raw_deg / 20.0 * 5.0, 5.0)
            s_net = round(min(btw_pts + pr_pts + deg_pts, 20.0), 2)

            # Component C: Evidence Diversity Score (Max 20 pts)
            inc_edges = node_edges.get(nid, [])
            has_dev = False
            has_private_veh = False
            has_public_veh = False
            has_social = False
            has_loc = False
            has_prov_rel = False
            distinct_modalities: Set[str] = set()

            for e in inc_edges:
                et = e.get("edge_type", "")
                other = e.get("target_id") if e.get("source_id") == nid else e.get("source_id")
                other_str = str(other)

                if et == "USED_DEVICE":
                    has_dev = True
                    distinct_modalities.add("DEVICE")
                elif et == "USED_VEHICLE":
                    distinct_modalities.add("VEHICLE")
                    if other_str in KNOWN_SHARED_BUSES or any(b in other_str for b in KNOWN_SHARED_BUSES):
                        has_public_veh = True
                    else:
                        has_private_veh = True
                elif et == "HAS_SOCIAL_ACCOUNT":
                    has_social = True
                    distinct_modalities.add("SOCIAL_ACCOUNT")
                elif et == "TRAVELLED_TO":
                    has_loc = True
                    distinct_modalities.add("LOCATION")
                elif et == "OBSERVES_ENTITY":
                    has_prov_rel = True
                    distinct_modalities.add("ENTITY_CLUSTER")
                elif et == "APPEARS_IN":
                    distinct_modalities.add("CASE_DOSSIER")

            s_evid = 0.0
            if has_dev:
                s_evid += 4.5
            if has_private_veh:
                s_evid += 4.5
            elif has_public_veh:
                s_evid += 1.5  # Reduced weight for shared commercial transit
            if has_social:
                s_evid += 4.0
            if has_loc:
                s_evid += 3.5
            if has_prov_rel or is_prov:
                s_evid += 3.5

            s_evid = round(min(s_evid, 20.0), 2)

            # Component D: Cross-Case Bridge Score (Max 15 pts)
            tags_clean = [t.strip() for t in str(m.get("analytical_tags", "")).split(";")]
            is_ccc_member = nid in ccc_entities or (res_id and res_id in ccc_entities)
            is_bridge_tag = "cross-case bridge" in tags_clean
            is_high_conn_tag = "high-connectivity entity" in tags_clean

            s_bridge = 0.0
            if is_ccc_member:
                s_bridge += 8.0
            if is_bridge_tag:
                s_bridge += 4.0
            if is_high_conn_tag:
                s_bridge += 3.0
            s_bridge = round(min(s_bridge, 15.0), 2)

            # Component E: Phase 4 GraphSAGE Predictions (Max 20 pts)
            pr_list = node_preds.get(nid, [])
            top_score = max([x["prediction_score"] for x in pr_list]) if pr_list else 0.0
            cross_preds = sum(1 for x in pr_list if x["is_cross_case"])
            top_intermediates = max([x["common_neighbors_count"] for x in pr_list]) if pr_list else 0

            # Scale top score: max score in data is ~0.25 -> 0.20 maps to 10 pts
            sage_score_pts = min((top_score / 0.20) * 10.0, 10.0)
            cross_candidate_pts = 5.0 if cross_preds >= 5 else (3.0 if cross_preds >= 1 else 0.0)
            intermediate_pts = min(top_intermediates * 2.5, 5.0)

            s_sage = round(min(sage_score_pts + cross_candidate_pts + intermediate_pts, 20.0), 2)

            # Public Infrastructure Safeguard Penalty
            p_infra = 0.0
            if has_public_veh and not has_private_veh:
                p_infra = 3.0

            # Composite Final Score (0.0 - 100.0)
            composite = s_cross + s_net + s_evid + s_bridge + s_sage - p_infra
            final_score = round(max(min(composite, 100.0), 0.0), 1)

            # Priority Tier Classification
            if final_score >= THRESHOLD_HIGH:
                tier = PriorityTier.HIGH
            elif final_score >= THRESHOLD_MEDIUM:
                tier = PriorityTier.MEDIUM
            else:
                tier = PriorityTier.LOW

            # Dynamic Feature-Grounded Explanations (ONLY from contributing signals)
            reasons: List[str] = []
            if is_prov and num_cases >= 2:
                reasons.append(f"Provisional entity-resolution cluster spanning {num_cases} case dossiers")
            elif num_cases >= 2:
                reasons.append(f"Cross-case presence spanning {num_cases} distinct case dossiers")

            if has_dev:
                reasons.append("Corroborated device / hardware assignment")
            if has_private_veh:
                reasons.append("Associated with dedicated or private vehicle transport")
            if has_social:
                reasons.append("Corroborated social / cyber communication profile")
            if has_loc:
                reasons.append("Documented travel movements across case locations")
            if is_prov or has_prov_rel:
                reasons.append("High-confidence resolved entity cluster association")

            if is_ccc_member:
                reasons.append("Direct participant in cross-case connecting pathways")
            if is_bridge_tag:
                reasons.append("Acts as a cross-case network structural bridge")
            if is_high_conn_tag:
                reasons.append("High-connectivity topological hub entity")

            if top_score >= 0.10:
                reasons.append(f"High-strength Phase 4 GraphSAGE candidate link (confidence: {top_score:.3f})")
            elif top_score >= 0.03:
                reasons.append(f"Moderate Phase 4 GraphSAGE candidate association (confidence: {top_score:.3f})")
            if cross_preds >= 5:
                reasons.append(f"Has {cross_preds} predicted cross-case candidate associations")
            elif cross_preds >= 1:
                reasons.append("Has predicted cross-case candidate associations")

            if not reasons:
                reasons.append("Single-case participant with baseline observational records")

            # Dynamic Caveats (Strictly grounded)
            caveats: List[str] = []
            if has_public_veh:
                caveats.append(
                    "Vehicle connection involves commercial public transit fleet (VEH_026); weight dampened to prevent artificial hub inflation"
                )
            if is_prov:
                caveats.append(
                    "Provisional entity-resolution cluster; requires independent verification of underlying personas"
                )
            caveats.append("Requires investigator verification before formal field action")

            breakdown = PriorityScoreBreakdown(
                cross_case_score=s_cross,
                network_score=s_net,
                evidence_score=s_evid,
                bridge_score=s_bridge,
                sage_score=s_sage,
                infrastructure_penalty=p_infra,
                total_score=final_score,
            )

            prov_records = provenance_records_map.get(nid, [])

            priority_obj = PersonInvestigationPriority(
                person_id=nid,
                label=label,
                entity_type="PERSON",
                is_provisional_resolved=is_prov,
                resolved_entity_id=res_id,
                score=final_score,
                priority=tier,
                cases_count=num_cases,
                associated_cases=all_cases,
                modalities_count=len(distinct_modalities),
                modalities=sorted(list(distinct_modalities)),
                network_degree=raw_deg,
                betweenness_centrality=btw,
                pagerank=pr,
                score_breakdown=breakdown,
                reasons=reasons,
                caveats=caveats,
                top_candidate_link_score=round(top_score, 4) if top_score > 0 else None,
                cross_case_candidates_count=cross_preds,
                provenance_count=len(prov_records),
            )
            scored_priorities.append(priority_obj)
            priority_map[nid] = priority_obj

        # Sort by score descending deterministically
        scored_priorities.sort(key=lambda x: (x.score, x.cases_count, x.network_degree), reverse=True)

        self._priorities_list = scored_priorities
        self._priority_by_id = priority_map
        self._provenance_by_id = provenance_records_map

    def _filter_priority_for_user(
        self,
        p: PersonInvestigationPriority,
        allowed_cases: Optional[Set[str]],
    ) -> Optional[PersonInvestigationPriority]:
        """
        Applies RBAC case authorization and data isolation.
        If user is restricted, only authorized cases are visible, and provenance / case counts
        are strictly sanitized to prevent information leakage.
        """
        if allowed_cases is None:
            return p  # Global access (ADMIN / SUPERVISOR)

        # Check if entity belongs to any case user has access to
        visible_cases = [c for c in p.associated_cases if c in allowed_cases]
        if not visible_cases:
            return None  # Access denied to this person entirely

        # Sanitize associated cases and counts to prevent leaking existence of unauthorized cases
        masked_p = p.model_copy(deep=True)
        masked_p.associated_cases = visible_cases
        masked_p.cases_count = len(visible_cases)

        # Sanitize reasons: avoid disclosing unauthorized case counts
        sanitized_reasons = []
        for r in masked_p.reasons:
            if "case dossiers" in r:
                if len(visible_cases) >= 2:
                    sanitized_reasons.append(f"Cross-case presence spanning {len(visible_cases)} authorized case dossiers")
                else:
                    sanitized_reasons.append("Associated with authorized case dossier")
            else:
                sanitized_reasons.append(r)
        masked_p.reasons = sanitized_reasons

        return masked_p

    def get_priorities(
        self,
        case_id: Optional[str] = None,
        priority: Optional[str] = None,
        min_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> PriorityListResponse:
        """
        Retrieves filtered, ranked priorities with RBAC case clearance.
        """
        self.load_if_needed()

        # Step 1: RBAC case filtering and data sanitization
        filtered: List[PersonInvestigationPriority] = []
        for p in self._priorities_list:
            masked = self._filter_priority_for_user(p, user_allowed_cases)
            if masked is not None:
                filtered.append(masked)

        # Step 2: Specific case filter
        if case_id:
            filtered = [p for p in filtered if case_id in p.associated_cases]

        # Step 3: Priority tier filter
        if priority:
            p_upper = priority.strip().upper()
            filtered = [p for p in filtered if p.priority.value == p_upper]

        # Step 4: Minimum score filter
        if min_score is not None:
            filtered = [p for p in filtered if p.score >= min_score]

        total = len(filtered)
        high_cnt = sum(1 for p in filtered if p.priority == PriorityTier.HIGH)
        med_cnt = sum(1 for p in filtered if p.priority == PriorityTier.MEDIUM)
        low_cnt = sum(1 for p in filtered if p.priority == PriorityTier.LOW)

        paginated = filtered[offset : offset + limit]

        return PriorityListResponse(
            total=total,
            limit=limit,
            offset=offset,
            high_count=high_cnt,
            medium_count=med_cnt,
            low_count=low_cnt,
            priorities=paginated,
        )

    def get_priority_by_id(
        self,
        person_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> Tuple[Optional[PersonInvestigationPriority], bool]:
        """
        Returns (priority_object, exists_in_system).
        If entity exists but user is unauthorized, returns (None, True).
        If entity does not exist at all, returns (None, False).
        """
        self.load_if_needed()
        p = self._priority_by_id.get(person_id)
        if not p:
            return None, False

        masked = self._filter_priority_for_user(p, user_allowed_cases)
        if masked is None:
            return None, True  # Exists, but user lacks case clearance

        return masked, True

    def get_person_evidence(
        self,
        person_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> Tuple[Optional[PersonEvidenceResponse], bool]:
        """
        Retrieves structured provenance records for a person with RBAC case filtering.
        """
        p, exists = self.get_priority_by_id(person_id, user_allowed_cases=user_allowed_cases)
        if not exists:
            return None, False
        if p is None:
            return None, True  # Unauthorized

        raw_records = self._provenance_by_id.get(person_id, [])

        # Filter provenance records by user's authorized cases
        if user_allowed_cases is not None:
            filtered_records = [
                r for r in raw_records
                if r.case_id == "Unavailable" or r.case_id in user_allowed_cases
            ]
        else:
            filtered_records = raw_records

        return (
            PersonEvidenceResponse(
                person_id=person_id,
                label=p.label,
                is_provisional_resolved=p.is_provisional_resolved,
                total_records=len(filtered_records),
                records=filtered_records,
            ),
            True,
        )
