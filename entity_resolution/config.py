"""
Configuration parameters for Phase 2: Entity Resolution.
"""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "synthetic_data_generator" / "output" / "evidence_dataset"
GROUND_TRUTH_DIR = BASE_DIR / "synthetic_data_generator" / "output" / "ground_truth"

OUTPUT_DIR = BASE_DIR / "output" / "entity_resolution"
MODEL_DIR = OUTPUT_DIR / "model"
REPORTS_DIR = OUTPUT_DIR / "reports"

# Random Seed for Reproducibility
RANDOM_SEED = 42

# Sentence Transformer Configuration
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_CACHE_FILE = OUTPUT_DIR / "embedding_cache.pkl"

# Confidence Tier Thresholds
TIER_HIGH_THRESHOLD = 0.90
TIER_MEDIUM_THRESHOLD = 0.70

TIER_HIGH_LABEL = "HIGH CONFIDENCE"
TIER_MEDIUM_LABEL = "REVIEW REQUIRED"
TIER_LOW_LABEL = "LOW CONFIDENCE / LIKELY DIFFERENT"

# Case-Aware Train / Val / Test Split
# To prevent trivial entity leakage across cases:
TRAIN_CASES = ["CASE_001", "CASE_003", "CASE_002", "CASE_005", "CASE_004"]
VAL_CASES = ["CASE_007", "CASE_008"]
TEST_CASES = ["CASE_009", "CASE_006", "CASE_010"]

# XGBoost Hyperparameters
XGBOOST_PARAMS = {
    "n_estimators": 100,
    "max_depth": 4,
    "learning_rate": 0.08,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 2,
    "random_state": RANDOM_SEED,
    "eval_metric": "logloss",
}

# Forbidden feature tokens (data leakage audit)
FORBIDDEN_FEATURE_TOKENS = [
    "global",
    "entity_id",
    "true_role",
    "syndicate",
    "ground_truth",
    "canonical_role",
    "network_cluster",
    "case_memberships",
]
