"""
Feature Extractor for Phase 4.
Extracts purely observable, typed structural features for every node in the Knowledge Graph.
Strictly zero ground-truth leakage: no hidden roles, syndicates, or global IDs.
"""

import csv
import math
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
import networkx as nx
import numpy as np
import torch

from phase4.config import NODE_METRICS_PATH

ORDERED_NODE_TYPES = [
    "PERSON", "VICTIM", "CASE", "PHONE", "DEVICE",
    "VEHICLE", "BANK_ACCOUNT", "SOCIAL_ACCOUNT", "LOCATION", "EVIDENCE",
    "ORGANIZATION", "UNKNOWN"
]
TYPE_TO_IDX = {t: i for i, t in enumerate(ORDERED_NODE_TYPES)}

class FeatureExtractor:
    def __init__(self, node_metrics_path: Path = NODE_METRICS_PATH):
        self.node_metrics_path = Path(node_metrics_path)
        self.metrics_cache: Dict[str, Dict[str, float]] = {}
        self._load_metrics()

    def _load_metrics(self):
        """Loads centrality metrics from Phase 3 output/graph_analysis/node_metrics.csv."""
        if not self.node_metrics_path.exists():
            return
        with open(self.node_metrics_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                nid = row["node_id"]
                self.metrics_cache[nid] = {
                    "degree_centrality": float(row.get("degree_centrality") or 0.0),
                    "betweenness_centrality": float(row.get("betweenness_centrality") or 0.0),
                    "pagerank": float(row.get("pagerank") or 0.0),
                    "case_count": float(row.get("case_count") or 1.0),
                    "raw_degree": float(row.get("raw_degree") or 0.0)
                }

    def extract_node_features(
        self,
        multi_graph: nx.MultiDiGraph,
        node_to_idx: Dict[str, int]
    ) -> Tuple[torch.Tensor, List[str]]:
        """
        Extracts a normalized feature vector for each node in index order.
        Returns: (feature_tensor, feature_names)
        """
        num_nodes = len(node_to_idx)
        raw_features: List[List[float]] = []

        # Undirected projection for degree statistics
        undirected_g = multi_graph.to_undirected()

        for idx in range(num_nodes):
            nid = next(k for k, v in node_to_idx.items() if v == idx)
            ndata = multi_graph.nodes[nid]
            ntype = ndata.get("node_type", "UNKNOWN")

            row_feats = []

            # 1. One-hot node type (11 dims)
            type_one_hot = [0.0] * len(ORDERED_NODE_TYPES)
            type_idx = TYPE_TO_IDX.get(ntype, TYPE_TO_IDX["UNKNOWN"])
            type_one_hot[type_idx] = 1.0
            row_feats.extend(type_one_hot)

            # 2. Structural Degree Features (log1p normalized)
            in_deg = multi_graph.in_degree(nid)
            out_deg = multi_graph.out_degree(nid)
            tot_deg = in_deg + out_deg
            
            # Weighted degree
            w_in = sum(d.get("weight", 1.0) for _, _, d in multi_graph.in_edges(nid, data=True))
            w_out = sum(d.get("weight", 1.0) for _, _, d in multi_graph.out_edges(nid, data=True))

            row_feats.append(math.log1p(tot_deg))
            row_feats.append(math.log1p(in_deg))
            row_feats.append(math.log1p(out_deg))
            row_feats.append(math.log1p(w_in + w_out))

            # 3. Phase 3 Centrality Metrics
            m = self.metrics_cache.get(nid, {})
            row_feats.append(m.get("pagerank", 0.0) * 1000.0)  # Scale up small pagerank
            row_feats.append(m.get("betweenness_centrality", 0.0) * 100.0)
            row_feats.append(m.get("degree_centrality", 0.0))

            # 4. Multi-Case and Multi-Evidence Breadth
            cases = ndata.get("case_ids", set())
            case_count = len(cases) if isinstance(cases, (set, list)) else 1.0
            row_feats.append(math.log1p(case_count))

            # Evidence connections count
            evid_edges = sum(
                1 for _, nbr, d in multi_graph.out_edges(nid, data=True)
                if multi_graph.nodes[nbr].get("node_type") == "EVIDENCE"
            )
            row_feats.append(math.log1p(evid_edges))

            # 5. Neighboring Node-Type Distribution (11 dims)
            nbr_types_count = [0.0] * len(ORDERED_NODE_TYPES)
            nbrs = list(undirected_g.neighbors(nid)) if undirected_g.has_node(nid) else []
            if nbrs:
                for nbr in nbrs:
                    t = multi_graph.nodes[nbr].get("node_type", "UNKNOWN")
                    t_i = TYPE_TO_IDX.get(t, TYPE_TO_IDX["UNKNOWN"])
                    nbr_types_count[t_i] += 1.0
                # Normalize to probabilities
                nbr_types_count = [c / len(nbrs) for c in nbr_types_count]
            row_feats.extend(nbr_types_count)

            # 6. Provisional Resolved Entity Indicator
            is_prov = 1.0 if ndata.get("is_provisional_resolved") else 0.0
            row_feats.append(is_prov)

            raw_features.append(row_feats)

        feature_matrix = np.array(raw_features, dtype=np.float32)

        # Standardize continuous features across nodes
        # Column 11 onwards are continuous (except the last binary is_prov flag)
        continuous_indices = list(range(len(ORDERED_NODE_TYPES), feature_matrix.shape[1] - 1))
        for col in continuous_indices:
            mean = feature_matrix[:, col].mean()
            std = feature_matrix[:, col].std()
            if std > 1e-6:
                feature_matrix[:, col] = (feature_matrix[:, col] - mean) / std

        feature_names = [f"type_{t}" for t in ORDERED_NODE_TYPES]
        feature_names.extend([
            "log_total_degree", "log_in_degree", "log_out_degree", "log_weighted_degree",
            "scaled_pagerank", "scaled_betweenness", "degree_centrality",
            "log_case_count", "log_evidence_count"
        ])
        feature_names.extend([f"nbr_ratio_{t}" for t in ORDERED_NODE_TYPES])
        feature_names.append("is_provisional_resolved")

        return torch.tensor(feature_matrix, dtype=torch.float32), feature_names
