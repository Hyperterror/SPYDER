"""
Temporal Graph Engine for Global Case Knowledge Graph.
Provides time-window filtering, event-centered analysis, and multi-case chronological tracking.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Set, Any, Optional, Tuple
import networkx as nx

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
]

def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses timestamp string safely without inventing dates."""
    if not ts_str:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    return None

class TemporalEngine:
    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph

    def filter_subgraph_by_time(self, start_time: str, end_time: str) -> nx.MultiDiGraph:
        """
        Extracts a temporal slice of the Knowledge Graph between start_time and end_time.
        Edges without timestamps are retained if they represent structural affiliations
        (e.g., APPEARS_IN, OBSERVES_ENTITY) unless explicitly excluded.
        """
        dt_start = parse_timestamp(start_time)
        dt_end = parse_timestamp(end_time)

        sub_g = nx.MultiDiGraph()

        # Copy nodes
        for n, d in self.graph.nodes(data=True):
            sub_g.add_node(n, **d)

        # Filter edges
        for u, v, k, data in self.graph.edges(keys=True, data=True):
            ts = parse_timestamp(data.get("timestamp"))
            if ts:
                if dt_start and ts < dt_start:
                    continue
                if dt_end and ts > dt_end:
                    continue
                sub_g.add_edge(u, v, key=k, **data)
            else:
                # Structural edges without timestamp
                sub_g.add_edge(u, v, key=k, **data)

        # Remove isolated nodes with degree 0
        isolates = list(nx.isolates(sub_g))
        sub_g.remove_nodes_from(isolates)
        return sub_g

    def get_connections_around_incident(
        self, incident_time: str, pre_days: int = 7, post_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all person-to-person and communication interactions occurring
        within [incident_time - pre_days, incident_time + post_days].
        """
        inc_dt = parse_timestamp(incident_time)
        if not inc_dt:
            return []

        start_dt = inc_dt - timedelta(days=pre_days)
        end_dt = inc_dt + timedelta(days=post_days)

        active_edges = []
        for u, v, k, data in self.graph.edges(keys=True, data=True):
            ts = parse_timestamp(data.get("timestamp"))
            if ts and start_dt <= ts <= end_dt:
                active_edges.append({
                    "source": u,
                    "target": v,
                    "edge_type": data.get("edge_type"),
                    "timestamp": data.get("timestamp"),
                    "case_id": data.get("provenance_case_id"),
                    "evidence_table": data.get("provenance_table"),
                    "evidence_id": data.get("provenance_record_id"),
                    "weight": data.get("weight"),
                    "notes": data.get("notes")
                })

        active_edges.sort(key=lambda x: x["timestamp"] or "")
        return active_edges

    def find_entities_connecting_cases_in_window(
        self, case_a: str, case_b: str, max_window_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Identifies entities that were active in both case_a and case_b within
        a constrained time window.
        """
        # Find all edges belonging to case_a and case_b
        edges_a = [d for _, _, d in self.graph.edges(data=True) if d.get("provenance_case_id") == case_a and d.get("timestamp")]
        edges_b = [d for _, _, d in self.graph.edges(data=True) if d.get("provenance_case_id") == case_b and d.get("timestamp")]

        if not edges_a or not edges_b:
            return []

        # Compare timestamps for shared or connected entities
        cross_temporal_links = []
        for ea in edges_a:
            ta = parse_timestamp(ea["timestamp"])
            if not ta:
                continue
            for eb in edges_b:
                tb = parse_timestamp(eb["timestamp"])
                if not tb:
                    continue
                diff_days = abs((ta - tb).total_seconds()) / 86400.0
                if diff_days <= max_window_days:
                    cross_temporal_links.append({
                        "case_a": case_a,
                        "case_b": case_b,
                        "record_a": ea["provenance_record_id"],
                        "record_b": eb["provenance_record_id"],
                        "timestamp_a": ea["timestamp"],
                        "timestamp_b": eb["timestamp"],
                        "day_difference": round(diff_days, 1),
                        "modality_a": ea.get("edge_type"),
                        "modality_b": eb.get("edge_type")
                    })

        return cross_temporal_links

    def get_chronological_timeline_for_entity(self, entity_id: str) -> List[Dict[str, Any]]:
        """
        Builds a strictly chronological activity timeline for any node (person, device, vehicle, etc.).
        """
        timeline = []
        # Inward and outward edges
        for u, v, k, data in self.graph.in_edges(entity_id, keys=True, data=True):
            if data.get("timestamp"):
                timeline.append({
                    "timestamp": data["timestamp"],
                    "direction": "INCOMING",
                    "counterparty": u,
                    "edge_type": data.get("edge_type"),
                    "case_id": data.get("provenance_case_id"),
                    "table": data.get("provenance_table"),
                    "record_id": data.get("provenance_record_id"),
                    "notes": data.get("notes")
                })

        for u, v, k, data in self.graph.out_edges(entity_id, keys=True, data=True):
            if data.get("timestamp"):
                timeline.append({
                    "timestamp": data["timestamp"],
                    "direction": "OUTGOING",
                    "counterparty": v,
                    "edge_type": data.get("edge_type"),
                    "case_id": data.get("provenance_case_id"),
                    "table": data.get("provenance_table"),
                    "record_id": data.get("provenance_record_id"),
                    "notes": data.get("notes")
                })

        timeline.sort(key=lambda x: x["timestamp"])
        return timeline
