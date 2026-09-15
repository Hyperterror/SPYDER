"""
Phase 4: GraphSAGE / Graph Embedding + Link Prediction Module.
SIH26189 — AI-Powered Criminal Network Analysis System.
"""

from phase4.graph_loader import GraphLoader
from phase4.features import FeatureExtractor
from phase4.candidate_generation import CandidateGenerator
from phase4.split import DataSplitter
from phase4.model import (
    GraphSAGELayer, GraphSAGEEncoder, GraphSAGEModel,
    DotProductDecoder, CosineDecoder, MLPDecoder
)
from phase4.baselines import BaselineEvaluator
from phase4.train import GraphSAGETrainer
from phase4.evaluate import Phase4Evaluator
from phase4.predict import LinkPredictor
from phase4.explain import generate_prediction_explanation
from phase4.leakage_audit import LeakageAuditor

__all__ = [
    "GraphLoader",
    "FeatureExtractor",
    "CandidateGenerator",
    "DataSplitter",
    "GraphSAGELayer",
    "GraphSAGEEncoder",
    "GraphSAGEModel",
    "DotProductDecoder",
    "CosineDecoder",
    "MLPDecoder",
    "BaselineEvaluator",
    "GraphSAGETrainer",
    "Phase4Evaluator",
    "LinkPredictor",
    "generate_prediction_explanation",
    "LeakageAuditor"
]
