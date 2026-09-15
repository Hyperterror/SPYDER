"""
Evaluation Metrics Module for Entity Resolution.
Computes Accuracy, Precision, Recall, F1, ROC-AUC, PR-AUC,
False Merge Rate (FMR), and False Split Rate (FSR).
"""

from typing import Dict, List, Any, Optional
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix
)

def compute_metrics(y_true: List[int], y_pred: List[int], y_prob: Optional[List[float]] = None) -> Dict[str, float]:
    """
    Computes comprehensive identity resolution evaluation metrics.
    """
    y_t = np.array(y_true)
    y_p = np.array(y_pred)

    if len(y_t) == 0:
        return {}

    acc = float(accuracy_score(y_t, y_p))
    prec = float(precision_score(y_t, y_p, zero_division=0))
    rec = float(recall_score(y_t, y_p, zero_division=0))
    f1 = float(f1_score(y_t, y_p, zero_division=0))

    # Confusion matrix: tn, fp, fn, tp
    cm = confusion_matrix(y_t, y_p, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    # False Merge Rate = FP / (FP + TN)
    fmr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    # False Split Rate = FN / (FN + TP)
    fsr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0

    roc_auc = 0.5
    pr_auc = 0.0
    if y_prob is not None and len(np.unique(y_t)) > 1:
        try:
            roc_auc = float(roc_auc_score(y_t, y_prob))
            pr_auc = float(average_precision_score(y_t, y_prob))
        except Exception:
            pass

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "false_merge_rate": round(fmr, 4),
        "false_split_rate": round(fsr, 4),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "total_samples": int(len(y_t)),
    }
