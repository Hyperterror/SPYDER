"""
Inference Pipeline for Entity Resolution.
Evaluates novel or ad-hoc pairs of person observations and outputs match probability,
confidence tier, and evidence-based explanations without accessing ground truth.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import xgboost as xgb

from entity_resolution.config import (
    MODEL_DIR, TIER_HIGH_THRESHOLD, TIER_MEDIUM_THRESHOLD,
    TIER_HIGH_LABEL, TIER_MEDIUM_LABEL, TIER_LOW_LABEL
)
from entity_resolution.feature_engineering import FeatureEngineer
from entity_resolution.explain import generate_explanation

class EntityResolutionPredictor:
    def __init__(self, model_path: Path = None):
        self.model_path = Path(model_path) if model_path else MODEL_DIR / "xgboost_entity_resolution.json"
        self.model = xgb.XGBClassifier()
        self.model.load_model(str(self.model_path))
        self.feature_names_path = self.model_path.parent / "feature_names.json"
        if self.feature_names_path.exists():
            import json
            with open(self.feature_names_path, "r", encoding="utf-8") as f:
                self.feature_names = json.load(f)
        else:
            self.feature_names = self.model.get_booster().feature_names or []
        self.feature_eng = FeatureEngineer()

    def predict_pair(self, p1: Dict[str, Any], p2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs full inference on a candidate pair (p1, p2).
        Returns match probability, confidence tier, and explanation.
        """
        feats = self.feature_eng.extract_features_for_pair(p1, p2)
        
        # Prepare feature vector matching model's feature names
        feature_names = self.feature_names
        X = np.array([[feats.get(fn, 0.0) for fn in feature_names]], dtype=np.float32)

        prob = float(self.model.predict_proba(X)[0, 1])

        if prob >= TIER_HIGH_THRESHOLD:
            tier = TIER_HIGH_LABEL
        elif prob >= TIER_MEDIUM_THRESHOLD:
            tier = TIER_MEDIUM_LABEL
        else:
            tier = TIER_LOW_LABEL

        expl = generate_explanation(feats, prob, p1, p2)

        return {
            "person_id_a": p1.get("person_id", ""),
            "person_id_b": p2.get("person_id", ""),
            "name_a": p1.get("raw_name", ""),
            "name_b": p2.get("raw_name", ""),
            "case_id_a": p1.get("case_id", ""),
            "case_id_b": p2.get("case_id", ""),
            "match_probability": round(prob, 4),
            "confidence_tier": tier,
            "explanation": expl,
            "features": feats
        }
