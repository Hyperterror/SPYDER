"""
Centrality and Network Metrics Module.
Calculates degree, betweenness, and PageRank metrics using standard graph algorithms,
identifying high-connectivity nodes and cross-case bridges with neutral analytical terminology.
"""

from typing import Dict, List, Set, Any, Optional
import networkx as nx

class CentralityAnalyzer:
    def __init__(self, multi_graph: nx.MultiDiGraph, projected_graph: nx.Graph):
        self.multi_graph = multi_graph
        self.projected_graph = projected_graph

    def calculate_node_metrics(self) -> List[Dict[str, Any]]:
        """
        Computes network centrality metrics on the projected graph for all nodes,
        with deep analytical profiling for PERSON and provisional resolved entity nodes.
        """
        # Centrality algorithms
        degree_dict = dict(self.projected_graph.degree())
        degree_centrality = nx.degree_centrality(self.projected_graph)
        
        # Betweenness centrality (using weight if available)
        try:
            betweenness = nx.betweenness_centrality(self.projected_graph, weight="weight", normalized=True)
        except Exception:
            betweenness = nx.betweenness_centrality(self.projected_graph, normalized=True)

        # PageRank
        try:
            pagerank = nx.pagerank(self.projected_graph, weight="weight", alpha=0.85)
        except Exception:
            pagerank = {n: 1.0 / self.projected_graph.number_of_nodes() for n in self.projected_graph.nodes()}

        results = []
        for n_id, data in self.projected_graph.nodes(data=True):
            n_type = data.get("node_type", "UNKNOWN")
            raw_degree = degree_dict.get(n_id, 0)
            deg_cent = degree_centrality.get(n_id, 0.0)
            btw = betweenness.get(n_id, 0.0)
            pr = pagerank.get(n_id, 0.0)

            # Analyze multi-case association
            case_ids = data.get("case_ids", [])
            if isinstance(case_ids, set):
                case_ids = list(case_ids)
            
            # Count distinct cases from incident edges
            incident_cases = set(case_ids)
            for neighbor in self.projected_graph.neighbors(n_id):
                nbr_cases = self.projected_graph.nodes[neighbor].get("case_ids", [])
                incident_cases.update(nbr_cases)

            # Classify analytical role (strictly neutral, non-prejudicial terminology)
            analytical_tags = []
            is_cross_case_bridge = len(incident_cases) >= 2
            
            if is_cross_case_bridge:
                analytical_tags.append("cross-case bridge")
            
            if deg_cent > 0.02 or raw_degree >= 8:
                analytical_tags.append("high-connectivity entity")
            
            if btw > 0.01:
                analytical_tags.append("high-betweenness conduit")

            if not analytical_tags:
                analytical_tags.append("local case participant")

            priority_status = "ROUTINE"
            if "cross-case bridge" in analytical_tags and "high-connectivity entity" in analytical_tags:
                priority_status = "high-priority investigative lead"
            elif is_cross_case_bridge:
                priority_status = "cross-case priority review"

            results.append({
                "node_id": n_id,
                "node_type": n_type,
                "label": data.get("label", n_id),
                "case_count": len(incident_cases),
                "case_ids": "; ".join(sorted(list(incident_cases))),
                "raw_degree": raw_degree,
                "degree_centrality": round(deg_cent, 6),
                "betweenness_centrality": round(btw, 6),
                "pagerank": round(pr, 6),
                "analytical_tags": "; ".join(analytical_tags),
                "priority_status": priority_status,
                "is_provisional_resolved": data.get("is_provisional_resolved", False)
            })

        # Sort by PageRank descending
        results.sort(key=lambda x: x["pagerank"], reverse=True)
        return results

    def get_top_entities_by_metric(
        self, metric_name: str = "pagerank", node_type: str = "PERSON", top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Retrieves top-k nodes of specified type ranked by metric."""
        all_metrics = self.calculate_node_metrics()
        filtered = [m for m in all_metrics if m["node_type"] == node_type]
        filtered.sort(key=lambda x: x.get(metric_name, 0.0), reverse=True)
        return filtered[:top_k]
