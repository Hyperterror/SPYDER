"""
Topological Heuristic Baselines for Phase 4 Link Prediction.
Implements:
1. Common Neighbors (CN)
2. Jaccard Coefficient (JC)
3. Adamic-Adar Index (AA)
4. Preferential Attachment (PA)
5. Multi-Modal Evidence Heuristic
Evaluates performance against identical candidate splits.
"""

import math
from typing import Dict, List, Set, Any, Tuple
import networkx as nx
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_fscore_support

class BaselineEvaluator:
    def __init__(self, multi_graph: nx.MultiDiGraph):
        self.multi_graph = multi_graph
        self.undirected_g = multi_graph.to_undirected()

    def score_pair_cn(self, u: str, v: str) -> float:
        """Common Neighbors Count."""
        if not self.undirected_g.has_node(u) or not self.undirected_g.has_node(v):
            return 0.0
        nu = set(self.undirected_g.neighbors(u))
        nv = set(self.undirected_g.neighbors(v))
        return float(len(nu & nv))

    def score_pair_jaccard(self, u: str, v: str) -> float:
        """Jaccard Coefficient."""
        if not self.undirected_g.has_node(u) or not self.undirected_g.has_node(v):
            return 0.0
        nu = set(self.undirected_g.neighbors(u))
        nv = set(self.undirected_g.neighbors(v))
        union = nu | nv
        return float(len(nu & nv) / len(union)) if union else 0.0

    def score_pair_adamic_adar(self, u: str, v: str) -> float:
        """Adamic-Adar Index."""
        if not self.undirected_g.has_node(u) or not self.undirected_g.has_node(v):
            return 0.0
        nu = set(self.undirected_g.neighbors(u))
        nv = set(self.undirected_g.neighbors(v))
        common = nu & nv
        score = 0.0
        for w in common:
            deg = self.undirected_g.degree(w)
            if deg > 1:
                score += 1.0 / math.log(deg)
        return score

    def score_pair_pref_attachment(self, u: str, v: str) -> float:
        """Preferential Attachment."""
        if not self.undirected_g.has_node(u) or not self.undirected_g.has_node(v):
            return 0.0
        return float(self.undirected_g.degree(u) * self.undirected_g.degree(v))

    def evaluate_candidates(self, candidates: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Runs all heuristic baselines over candidate pairs and reports:
        ROC-AUC, PR-AUC, F1, Precision, Recall.
        """
        y_true = [c["label"] for c in candidates]
        if sum(y_true) == 0 or sum(y_true) == len(y_true):
            return {}

        results = {}
        for method_name, score_fn in [
            ("common_neighbors", self.score_pair_cn),
            ("jaccard_similarity", self.score_pair_jaccard),
            ("adamic_adar", self.score_pair_adamic_adar),
            ("preferential_attachment", self.score_pair_pref_attachment),
        ]:
            scores = [score_fn(c["source"], c["target"]) for c in candidates]
            # Normalize scores to [0, 1]
            max_s = max(scores) if scores else 1.0
            norm_scores = [s / max_s if max_s > 0 else 0.0 for s in scores]

            roc_auc = roc_auc_score(y_true, norm_scores)
            pr_auc = average_precision_score(y_true, norm_scores)

            # Threshold at median or 0.2
            y_pred = [1 if s >= 0.2 else 0 for s in norm_scores]
            prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)

            results[method_name] = {
                "roc_auc": round(float(roc_auc), 4),
                "pr_auc": round(float(pr_auc), 4),
                "precision": round(float(prec), 4),
                "recall": round(float(rec), 4),
                "f1": round(float(f1), 4)
            }

        return results
