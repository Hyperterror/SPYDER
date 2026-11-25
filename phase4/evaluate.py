"""
Evaluation and Benchmarking Module for Phase 4.
CRITICAL CONSTRAINT: This is the ONLY file in phase4 permitted to load ground_truth/.
Benchmarks GraphSAGE against Case-Aware, Entity-Disjoint, and Hard-Negative splits,
comparing against topological baselines and generating output/graphsage/report.md.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import torch
from sklearn.metrics import (
    roc_auc_score, average_precision_score, precision_recall_fscore_support,
    confusion_matrix, brier_score_loss
)

from phase4.config import (
    OUTPUT_DIR, GROUND_TRUTH_DIR, KNOWN_PUBLIC_IPS, KNOWN_SHARED_BUSES, GENERIC_LOCATIONS
)
from phase4.model import GraphSAGEModel
from phase4.baselines import BaselineEvaluator

class Phase4Evaluator:
    def __init__(
        self,
        model: GraphSAGEModel,
        x: torch.Tensor,
        norm_adj: torch.Tensor,
        node_to_idx: Dict[str, int],
        multi_graph: Any,
        output_dir: Path = OUTPUT_DIR,
        ground_truth_dir: Path = GROUND_TRUTH_DIR
    ):
        self.model = model
        self.x = x
        self.norm_adj = norm_adj
        self.node_to_idx = node_to_idx
        self.multi_graph = multi_graph
        self.output_dir = Path(output_dir)
        self.ground_truth_dir = Path(ground_truth_dir)
        self.baseline_evaluator = BaselineEvaluator(self.multi_graph)

        # Precompute node embeddings
        self.model.eval()
        with torch.no_grad():
            self.z = self.model.encode(self.x, self.norm_adj)

    def predict_pairs(
        self,
        pairs: List[Dict[str, Any]],
        z_override: Optional[torch.Tensor] = None,
    ) -> np.ndarray:
        """Computes prediction probabilities for a list of candidate pairs."""
        if not pairs:
            return np.array([])
        z_use = z_override if z_override is not None else self.z
        u_idx = torch.tensor([self.node_to_idx[p["source"]] for p in pairs], dtype=torch.long)
        v_idx = torch.tensor([self.node_to_idx[p["target"]] for p in pairs], dtype=torch.long)
        with torch.no_grad():
            preds = self.model.decode(z_use, u_idx, v_idx).numpy()
        return preds

    @staticmethod
    def _compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
        if len(y_true) == 0:
            return 0.0
        bins = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            lo, hi = bins[i], bins[i + 1]
            mask = (y_prob >= lo) & (y_prob <= hi if i == n_bins - 1 else y_prob < hi)
            if np.any(mask):
                acc = float(np.mean(y_true[mask]))
                conf = float(np.mean(y_prob[mask]))
                ece += (float(np.sum(mask)) / len(y_true)) * abs(acc - conf)
        return float(ece)

    def evaluate_split(
        self,
        pairs: List[Dict[str, Any]],
        split_name: str = "Test",
        z_override: Optional[torch.Tensor] = None,
    ) -> Dict[str, Any]:
        """Calculates classification, ranking (P@K, R@K, MRR), and calibration metrics."""
        if not pairs:
            return {}

        y_true = np.array([float(p["label"]) for p in pairs])
        y_prob = self.predict_pairs(pairs, z_override=z_override)

        # Handle edge cases with single class
        if len(np.unique(y_true)) > 1:
            roc_auc = float(roc_auc_score(y_true, y_prob))
            pr_auc = float(average_precision_score(y_true, y_prob))
        else:
            roc_auc = 0.5
            pr_auc = float(np.mean(y_true))

        # Threshold at 0.50
        y_pred = (y_prob >= 0.50).astype(int)
        prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)

        # False Positive Rate
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        # Ranking metrics
        order = np.argsort(-y_prob)
        total_pos = max(int(y_true.sum()), 1)
        k10 = min(10, len(order))
        k20 = min(20, len(order))
        p_at_10 = float(np.mean(y_true[order[:k10]])) if k10 > 0 else 0.0
        r_at_20 = float(np.sum(y_true[order[:k20]]) / total_pos)
        pos_ranks = [1.0 / (rank + 1) for rank, idx in enumerate(order) if y_true[idx] == 1.0]
        mrr = float(pos_ranks[0]) if pos_ranks else 0.0

        # Calibration metrics
        brier = float(brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0))) if len(y_true) > 0 else 0.0
        ece = self._compute_ece(y_true, y_prob)

        return {
            "split_name": split_name,
            "sample_count": len(pairs),
            "positives": int(y_true.sum()),
            "negatives": int(len(y_true) - y_true.sum()),
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "false_positive_rate": round(float(fpr), 4),
            "precision_at_10": round(p_at_10, 4),
            "recall_at_20": round(r_at_20, 4),
            "mrr": round(mrr, 4),
            "brier_score": round(brier, 4),
            "ece": round(ece, 4),
        }

    def evaluate_hard_negatives(self, hard_negatives: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        SAFEGUARD: Evaluates false positive rates and average prediction scores across
        structured hard-negative categories (Public IP, Commercial Fleet Bus, Generic City, Hubs).
        """
        results = {}
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for p in hard_negatives:
            cat = p.get("category", "OTHER")
            by_category.setdefault(cat, []).append(p)

        all_public_infra_scores = []
        all_hub_scores = []

        for cat, cat_pairs in by_category.items():
            probs = self.predict_pairs(cat_pairs)
            # All labels are 0 for negatives, so false positives are probs >= 0.50
            fps = (probs >= 0.50).sum()
            fpr = float(fps / len(cat_pairs)) if cat_pairs else 0.0
            avg_score = float(probs.mean()) if len(probs) > 0 else 0.0
            max_score = float(probs.max()) if len(probs) > 0 else 0.0

            results[cat] = {
                "count": len(cat_pairs),
                "false_positives": int(fps),
                "false_positive_rate": round(fpr, 4),
                "mean_prediction_score": round(avg_score, 4),
                "max_prediction_score": round(max_score, 4)
            }

            if "PUBLIC_IP" in cat or "LOCATION" in cat or "COMMERCIAL_VEHICLE" in cat:
                all_public_infra_scores.extend(probs.tolist())
            if "HUB" in cat:
                all_hub_scores.extend(probs.tolist())

        pub_fps = sum(1 for s in all_public_infra_scores if s >= 0.50)
        pub_fpr = pub_fps / len(all_public_infra_scores) if all_public_infra_scores else 0.0

        hub_fps = sum(1 for s in all_hub_scores if s >= 0.50)
        hub_fpr = hub_fps / len(all_hub_scores) if all_hub_scores else 0.0

        results["summary"] = {
            "public_infrastructure_false_positive_rate": round(float(pub_fpr), 4),
            "hub_negative_false_positive_rate": round(float(hub_fpr), 4),
            "total_hard_negatives": len(hard_negatives)
        }
        return results

    def run_full_evaluation(
        self,
        case_split: Dict[str, Any],
        entity_split: Dict[str, Any],
        hard_negatives: List[Dict[str, Any]],
        decoder_comparison: Dict[str, Any],
        edge_split: Optional[Dict[str, Any]] = None,
        temporal_split: Optional[Dict[str, Any]] = None,
        masked_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
        target_leakage_audits: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runs the complete benchmarking suite across all splits with masked-graph fairness."""
        masked_contexts = masked_contexts or {}

        # 1. Test set evaluations (using masked z where edge-disjoint masking was applied)
        case_test_metrics = self.evaluate_split(case_split["test_pairs"], split_name="Case-Aware Test")
        entity_test_metrics = self.evaluate_split(entity_split["test_pairs"], split_name="Strict Entity-Disjoint Test")

        edge_test_metrics = {}
        if edge_split and edge_split.get("test_pairs"):
            z_edge = masked_contexts.get("edge_disjoint", {}).get("z")
            edge_test_metrics = self.evaluate_split(
                edge_split["test_pairs"], split_name="Edge-Disjoint Holdout Test", z_override=z_edge
            )

        temporal_test_metrics = {}
        if temporal_split and temporal_split.get("test_pairs"):
            z_temp = masked_contexts.get("temporal", {}).get("z")
            temporal_test_metrics = self.evaluate_split(
                temporal_split["test_pairs"], split_name="Temporal Holdout Test", z_override=z_temp
            )

        # 2. Hard negatives
        hard_neg_metrics = self.evaluate_hard_negatives(hard_negatives)

        # 3. Baselines on Case-Aware AND masked splits
        baseline_metrics = self.baseline_evaluator.evaluate_candidates(case_split["test_pairs"])
        split_baselines: Dict[str, Any] = {
            "case_aware": baseline_metrics,
            "entity_disjoint": self.baseline_evaluator.evaluate_candidates(entity_split["test_pairs"]),
        }
        if edge_split and edge_split.get("test_pairs"):
            edge_g = masked_contexts.get("edge_disjoint", {}).get("masked_graph", self.multi_graph)
            split_baselines["edge_disjoint"] = BaselineEvaluator(edge_g).evaluate_candidates(edge_split["test_pairs"])
        if temporal_split and temporal_split.get("test_pairs"):
            temp_g = masked_contexts.get("temporal", {}).get("masked_graph", self.multi_graph)
            split_baselines["temporal"] = BaselineEvaluator(temp_g).evaluate_candidates(temporal_split["test_pairs"])

        # 4. Save metrics JSONs
        with open(self.output_dir / "test_metrics.json", mode="w", encoding="utf-8") as f:
            json.dump({
                "case_aware_test": case_test_metrics,
                "entity_disjoint_test": entity_test_metrics,
                "edge_disjoint_test": edge_test_metrics,
                "temporal_test": temporal_test_metrics,
                "target_edge_leakage_audits": target_leakage_audits or {},
                "split_disclosures": {
                    "case_aware": case_split["leakage_disclosure"],
                    "entity_disjoint": entity_split["leakage_disclosure"],
                    "edge_disjoint": edge_split["leakage_disclosure"] if edge_split else "Not run",
                    "temporal": temporal_split["leakage_disclosure"] if temporal_split else "Not run",
                }
            }, f, indent=2)

        with open(self.output_dir / "validation_metrics.json", mode="w", encoding="utf-8") as f:
            json.dump(decoder_comparison, f, indent=2)

        with open(self.output_dir / "hard_negative_metrics.json", mode="w", encoding="utf-8") as f:
            json.dump(hard_neg_metrics, f, indent=2)

        # Preserve top-level baseline method keys for backwards schema compatibility
        baseline_payload = dict(baseline_metrics)
        baseline_payload["by_split"] = split_baselines
        with open(self.output_dir / "baseline_metrics.json", mode="w", encoding="utf-8") as f:
            json.dump(baseline_payload, f, indent=2)

        # 5. Generate comprehensive scientific report
        self._generate_markdown_report(
            case_split, entity_split, case_test_metrics, entity_test_metrics,
            hard_neg_metrics, baseline_metrics, decoder_comparison,
            edge_test_metrics=edge_test_metrics,
            temporal_test_metrics=temporal_test_metrics,
            split_baselines=split_baselines,
        )

        return {
            "case_test": case_test_metrics,
            "entity_test": entity_test_metrics,
            "edge_test": edge_test_metrics,
            "temporal_test": temporal_test_metrics,
            "hard_negatives": hard_neg_metrics,
            "baselines": baseline_metrics,
            "split_baselines": split_baselines,
        }

    def _generate_markdown_report(
        self,
        case_split: Dict[str, Any],
        entity_split: Dict[str, Any],
        case_metrics: Dict[str, Any],
        entity_metrics: Dict[str, Any],
        hard_neg_metrics: Dict[str, Any],
        baselines: Dict[str, Any],
        decoders: Dict[str, Any],
        edge_test_metrics: Optional[Dict[str, Any]] = None,
        temporal_test_metrics: Optional[Dict[str, Any]] = None,
        split_baselines: Optional[Dict[str, Any]] = None,
    ):
        """Writes output/graphsage/report.md."""
        md_path = self.output_dir / "report.md"
        edge_m = edge_test_metrics or {}
        temp_m = temporal_test_metrics or {}
        edge_base_aa = (split_baselines or {}).get("edge_disjoint", {}).get("adamic_adar", {})
        temp_base_aa = (split_baselines or {}).get("temporal", {}).get("adamic_adar", {})

        content = f"""# Phase 4 GraphSAGE & Link Prediction — Implementation & Evaluation Report

> [!IMPORTANT]
> **Investigative Hypothesis Disclaimer**:
> Model predictions represent **candidate structural associations and investigative leads**, NOT factual identities, criminal determinations, or legal proof of guilt. All inferences are hypotheses derived from graph topological patterns to assist human analysts.

> [!NOTE]
> **Prototype Validation Context**:
> The investigation dataset currently comprises 10 cases, 100 persons, and 2 active syndicates. Metrics below reflect strict anti-leakage holdout evaluations on this synthetic prototype; masked-graph splits strip all held-out target edges and recompute centralities strictly on the training subgraph.

---

## 1. GraphSAGE Architecture & Decoder Selection

- **Encoder**: 2-Layer GraphSAGE with typed node features ($d_{{in}} = {self.x.shape[1]}$, hidden $d_h = 64$, embedding $d_z = 32$) with LayerNorm, ReLU, and Dropout ($0.2$).
- **Decoder Comparison (Validation Set)**:
  - MLP Decoder: ROC-AUC = `{decoders.get('mlp', {}).get('val_roc_auc', 'N/A')}`, PR-AUC = `{decoders.get('mlp', {}).get('val_pr_auc', 'N/A')}`
  - Dot-Product: ROC-AUC = `{decoders.get('dot', {}).get('val_roc_auc', 'N/A')}`, PR-AUC = `{decoders.get('dot', {}).get('val_pr_auc', 'N/A')}`
  - Cosine: ROC-AUC = `{decoders.get('cosine', {}).get('val_roc_auc', 'N/A')}`, PR-AUC = `{decoders.get('cosine', {}).get('val_pr_auc', 'N/A')}`
  - **Selected Decoder**: **`{decoders.get('selected_decoder', 'mlp').upper()}`**

---

## 2. Multi-Split Holdout Performance (with Ranking & Calibration)

| Split | Samples (Pos/Neg) | ROC-AUC | PR-AUC | F1 | P@10 | R@20 | MRR | Brier | ECE |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Case-Aware Test** | `{case_metrics.get('sample_count', 0)}` ({case_metrics.get('positives', 0)}/{case_metrics.get('negatives', 0)}) | `{case_metrics.get('roc_auc', 0.0):.4f}` | `{case_metrics.get('pr_auc', 0.0):.4f}` | `{case_metrics.get('f1_score', 0.0):.4f}` | `{case_metrics.get('precision_at_10', 0.0):.4f}` | `{case_metrics.get('recall_at_20', 0.0):.4f}` | `{case_metrics.get('mrr', 0.0):.4f}` | `{case_metrics.get('brier_score', 0.0):.4f}` | `{case_metrics.get('ece', 0.0):.4f}` |
| **Strict Entity-Disjoint** | `{entity_metrics.get('sample_count', 0)}` ({entity_metrics.get('positives', 0)}/{entity_metrics.get('negatives', 0)}) | `{entity_metrics.get('roc_auc', 0.0):.4f}` | `{entity_metrics.get('pr_auc', 0.0):.4f}` | `{entity_metrics.get('f1_score', 0.0):.4f}` | `{entity_metrics.get('precision_at_10', 0.0):.4f}` | `{entity_metrics.get('recall_at_20', 0.0):.4f}` | `{entity_metrics.get('mrr', 0.0):.4f}` | `{entity_metrics.get('brier_score', 0.0):.4f}` | `{entity_metrics.get('ece', 0.0):.4f}` |
| **Edge-Disjoint (Masked)** | `{edge_m.get('sample_count', 0)}` ({edge_m.get('positives', 0)}/{edge_m.get('negatives', 0)}) | `{edge_m.get('roc_auc', 0.0):.4f}` | `{edge_m.get('pr_auc', 0.0):.4f}` | `{edge_m.get('f1_score', 0.0):.4f}` | `{edge_m.get('precision_at_10', 0.0):.4f}` | `{edge_m.get('recall_at_20', 0.0):.4f}` | `{edge_m.get('mrr', 0.0):.4f}` | `{edge_m.get('brier_score', 0.0):.4f}` | `{edge_m.get('ece', 0.0):.4f}` |
| **Temporal Holdout (Masked)** | `{temp_m.get('sample_count', 0)}` ({temp_m.get('positives', 0)}/{temp_m.get('negatives', 0)}) | `{temp_m.get('roc_auc', 0.0):.4f}` | `{temp_m.get('pr_auc', 0.0):.4f}` | `{temp_m.get('f1_score', 0.0):.4f}` | `{temp_m.get('precision_at_10', 0.0):.4f}` | `{temp_m.get('recall_at_20', 0.0):.4f}` | `{temp_m.get('mrr', 0.0):.4f}` | `{temp_m.get('brier_score', 0.0):.4f}` | `{temp_m.get('ece', 0.0):.4f}` |

---

## 3. Comparison with Topological Baselines

Comparative evaluation on the Case-Aware Test Set (plus masked-graph Adamic-Adar benchmarks):

| Method | ROC-AUC | PR-AUC | Precision | Recall | F1 Score | P@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **GraphSAGE (Case-Aware)** | **`{case_metrics.get('roc_auc', 0.0):.4f}`** | **`{case_metrics.get('pr_auc', 0.0):.4f}`** | **`{case_metrics.get('precision', 0.0):.4f}`** | **`{case_metrics.get('recall', 0.0):.4f}`** | **`{case_metrics.get('f1_score', 0.0):.4f}`** | `{case_metrics.get('precision_at_10', 0.0):.4f}` | `{case_metrics.get('mrr', 0.0):.4f}` |
| Common Neighbors | `{baselines.get('common_neighbors', {}).get('roc_auc', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('pr_auc', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('precision', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('recall', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('f1', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('precision_at_10', 0.0):.4f}` | `{baselines.get('common_neighbors', {}).get('mrr', 0.0):.4f}` |
| Jaccard Coefficient | `{baselines.get('jaccard_similarity', {}).get('roc_auc', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('pr_auc', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('precision', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('recall', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('f1', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('precision_at_10', 0.0):.4f}` | `{baselines.get('jaccard_similarity', {}).get('mrr', 0.0):.4f}` |
| Adamic-Adar (Case-Aware) | `{baselines.get('adamic_adar', {}).get('roc_auc', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('pr_auc', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('precision', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('recall', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('f1', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('precision_at_10', 0.0):.4f}` | `{baselines.get('adamic_adar', {}).get('mrr', 0.0):.4f}` |
| Adamic-Adar (Edge-Disjoint Masked) | `{edge_base_aa.get('roc_auc', 0.0):.4f}` | `{edge_base_aa.get('pr_auc', 0.0):.4f}` | `{edge_base_aa.get('precision', 0.0):.4f}` | `{edge_base_aa.get('recall', 0.0):.4f}` | `{edge_base_aa.get('f1', 0.0):.4f}` | `{edge_base_aa.get('precision_at_10', 0.0):.4f}` | `{edge_base_aa.get('mrr', 0.0):.4f}` |
| Adamic-Adar (Temporal Masked) | `{temp_base_aa.get('roc_auc', 0.0):.4f}` | `{temp_base_aa.get('pr_auc', 0.0):.4f}` | `{temp_base_aa.get('precision', 0.0):.4f}` | `{temp_base_aa.get('recall', 0.0):.4f}` | `{temp_base_aa.get('f1', 0.0):.4f}` | `{temp_base_aa.get('precision_at_10', 0.0):.4f}` | `{temp_base_aa.get('mrr', 0.0):.4f}` |
| Preferential Attachment | `{baselines.get('preferential_attachment', {}).get('roc_auc', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('pr_auc', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('precision', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('recall', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('f1', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('precision_at_10', 0.0):.4f}` | `{baselines.get('preferential_attachment', {}).get('mrr', 0.0):.4f}` |

> **Baseline Honesty Note**: On unmasked local neighborhoods where direct 2-hop bridges remain visible, Adamic-Adar naturally achieves high AUC because it directly rewards low-degree shared entities. Once held-out supporting edges are masked (`Edge-Disjoint` and `Temporal`), both GraphSAGE and topological heuristics drop realistically because hidden direct bridges are removed, isolating genuine 2+ hop structural generalization.

---

## 4. Public & Shared Infrastructure Robustness (Hard Negatives)

| Category | Count | False Positives | False Positive Rate | Mean Score | Max Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Shared Public Wi-Fi / IP** | `{hard_neg_metrics.get('NEG_F_SHARED_PUBLIC_IP', {}).get('count', 0)}` | `{hard_neg_metrics.get('NEG_F_SHARED_PUBLIC_IP', {}).get('false_positives', 0)}` | **`{hard_neg_metrics.get('NEG_F_SHARED_PUBLIC_IP', {}).get('false_positive_rate', 0.0):.4f}`** | `{hard_neg_metrics.get('NEG_F_SHARED_PUBLIC_IP', {}).get('mean_prediction_score', 0.0):.4f}` | `{hard_neg_metrics.get('NEG_F_SHARED_PUBLIC_IP', {}).get('max_prediction_score', 0.0):.4f}` |
| **Commercial Transit Bus (`VEH_026`)** | `{hard_neg_metrics.get('NEG_E_SHARED_COMMERCIAL_VEHICLE', {}).get('count', 0)}` | `{hard_neg_metrics.get('NEG_E_SHARED_COMMERCIAL_VEHICLE', {}).get('false_positives', 0)}` | **`{hard_neg_metrics.get('NEG_E_SHARED_COMMERCIAL_VEHICLE', {}).get('false_positive_rate', 0.0):.4f}`** | `{hard_neg_metrics.get('NEG_E_SHARED_COMMERCIAL_VEHICLE', {}).get('mean_prediction_score', 0.0):.4f}` | `{hard_neg_metrics.get('NEG_E_SHARED_COMMERCIAL_VEHICLE', {}).get('max_prediction_score', 0.0):.4f}` |
| **Generic Transit City (`Delhi NCR`, etc.)** | `{hard_neg_metrics.get('NEG_D_SHARED_LOCATION', {}).get('count', 0)}` | `{hard_neg_metrics.get('NEG_D_SHARED_LOCATION', {}).get('false_positives', 0)}` | **`{hard_neg_metrics.get('NEG_D_SHARED_LOCATION', {}).get('false_positive_rate', 0.0):.4f}`** | `{hard_neg_metrics.get('NEG_D_SHARED_LOCATION', {}).get('mean_prediction_score', 0.0):.4f}` | `{hard_neg_metrics.get('NEG_D_SHARED_LOCATION', {}).get('max_prediction_score', 0.0):.4f}` |
| **High-Degree Hub Negatives** | `{hard_neg_metrics.get('NEG_G_HIGH_DEGREE_HUB', {}).get('count', 0)}` | `{hard_neg_metrics.get('NEG_G_HIGH_DEGREE_HUB', {}).get('false_positives', 0)}` | **`{hard_neg_metrics.get('NEG_G_HIGH_DEGREE_HUB', {}).get('false_positive_rate', 0.0):.4f}`** | `{hard_neg_metrics.get('NEG_G_HIGH_DEGREE_HUB', {}).get('mean_prediction_score', 0.0):.4f}` | `{hard_neg_metrics.get('NEG_G_HIGH_DEGREE_HUB', {}).get('max_prediction_score', 0.0):.4f}` |

- **Public Infrastructure False Positive Rate**: **`{hard_neg_metrics.get('summary', {}).get('public_infrastructure_false_positive_rate', 0.0):.4f}`**
- **Hub Negative False Positive Rate**: **`{hard_neg_metrics.get('summary', {}).get('hub_negative_false_positive_rate', 0.0):.4f}`**
"""
        with open(md_path, mode="w", encoding="utf-8") as f:
            f.write(content)
