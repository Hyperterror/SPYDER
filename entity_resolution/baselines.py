"""
Baseline Models for Entity Resolution.
Implements:
1. Exact Identifier Matching Rule (Phone / IMEI / Vehicle Reg)
2. Name Similarity Threshold Rule (Levenshtein / Jaro-Winkler >= 0.85)
"""

from typing import List, Dict, Any
from entity_resolution.evaluate import compute_metrics

class ExactIdentifierBaseline:
    """Predicts a match if any strong identifier (phone, IMEI, vehicle) matches exactly."""
    def predict(self, rows: List[Dict[str, Any]]) -> List[int]:
        preds = []
        for r in rows:
            phone_match = r.get("phone_exact_match", 0.0) == 1.0
            imei_match = r.get("imei_match", 0.0) == 1.0
            veh_match = r.get("vehicle_reg_match", 0.0) == 1.0
            
            # Predict 1 if any exact identifier matches
            if phone_match or imei_match or veh_match:
                preds.append(1)
            else:
                preds.append(0)
        return preds

class NameSimilarityBaseline:
    """Predicts a match if surface name similarity exceeds high threshold (>= 0.85)."""
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    def predict(self, rows: List[Dict[str, Any]]) -> List[int]:
        preds = []
        for r in rows:
            lev_sim = r.get("name_levenshtein_sim", 0.0)
            jw_sim = r.get("name_jaro_winkler_sim", 0.0)
            if max(lev_sim, jw_sim) >= self.threshold:
                preds.append(1)
            else:
                preds.append(0)
        return preds

def evaluate_baselines(test_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Evaluates both baselines on the test set."""
    y_true = [r["same_entity"] for r in test_rows]

    # Baseline 1
    b1 = ExactIdentifierBaseline()
    b1_preds = b1.predict(test_rows)
    b1_metrics = compute_metrics(y_true, b1_preds)

    # Baseline 2
    b2 = NameSimilarityBaseline()
    b2_preds = b2.predict(test_rows)
    b2_metrics = compute_metrics(y_true, b2_preds)

    return {
        "Baseline 1: Exact Identifier Match": b1_metrics,
        "Baseline 2: Name Similarity (>=0.85)": b2_metrics,
    }
