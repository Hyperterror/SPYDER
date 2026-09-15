"""
Configuration for Phase 3 Global Case Knowledge Graph & Network Analysis.
Defines paths, thresholds, scoring weights, and safety limits.
"""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "synthetic_data_generator" / "output" / "evidence_dataset"
GROUND_TRUTH_DIR = BASE_DIR / "synthetic_data_generator" / "output" / "ground_truth"
ER_PREDICTIONS_PATH = BASE_DIR / "output" / "entity_resolution" / "predictions.csv"
OUTPUT_DIR = BASE_DIR / "output" / "graph_analysis"

# Provisional Resolved Entity Clustering Safeguards
ER_HIGH_CONFIDENCE_THRESHOLD = 0.90   # Minimum probability for provisional pairing
ER_CONFLICT_THRESHOLD = 0.50          # If an intermediate/cross-pair in candidate pool has p < 0.50, flag/block merge
MAX_TRANSITIVE_CHAIN_LENGTH = 3       # Max hops in ER cluster before requiring explicit manual review
MIN_CLUSTER_COHESION = 0.85           # Minimum average edge weight for an ER cluster to remain unflagged

# Public / Shared Infrastructure (Known Hotspots, Transit Portals, Public Hotlines)
KNOWN_PUBLIC_IPS = {
    "103.21.244.18",   # Mahipalpur Transit Lodge Public Wi-Fi
    "49.205.12.87",    # Cyber Kiosk Shared Broadband
    "117.247.88.102",  # Railway Station Public Wi-Fi Hotspot
}

KNOWN_PUBLIC_ACCOUNTS = {
    "ACC_SBI_IRCTC_099",  # IRCTC / Railway ticketing portal
}

KNOWN_PUBLIC_PHONES = {
    "+911123010000",  # Central transit helpline
    "+911800112233",  # National helpline
}

# Identifier Reliability Baseline Weights
IDENTIFIER_BASE_RELIABILITY = {
    "IMEI": 0.85,
    "PHONE_NUMBER": 0.75,
    "BANK_ACCOUNT": 0.80,
    "VEHICLE_REG": 0.70,
    "SOCIAL_HANDLE": 0.65,
    "IP_ADDRESS": 0.30,
    "CELL_TOWER": 0.40,
    "LOCATION": 0.35,
}

# Cross-Case Connection Scoring Weights
SCORE_WEIGHTS = {
    "evidence_diversity": 0.30,     # Distinct evidence modalities (CDR, financial, travel, device, etc.)
    "relationship_strength": 0.25, # Interaction frequency / duration
    "identifier_reliability": 0.25,# Reliability adjusted for fan-out and sharing
    "temporal_consistency": 0.20,  # Temporal proximity and chronological sequence
}

# Cross-Case Priority Tiers
TIER_HIGH_PRIORITY = "HIGH-PRIORITY LEAD"
TIER_REVIEW = "REVIEW"
TIER_LOW_PRIORITY = "LOW PRIORITY"

THRESHOLD_HIGH_PRIORITY = 0.70
THRESHOLD_REVIEW = 0.40

# Graph Analytics Parameters
MAX_CROSS_CASE_PATH_HOPS = 4
DEFAULT_TEMPORAL_WINDOW_DAYS = 30
