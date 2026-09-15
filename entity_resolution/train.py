"""
Model Training and Evaluation Pipeline for Entity Resolution.
Implements case-aware splitting, XGBoost classifier training, evaluation across splits,
hard-negative stress testing, baseline comparison, and artifact export.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import xgboost as xgb

from entity_resolution.config import (
    EVIDENCE_DIR, GROUND_TRUTH_DIR, OUTPUT_DIR, MODEL_DIR, REPORTS_DIR,
    TRAIN_CASES, VAL_CASES, TEST_CASES, XGBOOST_PARAMS,
    TIER_HIGH_THRESHOLD, TIER_MEDIUM_THRESHOLD,
    TIER_HIGH_LABEL, TIER_MEDIUM_LABEL, TIER_LOW_LABEL,
    FORBIDDEN_FEATURE_TOKENS
)
from entity_resolution.pair_generation import PairDatasetBuilder
from entity_resolution.evaluate import compute_metrics
from entity_resolution.baselines import evaluate_baselines
from entity_resolution.explain import generate_explanation

def partition_by_case(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Partitions candidate pair rows into Train, Val, Test, and Hard-Negative subsets
    using case-aware boundaries to prevent trivial entity memorization.
    """
    train_rows = []
    val_rows = []
    test_rows = []
    hn_rows = []

    train_set = set(TRAIN_CASES)
    val_set = set(VAL_CASES)
    test_set = set(TEST_CASES)

    for r in rows:
        c_a = r["case_id_a"]
        c_b = r["case_id_b"]

        if r.get("is_hard_negative", 0) == 1:
            hn_rows.append(r)

        if c_a in test_set or c_b in test_set:
            test_rows.append(r)
        elif c_a in val_set or c_b in val_set:
            val_rows.append(r)
        else:
            train_rows.append(r)

    return train_rows, val_rows, test_rows, hn_rows

def get_feature_matrix(rows: List[Dict[str, Any]], feature_names: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Extracts numpy feature matrix X and ground-truth label vector y."""
    X = np.zeros((len(rows), len(feature_names)), dtype=np.float32)
    y = np.zeros(len(rows), dtype=np.int32)

    for i, r in enumerate(rows):
        for j, fn in enumerate(feature_names):
            X[i, j] = float(r.get(fn, 0.0))
        y[i] = int(r.get("same_entity", 0))

    return X, y

def train_and_evaluate(evidence_dir: Path = EVIDENCE_DIR, ground_truth_dir: Path = GROUND_TRUTH_DIR, output_dir: Path = OUTPUT_DIR):
    out_dir = Path(output_dir)
    model_dir = out_dir / "model"
    reports_dir = out_dir / "reports"
    model_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build pair dataset
    builder = PairDatasetBuilder(evidence_dir=evidence_dir, ground_truth_dir=ground_truth_dir, output_dir=out_dir)
    dataset_summary = builder.build_dataset()
    rows = dataset_summary["rows"]
    feature_names = dataset_summary["feature_names"]

    # Explicit data leakage check
    print("Executing Data Leakage Audit on feature schema...")
    for fn in feature_names:
        for forbidden in FORBIDDEN_FEATURE_TOKENS:
            if forbidden in fn.lower():
                raise ValueError(f"CRITICAL LEAKAGE DETECTED in feature name: '{fn}' contains '{forbidden}'!")
    print(f"Data Leakage Audit Passed: {len(feature_names)} features verified clean.\n")

    # 2. Case-aware split
    train_rows, val_rows, test_rows, hn_rows = partition_by_case(rows)

    X_train, y_train = get_feature_matrix(train_rows, feature_names)
    X_val, y_val = get_feature_matrix(val_rows, feature_names)
    X_test, y_test = get_feature_matrix(test_rows, feature_names)
    X_hn, y_hn = get_feature_matrix(hn_rows, feature_names)

    # Handle class imbalance if necessary
    num_pos = np.sum(y_train == 1)
    num_neg = np.sum(y_train == 0)
    scale_pos = (num_neg / max(1, num_pos)) if num_pos > 0 else 1.0

    # 3. Train XGBoost model
    xgb_params = dict(XGBOOST_PARAMS)
    xgb_params["scale_pos_weight"] = float(scale_pos)

    model = xgb.XGBClassifier(**xgb_params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    # 4. Save trained model and feature schema
    model_path = model_dir / "xgboost_entity_resolution.json"
    model.save_model(str(model_path))
    with open(model_dir / "feature_names.json", "w", encoding="utf-8") as f:
        json.dump(feature_names, f, indent=2)

    # 5. Evaluate on all splits
    def eval_split(X, y):
        probs = model.predict_proba(X)[:, 1] if len(X) > 0 else []
        preds = [1 if p >= 0.50 else 0 for p in probs]
        return compute_metrics(y, preds, probs)

    train_metrics = eval_split(X_train, y_train)
    val_metrics = eval_split(X_val, y_val)
    test_metrics = eval_split(X_test, y_test)
    hn_metrics = eval_split(X_hn, y_hn)

    # Save metrics JSONs
    with open(out_dir / "train_metrics.json", "w", encoding="utf-8") as f:
        json.dump(train_metrics, f, indent=2)
    with open(out_dir / "validation_metrics.json", "w", encoding="utf-8") as f:
        json.dump(val_metrics, f, indent=2)
    with open(out_dir / "test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, indent=2)
    with open(out_dir / "hard_negative_metrics.json", "w", encoding="utf-8") as f:
        json.dump(hn_metrics, f, indent=2)

    # 6. Baseline evaluations on Test set
    baseline_results = evaluate_baselines(test_rows)

    # 7. Generate production predictions with confidence tiers and explanations
    X_all, _ = get_feature_matrix(rows, feature_names)
    all_probs = model.predict_proba(X_all)[:, 1]

    pred_records = []
    for idx, r in enumerate(rows):
        prob = float(all_probs[idx])
        if prob >= TIER_HIGH_THRESHOLD:
            tier = TIER_HIGH_LABEL
        elif prob >= TIER_MEDIUM_THRESHOLD:
            tier = TIER_MEDIUM_LABEL
        else:
            tier = TIER_LOW_LABEL

        expl = generate_explanation(r, prob)

        pred_records.append({
            "person_id_a": r["person_id_a"],
            "person_id_b": r["person_id_b"],
            "case_id_a": r["case_id_a"],
            "case_id_b": r["case_id_b"],
            "name_a": r["name_a"],
            "name_b": r["name_b"],
            "alias_a": r["alias_a"],
            "alias_b": r["alias_b"],
            "match_probability": round(prob, 4),
            "confidence_tier": tier,
            "explanation_summary": expl["summary"],
            "supporting_reasons": "; ".join(expl["supporting_reasons"]),
            "conflicting_reasons": "; ".join(expl["conflicting_reasons"])
        })

    # Export predictions.csv (strictly clean of ground truth)
    pred_csv_path = out_dir / "predictions.csv"
    with open(pred_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(pred_records[0].keys()))
        writer.writeheader()
        for pr in pred_records:
            writer.writerow(pr)

    # 8. Generate comprehensive Markdown report
    report_md = f"""# Entity Resolution Performance Report (SIH26189 Phase 2)

*Notice: The current dataset is synthetic and intended for prototype development and evaluation. It does not represent real NCRB/police data.*
*Notice: Model predictions are investigative leads and not legal determinations of identity, guilt, or criminal involvement.*

---

## 1. Dataset Partition & Split Summary

- **Total Candidate Pairs:** {len(rows)}
- **Train Set:** {len(train_rows)} pairs ({TRAIN_CASES})
- **Validation Set:** {len(val_rows)} pairs ({VAL_CASES})
- **Test Set:** {len(test_rows)} pairs ({TEST_CASES})
- **Hard-Negative Evaluation Subset:** {len(hn_rows)} pairs
- **Pairwise Features Extracted:** {len(feature_names)}

---

## 2. Test Set Model Performance vs Baselines

| Method | Precision | Recall | F1 Score | False Merge Rate (FMR) | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline 1: Exact Identifier Match** | {baseline_results['Baseline 1: Exact Identifier Match']['precision']:.4f} | {baseline_results['Baseline 1: Exact Identifier Match']['recall']:.4f} | {baseline_results['Baseline 1: Exact Identifier Match']['f1']:.4f} | {baseline_results['Baseline 1: Exact Identifier Match']['false_merge_rate']:.4f} | N/A |
| **Baseline 2: Name Similarity (>=0.85)** | {baseline_results['Baseline 2: Name Similarity (>=0.85)']['precision']:.4f} | {baseline_results['Baseline 2: Name Similarity (>=0.85)']['recall']:.4f} | {baseline_results['Baseline 2: Name Similarity (>=0.85)']['f1']:.4f} | {baseline_results['Baseline 2: Name Similarity (>=0.85)']['false_merge_rate']:.4f} | N/A |
| **Sentence Transformer + XGBoost** | **{test_metrics['precision']:.4f}** | **{test_metrics['recall']:.4f}** | **{test_metrics['f1']:.4f}** | **{test_metrics['false_merge_rate']:.4f}** | **{test_metrics['roc_auc']:.4f}** |

---

## 3. Hard-Negative Evaluation Metrics

Evaluated specifically on adversarial pairs sharing names, aliases, or public infrastructure (e.g. Ramesh Chand vs Ramesh Chand, Vicky vs Vicky, shared Wi-Fi IPs):

- **Hard-Negative Total Samples:** {hn_metrics['total_samples']}
- **Hard-Negative Precision:** {hn_metrics['precision']:.4f}
- **Hard-Negative Recall:** {hn_metrics['recall']:.4f}
- **Hard-Negative False Merge Rate:** {hn_metrics['false_merge_rate']:.4f}
- **False Merges on Hard Negatives:** {hn_metrics['false_positives']}

---

## 4. Feature Importance (Top Features)

"""
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    for rank, idx in enumerate(sorted_idx[:10], 1):
        report_md += f"{rank}. **{feature_names[idx]}**: {importances[idx]:.4f}\n"

    with open(reports_dir / "entity_resolution_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n" + "="*50)
    print("Phase 2 Model Training & Evaluation Complete")
    print("="*50)
    print(f"Test Precision: {test_metrics['precision']:.4f} | Recall: {test_metrics['recall']:.4f} | F1: {test_metrics['f1']:.4f}")
    print(f"Test False Merge Rate: {test_metrics['false_merge_rate']:.4f} | ROC-AUC: {test_metrics['roc_auc']:.4f}")
    print(f"Hard-Negative False Merge Rate: {hn_metrics['false_merge_rate']:.4f} (FP: {hn_metrics['false_positives']})")
    print("="*50 + "\n")

    return {
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "hn_metrics": hn_metrics,
        "baseline_results": baseline_results,
        "num_candidates": len(rows),
        "num_features": len(feature_names),
        "predictions_count": len(pred_records)
    }

if __name__ == "__main__":
    train_and_evaluate()
