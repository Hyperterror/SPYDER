"""
Inference Pipeline for Phase 4.
Generates ranked link predictions, computes confidence tiers, attaches evidence-backed
structural explanations, and exports node_embeddings.csv, candidate_links.csv, and predictions.csv.
"""

import csv
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional
import networkx as nx
import numpy as np
import torch

from phase4.config import (
    OUTPUT_DIR, THRESHOLD_HIGH_PRIORITY, THRESHOLD_REVIEW,
    KNOWN_PUBLIC_IPS, KNOWN_SHARED_BUSES, GENERIC_LOCATIONS
)
from phase4.model import GraphSAGEModel
from phase4.explain import generate_prediction_explanation

class LinkPredictor:
    def __init__(
        self,
        model: GraphSAGEModel,
        x: torch.Tensor,
        norm_adj: torch.Tensor,
        node_to_idx: Dict[str, int],
        idx_to_node: Dict[int, str],
        multi_graph: nx.MultiDiGraph,
        output_dir: Path = OUTPUT_DIR
    ):
        self.model = model
        self.x = x
        self.norm_adj = norm_adj
        self.node_to_idx = node_to_idx
        self.idx_to_node = idx_to_node
        self.multi_graph = multi_graph
        self.undirected_g = multi_graph.to_undirected()
        self.output_dir = Path(output_dir)

        self.model.eval()
        with torch.no_grad():
            self.embeddings = self.model.encode(self.x, self.norm_adj).cpu().numpy()

    def export_node_embeddings(self):
        """Exports learned 32-dim node embeddings to output/graphsage/node_embeddings.csv."""
        csv_path = self.output_dir / "node_embeddings.csv"
        num_nodes, dim = self.embeddings.shape
        fieldnames = ["node_id", "node_type"] + [f"dim_{i:02d}" for i in range(dim)]

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for idx in range(num_nodes):
                nid = self.idx_to_node[idx]
                ntype = self.multi_graph.nodes[nid].get("node_type", "UNKNOWN")
                row = {
                    "node_id": nid,
                    "node_type": ntype,
                    **{f"dim_{i:02d}": round(float(self.embeddings[idx, i]), 6) for i in range(dim)}
                }
                writer.writerow(row)

    def predict_and_explain_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculates prediction scores for candidate links, assigns priority tiers,
        synthesizes evidence-backed structural explanations, and exports predictions.csv.
        """
        results = []
        u_indices = torch.tensor([self.node_to_idx[c["source"]] for c in candidates], dtype=torch.long)
        v_indices = torch.tensor([self.node_to_idx[c["target"]] for c in candidates], dtype=torch.long)

        z_tensor = torch.tensor(self.embeddings, dtype=torch.float32)
        with torch.no_grad():
            scores = self.model.decode(z_tensor, u_indices, v_indices).numpy()

        for idx, c in enumerate(candidates):
            u, v = c["source"], c["target"]
            score = float(scores[idx])

            # Classify priority tier
            if score >= THRESHOLD_HIGH_PRIORITY:
                tier = "HIGH-PRIORITY LEAD"
            elif score >= THRESHOLD_REVIEW:
                tier = "REVIEW"
            else:
                tier = "LOW PRIORITY"

            # Find common 2-hop neighbors in graph
            nu = set(self.undirected_g.neighbors(u)) if self.undirected_g.has_node(u) else set()
            nv = set(self.undirected_g.neighbors(v)) if self.undirected_g.has_node(v) else set()
            common = nu & nv

            common_nbr_info = []
            modalities = set()
            penalty_reasons = []

            for nbr in common:
                ntype = self.multi_graph.nodes[nbr].get("node_type", "UNKNOWN")
                common_nbr_info.append({"id": nbr, "type": ntype})
                modalities.add(ntype)

                # Check infrastructure penalties
                if nbr in KNOWN_PUBLIC_IPS:
                    penalty_reasons.append(f"Pair co-occurs at public Wi-Fi hotspot ({nbr})")
                if nbr in KNOWN_SHARED_BUSES:
                    penalty_reasons.append(f"Pair co-occurs on high-fanout commercial sleeper bus ({nbr})")
                if nbr in GENERIC_LOCATIONS:
                    penalty_reasons.append(f"Pair co-occurs at generic transit city ({nbr})")

            # Check case memberships
            c1 = c.get("source_cases", "")
            c2 = c.get("target_cases", "")
            is_cross = c.get("is_cross_case", False)

            explanation = generate_prediction_explanation(
                source_node=u,
                target_node=v,
                score=score,
                tier=tier,
                common_neighbors=common_nbr_info,
                is_cross_case=is_cross,
                shared_modalities=sorted(list(modalities)),
                penalty_reasons=penalty_reasons
            )

            results.append({
                "source_node": u,
                "target_node": v,
                "label": c.get("label", 0),
                "category": c.get("category", "CANDIDATE"),
                "prediction_score": round(score, 4),
                "confidence_tier": tier,
                "node_types": "PERSON ↔ PERSON",
                "source_cases": c1,
                "target_cases": c2,
                "is_cross_case": is_cross,
                "common_neighbors_count": len(common),
                "common_neighbors": "; ".join([n["id"] for n in common_nbr_info[:4]]),
                "shared_modalities": "; ".join(sorted(list(modalities))),
                "top_structural_reasons": "; ".join(penalty_reasons) if penalty_reasons else "Direct structural proximity",
                "explanation": explanation
            })

        # Sort by score descending
        results.sort(key=lambda x: x["prediction_score"], reverse=True)

        # Export predictions.csv
        pred_csv = self.output_dir / "predictions.csv"
        fieldnames = [
            "source_node", "target_node", "prediction_score", "confidence_tier",
            "category", "label", "node_types", "source_cases", "target_cases",
            "is_cross_case", "common_neighbors_count", "common_neighbors",
            "shared_modalities", "top_structural_reasons", "explanation"
        ]
        with open(pred_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)

        # Export candidate_links.csv
        cand_csv = self.output_dir / "candidate_links.csv"
        cand_fields = ["source", "target", "label", "category", "source_cases", "target_cases", "is_cross_case"]
        with open(cand_csv, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cand_fields, extrasaction="ignore")
            writer.writeheader()
            for c in candidates:
                writer.writerow(c)

        return results
