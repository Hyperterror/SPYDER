"""
Graph Loader for Phase 4.
Loads the frozen Phase 3 Knowledge Graph from output/graph_analysis/, maintaining
all 10 node types, edge types, weights, timestamps, and provenance records.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional
import networkx as nx
import torch

from phase4.config import NODES_PATH, EDGES_PATH, CASE_GRAPH_PATH

class GraphLoader:
    def __init__(
        self,
        nodes_path: Path = NODES_PATH,
        edges_path: Path = EDGES_PATH,
        case_graph_path: Path = CASE_GRAPH_PATH
    ):
        self.nodes_path = Path(nodes_path)
        self.edges_path = Path(edges_path)
        self.case_graph_path = Path(case_graph_path)

        self.multi_graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.node_to_idx: Dict[str, int] = {}
        self.idx_to_node: Dict[int, str] = {}
        self.node_types: Dict[str, str] = {}
        self.node_cases: Dict[str, Set[str]] = {}

    def load_graph(self) -> nx.MultiDiGraph:
        """
        Loads the graph from nodes.csv and edges.csv, establishing integer indices.
        """
        # 1. Load Nodes
        idx = 0
        with open(self.nodes_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                n_id = row["node_id"]
                ntype = row["node_type"]
                cases = set(row["case_ids"].split("; ")) if row.get("case_ids") else set()
                cases = {c.strip() for c in cases if c.strip()}

                self.node_to_idx[n_id] = idx
                self.idx_to_node[idx] = n_id
                self.node_types[n_id] = ntype
                self.node_cases[n_id] = cases

                self.multi_graph.add_node(
                    n_id,
                    node_idx=idx,
                    node_type=ntype,
                    label=row.get("label", n_id),
                    case_ids=cases,
                    resolved_entity_id=row.get("resolved_entity_id"),
                    is_provisional_resolved=row.get("is_provisional_resolved") == "True"
                )
                idx += 1

        # 2. Load Edges
        with open(self.edges_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                u = row["source_id"]
                v = row["target_id"]
                etype = row["edge_type"]
                weight = float(row.get("weight") or 1.0)
                ts = row.get("timestamp")
                case_id = row.get("provenance_case_id")
                table = row.get("provenance_table")
                rec_id = row.get("provenance_record_id")

                # Handle nodes not in nodes.csv gracefully
                for node_id in [u, v]:
                    if node_id not in self.node_to_idx:
                        self.node_to_idx[node_id] = idx
                        self.idx_to_node[idx] = node_id
                        self.node_types[node_id] = "UNKNOWN"
                        self.node_cases[node_id] = {case_id} if case_id else set()
                        self.multi_graph.add_node(
                            node_id,
                            node_idx=idx,
                            node_type="UNKNOWN",
                            label=node_id,
                            case_ids=self.node_cases[node_id]
                        )
                        idx += 1

                self.multi_graph.add_edge(
                    u, v,
                    edge_type=etype,
                    weight=weight,
                    timestamp=ts,
                    provenance_table=table,
                    provenance_record_id=rec_id,
                    provenance_case_id=case_id,
                    notes=row.get("notes")
                )

        # Enrich edges with detailed attributes (e.g. ip_address, location) from case_graph.json if available
        if self.case_graph_path.exists():
            try:
                with open(self.case_graph_path, mode="r", encoding="utf-8") as f:
                    cg_data = json.load(f)
                for e in cg_data.get("edges", []):
                    u = e.get("source_id")
                    v = e.get("target_id")
                    if u and v and self.multi_graph.has_edge(u, v):
                        for k, d in self.multi_graph[u][v].items():
                            for attr in ["ip_address", "location"]:
                                if attr in e and attr not in d:
                                    d[attr] = e[attr]
            except Exception:
                pass

        return self.multi_graph

    def get_person_nodes(self) -> List[str]:
        """Returns all PERSON and provisional resolved entity nodes."""
        return [
            n for n, d in self.multi_graph.nodes(data=True)
            if d.get("node_type") == "PERSON"
        ]

    def build_masked_graph(
        self,
        excluded_edges: Optional[Set[Tuple[str, str]]] = None,
    ) -> nx.MultiDiGraph:
        """
        Constructs a copy of multi_graph with all excluded_edges removed (treated as undirected pairs).
        Used to guarantee zero held-out target-edge leakage during message passing & baseline scoring.
        """
        if not excluded_edges:
            return self.multi_graph.copy()

        masked = nx.MultiDiGraph()
        for n, d in self.multi_graph.nodes(data=True):
            masked.add_node(n, **dict(d))

        for u, v, d in self.multi_graph.edges(data=True):
            canon = (u, v) if u <= v else (v, u)
            if canon in excluded_edges or (u, v) in excluded_edges or (v, u) in excluded_edges:
                continue
            masked.add_edge(u, v, **dict(d))
        return masked

    def build_normalized_adj(
        self,
        excluded_edges: Optional[Set[Tuple[str, str]]] = None,
        graph: Optional[nx.MultiDiGraph] = None,
    ) -> torch.Tensor:
        """
        Builds a row-normalized adjacency matrix for GraphSAGE neighborhood aggregation.
        When excluded_edges is provided, masks those target edges to prevent evaluation leakage.
        """
        num_nodes = len(self.node_to_idx)
        adj = torch.zeros((num_nodes, num_nodes), dtype=torch.float32)
        src_graph = graph if graph is not None else self.multi_graph

        for u, v, d in src_graph.edges(data=True):
            if excluded_edges:
                canon = (u, v) if u <= v else (v, u)
                if canon in excluded_edges or (u, v) in excluded_edges or (v, u) in excluded_edges:
                    continue
            uidx = self.node_to_idx[u]
            vidx = self.node_to_idx[v]
            w = float(d.get("weight", 1.0))
            # Undirected message passing for representation learning
            adj[uidx, vidx] = max(adj[uidx, vidx].item(), w)
            adj[vidx, uidx] = max(adj[vidx, uidx].item(), w)

        # Add self-loops
        adj.fill_diagonal_(1.0)

        # Row normalize
        deg = adj.sum(dim=1, keepdim=True)
        deg[deg == 0] = 1.0
        norm_adj = adj / deg
        return norm_adj
