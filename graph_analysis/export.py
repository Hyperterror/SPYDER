"""
Export Module for Global Case Knowledge Graph.
Dumps graph artifacts, node metrics, community summaries, and cross-case connections
into CSV and JSON formats in output/graph_analysis/.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any
import networkx as nx

from graph_analysis.config import OUTPUT_DIR
from graph_analysis.schema import GraphNode, GraphEdge, CrossCaseConnection

class GraphExporter:
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_nodes_csv(self, nodes: Dict[str, GraphNode]):
        """Exports nodes.csv with attributes and case memberships."""
        csv_path = self.output_dir / "nodes.csv"
        fieldnames = ["node_id", "node_type", "label", "case_ids", "resolved_entity_id", "is_provisional_resolved", "priority_status"]
        
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for n_id, node in nodes.items():
                row = node.to_dict()
                row["case_ids"] = "; ".join(row.get("case_ids", []))
                writer.writerow(row)

    def export_edges_csv(self, edges: List[GraphEdge]):
        """Exports edges.csv with full provenance and context-aware weights."""
        csv_path = self.output_dir / "edges.csv"
        fieldnames = [
            "source_id", "target_id", "edge_type", "timestamp", "weight",
            "provenance_table", "provenance_record_id", "provenance_case_id",
            "provenance_evidence_type", "provenance_confidence", "notes"
        ]
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for e in edges:
                writer.writerow(e.to_dict())

    def export_case_graph_json(self, multi_graph: nx.MultiDiGraph):
        """Exports complete case graph in Node-Link JSON format."""
        json_path = self.output_dir / "case_graph.json"
        data = nx.node_link_data(multi_graph)
        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def export_cross_case_connections_csv(self, connections: List[CrossCaseConnection]):
        """Exports cross_case_connections.csv sorted by priority and score."""
        csv_path = self.output_dir / "cross_case_connections.csv"
        fieldnames = [
            "source_case", "target_case", "tier", "score", "path_length",
            "connecting_entities", "relationship_types", "supporting_evidence_count",
            "earliest_timestamp", "latest_timestamp", "path", "reasons", "explanation"
        ]
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for conn in connections:
                writer.writerow(conn.to_dict())

    def export_node_metrics_csv(self, metrics: List[Dict[str, Any]]):
        """Exports node_metrics.csv containing centrality rankings."""
        csv_path = self.output_dir / "node_metrics.csv"
        if not metrics:
            return
        fieldnames = list(metrics[0].keys())
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for m in metrics:
                writer.writerow(m)

    def export_communities_csv(self, communities: List[Dict[str, Any]]):
        """Exports communities.csv containing investigative clusters."""
        csv_path = self.output_dir / "communities.csv"
        if not communities:
            return
        fieldnames = [
            "community_id", "cluster_label", "analytical_classification", "total_nodes",
            "num_persons", "num_cases", "cases_represented", "cross_case_bridges_count",
            "cross_case_bridge_nodes", "top_connected_nodes", "mean_internal_degree", "evidence_modalities"
        ]
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for comm in communities:
                writer.writerow(comm)

    def export_graph_summary_json(self, summary_stats: Dict[str, Any]):
        """Exports graph_summary.json with high-level structural counts."""
        json_path = self.output_dir / "graph_summary.json"
        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(summary_stats, f, indent=2, ensure_ascii=False)
