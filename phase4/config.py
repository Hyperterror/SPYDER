"""
Configuration for Phase 4: GraphSAGE / Graph Embedding + Link Prediction.
Defines paths, model hyperparameters, candidate generation rules, and negative sampling types.
"""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
GRAPH_ANALYSIS_DIR = BASE_DIR / "output" / "graph_analysis"
NODES_PATH = GRAPH_ANALYSIS_DIR / "nodes.csv"
EDGES_PATH = GRAPH_ANALYSIS_DIR / "edges.csv"
CASE_GRAPH_PATH = GRAPH_ANALYSIS_DIR / "case_graph.json"
NODE_METRICS_PATH = GRAPH_ANALYSIS_DIR / "node_metrics.csv"
COMMUNITIES_PATH = GRAPH_ANALYSIS_DIR / "communities.csv"

GROUND_TRUTH_DIR = BASE_DIR / "synthetic_data_generator" / "output" / "ground_truth"
OUTPUT_DIR = BASE_DIR / "output" / "graphsage"
MODEL_DIR = OUTPUT_DIR / "model"

# Model Hyperparameters
HIDDEN_DIM = 64
EMBED_DIM = 32
DROPOUT = 0.2
LEARNING_RATE = 0.005
WEIGHT_DECAY = 1e-4
NUM_EPOCHS = 120
RANDOM_SEED = 42

# Candidate Generation & Negative Sampling
TARGET_NODE_TYPES = {"PERSON"}
NEGATIVE_RATIO = 3  # Ratio of negatives to positives in training
HARD_NEGATIVE_RATIO = 0.5  # Fraction of negatives that are structured hard negatives

# Priority Lead Thresholds
THRESHOLD_HIGH_PRIORITY = 0.70
THRESHOLD_REVIEW = 0.40

# Known Public Infrastructure & Ambiguous Identifiers
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

KNOWN_SHARED_BUSES = {
    "VEH_026",  # High-fanout commercial sleeper bus
    "JH-48-DL-2259"
}

GENERIC_LOCATIONS = {
    "LOC_Delhi_NCR",
    "LOC_Kolkata",
    "LOC_Patna",
    "LOC_Siliguri"
}
