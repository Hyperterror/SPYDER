"""
Cross-Case Connection Discovery and Scoring Engine.
Discovers multi-hop evidence trails linking disparate CASE dossiers, evaluates context-aware
connection strength, assigns investigative priority tiers, and generates human-readable rationales.
"""

from typing import Dict, List, Set, Any, Tuple, Optional
import networkx as nx

from graph_analysis.config import (
    MAX_CROSS_CASE_PATH_HOPS, SCORE_WEIGHTS, TIER_HIGH_PRIORITY,
    TIER_REVIEW, TIER_LOW_PRIORITY, THRESHOLD_HIGH_PRIORITY, THRESHOLD_REVIEW,
    KNOWN_PUBLIC_IPS, KNOWN_PUBLIC_ACCOUNTS, KNOWN_PUBLIC_PHONES
)
from graph_analysis.schema import CrossCaseConnection
from graph_analysis.explanations import generate_cross_case_explanation

class CrossCaseDetector:
    def __init__(self, multi_graph: nx.MultiDiGraph, projected_graph: nx.Graph):
        self.multi_graph = multi_graph
        self.projected_graph = projected_graph
        self.case_nodes = [n for n, d in self.projected_graph.nodes(data=True) if d.get("node_type") == "CASE"]

    def _score_connection(
        self,
        path: List[str],
        supporting_evidence: List[Dict[str, Any]],
        timestamps: List[str]
    ) -> Tuple[float, str, List[str]]:
        """
        Calculates a multi-factor, context-aware connection score according to Safeguard 2.
        Returns: (score, priority_tier, human_readable_reasons)
        """
        reasons = []

        # 1. Evidence Diversity Score (0.0 to 1.0)
        tables = set()
        for ev in supporting_evidence:
            tbl = ev.get("table") or ev.get("source_table")
            if tbl:
                tables.add(tbl)

        num_tables = len(tables)
        if num_tables >= 4:
            diversity_score = 1.0
            reasons.append(f"Strong multi-modal corroboration across {num_tables} distinct evidence sources")
        elif num_tables == 3:
            diversity_score = 0.85
            reasons.append("Corroborated across 3 independent evidence tables")
        elif num_tables == 2:
            diversity_score = 0.65
            reasons.append("Supported by 2 evidence tables")
        else:
            diversity_score = 0.35
            reasons.append("Single evidence modality trail")

        # 2. Relationship Strength & Interaction Recurrence
        weights = [ev.get("confidence", 0.7) for ev in supporting_evidence]
        avg_weight = sum(weights) / len(weights) if weights else 0.5
        rec_count = len(supporting_evidence)
        if rec_count >= 10:
            recurrence_boost = 1.0
            reasons.append(f"High interaction frequency ({rec_count} corroborating records)")
        elif rec_count >= 3:
            recurrence_boost = 0.8
            reasons.append(f"Repeated evidence records ({rec_count} entries)")
        else:
            recurrence_boost = 0.5

        strength_score = 0.7 * avg_weight + 0.3 * recurrence_boost

        # 3. Context-Aware Identifier Reliability (Safeguard 2)
        # Check intermediate nodes for public infrastructure or high fan-out
        has_public_infrastructure = False
        has_high_fanout = False
        has_hardware_signature = False
        has_provisional_resolved_entity = False

        intermediate_nodes = path[1:-1]
        for node in intermediate_nodes:
            # Check public infrastructure
            if node in KNOWN_PUBLIC_IPS or node in KNOWN_PUBLIC_ACCOUNTS or node in KNOWN_PUBLIC_PHONES:
                has_public_infrastructure = True
            
            # Check node attributes
            ndata = self.projected_graph.nodes.get(node, {})
            ntype = ndata.get("node_type", "UNKNOWN")

            if ndata.get("is_hardware_imei") or "IMEI_" in node:
                has_hardware_signature = True
            if ndata.get("is_provisional_resolved") or "PROV_RES_ENT" in node:
                has_provisional_resolved_entity = True

            # Degree / fan-out (for non-entity identifiers: vehicles, phones, accounts)
            deg = self.projected_graph.degree(node)
            cids = ndata.get("case_ids", [])
            if ntype in ["VEHICLE", "PHONE", "BANK_ACCOUNT"] and (deg >= 4 or len(cids) >= 3):
                has_high_fanout = True

        # 3. Temporal Consistency
        if timestamps and len(timestamps) >= 2:
            temporal_score = 0.85
            reasons.append(f"Temporal sequence documented across {len(timestamps)} timestamped events")
        elif timestamps:
            temporal_score = 0.60
            reasons.append("Partial timestamp corroboration")
        else:
            temporal_score = 0.40
            reasons.append("Structural association without active event timestamps")

        # 4. Context-Aware Identifier Reliability (Safeguard 2)
        if has_public_infrastructure:
            identifier_rel = 0.15
            reasons.append("Path relies on known public transit infrastructure (hotspot/public utility); reliability heavily discounted")
            diversity_score = min(diversity_score, 0.30)
        elif has_high_fanout:
            identifier_rel = 0.30
            reasons.append("Connecting identifier exhibits high fan-out across multiple cases (shared transit bus or fleet); moderate-to-low reliability")
            diversity_score = min(diversity_score, 0.40)
        elif has_provisional_resolved_entity:
            identifier_rel = 0.95
            reasons.append("Provisional entity-resolution cluster indicates high-confidence shared identity")
            diversity_score = max(diversity_score, 0.85)
            temporal_score = max(temporal_score, 0.80)
            strength_score = max(strength_score, 0.90)
        elif has_hardware_signature:
            identifier_rel = 0.92
            reasons.append("Direct hardware identifier (IMEI) provides high-confidence physical link")
            diversity_score = max(diversity_score, 0.80)
            strength_score = max(strength_score, 0.85)
        else:
            identifier_rel = 0.70

        # 5. Path Length & Ambiguity Penalty
        hops = len(path) - 1
        if hops == 2:
            base_factor = 1.0
            reasons.append("Direct cross-case connection via shared entity")
        elif hops == 3:
            base_factor = 0.95
            reasons.append("Direct cross-case link via intermediate entity")
        elif hops == 4:
            base_factor = 0.90
            reasons.append("Corroborated multi-step entity/device connection")
        else:
            base_factor = 0.75
            reasons.append("Extended multi-hop indirect trail")

        ambiguity_discount = 1.0
        if has_public_infrastructure:
            ambiguity_discount = 0.60
        elif has_high_fanout:
            ambiguity_discount = 0.75

        length_factor = base_factor * ambiguity_discount

        # Weighted composite score
        raw_score = (
            SCORE_WEIGHTS["evidence_diversity"] * diversity_score +
            SCORE_WEIGHTS["relationship_strength"] * strength_score +
            SCORE_WEIGHTS["identifier_reliability"] * identifier_rel +
            SCORE_WEIGHTS["temporal_consistency"] * temporal_score
        ) * length_factor

        final_score = max(0.05, min(0.99, raw_score))

        # Assign priority tier
        if final_score >= THRESHOLD_HIGH_PRIORITY:
            tier = TIER_HIGH_PRIORITY
        elif final_score >= THRESHOLD_REVIEW:
            tier = TIER_REVIEW
        else:
            tier = TIER_LOW_PRIORITY

        return final_score, tier, reasons

    def find_cross_case_connections(self, max_leads_per_pair: int = 5) -> List[CrossCaseConnection]:
        """
        Explores paths between every pair of distinct CASE nodes up to max hops,
        aggregates supporting evidence, and scores the leads.
        Intermediate nodes are strictly filtered to entity types (PERSON, PHONE, DEVICE,
        VEHICLE, BANK_ACCOUNT, SOCIAL_ACCOUNT). Ambient locations and evidence objects
        are excluded from serving as intermediate bridge entities.
        """
        connections = []
        cases = sorted(self.case_nodes)
        seen_case_pairs = set()

        # Permitted bridge node types
        allowed_intermediate_types = {
            "PERSON", "PHONE", "DEVICE", "VEHICLE", "BANK_ACCOUNT", "SOCIAL_ACCOUNT"
        }
        allowed_types = allowed_intermediate_types | {"CASE"}
        entity_subgraph = self.projected_graph.subgraph([
            n for n, d in self.projected_graph.nodes(data=True)
            if d.get("node_type") in allowed_types
        ])

        for i in range(len(cases)):
            for j in range(i + 1, len(cases)):
                c_a, c_b = cases[i], cases[j]
                pair_key = (c_a, c_b)
                if pair_key in seen_case_pairs:
                    continue
                seen_case_pairs.add(pair_key)

                try:
                    paths = list(nx.all_simple_paths(
                        entity_subgraph,
                        source=c_a,
                        target=c_b,
                        cutoff=MAX_CROSS_CASE_PATH_HOPS
                    ))
                except nx.NetworkXNoPath:
                    continue

                if not paths:
                    continue

                pair_connections = []
                for path in paths:
                    intermediates = path[1:-1]
                    
                    # Intermediates must be permitted entity types (no ambient locations or evidence items)
                    valid_intermediates = True
                    for n in intermediates:
                        ntype = self.projected_graph.nodes[n].get("node_type", "UNKNOWN")
                        if ntype not in allowed_intermediate_types:
                            valid_intermediates = False
                            break

                    if not valid_intermediates:
                        continue

                    # Collect supporting evidence from multi_graph
                    supporting_evidence = []
                    rel_types = set()
                    timestamps = []

                    for idx in range(len(path) - 1):
                        u, v = path[idx], path[idx + 1]
                        edges_uv = []
                        if self.multi_graph.has_edge(u, v):
                            for _, _, d in self.multi_graph.out_edges(u, data=True):
                                if d.get("target_id") == v or _ == v:
                                    edges_uv.append(d)
                        if self.multi_graph.has_edge(v, u):
                            for _, _, d in self.multi_graph.out_edges(v, data=True):
                                if d.get("target_id") == u or _ == u:
                                    edges_uv.append(d)

                        for ed in edges_uv:
                            rel_types.add(ed.get("edge_type", "CONNECTED"))
                            if ed.get("timestamp"):
                                timestamps.append(ed["timestamp"])
                            supporting_evidence.append({
                                "table": ed.get("provenance_table"),
                                "id": ed.get("provenance_record_id"),
                                "case": ed.get("provenance_case_id"),
                                "confidence": ed.get("weight", 0.7),
                                "notes": ed.get("notes")
                            })

                    score, tier, reasons = self._score_connection(path, supporting_evidence, timestamps)

                    explanation = generate_cross_case_explanation(
                        source_case=c_a,
                        target_case=c_b,
                        path_nodes=path,
                        relationship_types=list(rel_types),
                        supporting_evidence=supporting_evidence,
                        connecting_entities=intermediates,
                        tier=tier,
                        reasons=reasons
                    )

                    conn = CrossCaseConnection(
                        source_case=c_a,
                        target_case=c_b,
                        path=path,
                        connecting_entities=intermediates,
                        path_length=len(path) - 1,
                        relationship_types=sorted(list(rel_types)),
                        supporting_evidence=supporting_evidence,
                        timestamps=sorted(timestamps),
                        score=score,
                        tier=tier,
                        reasons=reasons,
                        explanation=explanation
                    )
                    pair_connections.append(conn)

                # Keep top leads for this pair
                pair_connections.sort(key=lambda x: x.score, reverse=True)
                connections.extend(pair_connections[:max_leads_per_pair])

        # Global sort by score descending
        connections.sort(key=lambda x: x.score, reverse=True)
        return connections
