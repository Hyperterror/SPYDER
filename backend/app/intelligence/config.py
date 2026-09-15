"""
Configuration for Phase 5A: Backend Intelligence Integration Layer.
Defines paths to frozen Phase 3 and Phase 4 artifacts, priority thresholds,
and known public infrastructure registries for hard-negative suppression.
"""

from pathlib import Path
from typing import Set

# Base repository root (backend/app/intelligence -> repo root is 3 levels up from backend/)
INTELLIGENCE_DIR = Path(__file__).resolve().parent
APP_DIR = INTELLIGENCE_DIR.parent
BACKEND_DIR = APP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

# Phase 4 Artifact Paths
PHASE4_OUTPUT_DIR = REPO_ROOT / "output" / "graphsage"
PREDICTIONS_PATH = PHASE4_OUTPUT_DIR / "predictions.csv"
CANDIDATE_LINKS_PATH = PHASE4_OUTPUT_DIR / "candidate_links.csv"
NODE_EMBEDDINGS_PATH = PHASE4_OUTPUT_DIR / "node_embeddings.csv"
HARD_NEGATIVE_METRICS_PATH = PHASE4_OUTPUT_DIR / "hard_negative_metrics.json"
BASELINE_METRICS_PATH = PHASE4_OUTPUT_DIR / "baseline_metrics.json"
TRAIN_METRICS_PATH = PHASE4_OUTPUT_DIR / "train_metrics.json"
VALIDATION_METRICS_PATH = PHASE4_OUTPUT_DIR / "validation_metrics.json"
TEST_METRICS_PATH = PHASE4_OUTPUT_DIR / "test_metrics.json"
LEAKAGE_AUDIT_PATH = PHASE4_OUTPUT_DIR / "leakage_audit.json"
REPORT_MD_PATH = PHASE4_OUTPUT_DIR / "report.md"

# Phase 3 Knowledge Graph Artifacts (for concrete provenance retrieval)
GRAPH_ANALYSIS_DIR = REPO_ROOT / "output" / "graph_analysis"
EDGES_PATH = GRAPH_ANALYSIS_DIR / "edges.csv"
NODES_PATH = GRAPH_ANALYSIS_DIR / "nodes.csv"
CASE_GRAPH_PATH = GRAPH_ANALYSIS_DIR / "case_graph.json"

# Deterministic Priority Thresholds (aligned with Phase 4 config)
THRESHOLD_HIGH_PRIORITY: float = 0.70
THRESHOLD_REVIEW: float = 0.40

# Hard Negative Categories from Phase 4
HARD_NEGATIVE_CATEGORIES: Set[str] = {
    "NEG_A_RANDOM",
    "NEG_B_SAME_CASE_HARD",
    "NEG_C_CROSS_CASE_HARD",
    "NEG_D_SHARED_LOCATION",
    "NEG_E_SHARED_COMMERCIAL_VEHICLE",
    "NEG_F_SHARED_PUBLIC_IP",
    "NEG_G_HIGH_DEGREE_HUB",
}

# Known Public Infrastructure & Ambiguous Identifiers (to prevent false high-priority leads)
KNOWN_PUBLIC_IPS: Set[str] = {
    "103.21.244.18",
    "49.205.12.87",
    "117.247.88.102",
}

KNOWN_SHARED_BUSES: Set[str] = {
    "VEH_026",
    "JH-48-DL-2259",
}

GENERIC_LOCATIONS: Set[str] = {
    "LOC_Delhi_NCR",
    "LOC_New_Delhi",
    "LOC_Anand_Vihar_(Delhi)",
    "LOC_Kolkata",
    "LOC_Patna",
}
