"""
Comprehensive Automated Test Suite for Phase 4:
GraphSAGE / Graph Embedding + Link Prediction.
Covers graph loading, typed features, candidate generation, negative sampling A-G,
case-aware & entity-disjoint splits, GraphSAGE forward pass, decoder outputs,
hard-negative safety (public Wi-Fi, commercial bus, generic location),
provenance preservation, determinism, and static leakage audit.
"""

import unittest
from pathlib import Path
import numpy as np
import torch

from phase4.config import (
    OUTPUT_DIR, KNOWN_PUBLIC_IPS, KNOWN_SHARED_BUSES, GENERIC_LOCATIONS
)
from phase4.graph_loader import GraphLoader
from phase4.features import FeatureExtractor
from phase4.candidate_generation import CandidateGenerator
from phase4.split import DataSplitter
from phase4.model import GraphSAGEModel, DotProductDecoder, CosineDecoder, MLPDecoder
from phase4.baselines import BaselineEvaluator
from phase4.predict import LinkPredictor
from phase4.leakage_audit import LeakageAuditor

class TestPhase4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = GraphLoader()
        cls.multi_graph = cls.loader.load_graph()
        cls.norm_adj = cls.loader.build_normalized_adj()

        cls.extractor = FeatureExtractor()
        cls.x, cls.feature_names = cls.extractor.extract_node_features(
            cls.multi_graph, cls.loader.node_to_idx
        )

        cls.candidate_gen = CandidateGenerator(cls.multi_graph, random_seed=42)
        cls.candidates = cls.candidate_gen.generate_all_candidates()

        cls.splitter = DataSplitter(cls.candidates, random_seed=42)
        cls.case_split = cls.splitter.create_case_aware_split()
        cls.entity_split = cls.splitter.create_entity_disjoint_split()

        cls.model = GraphSAGEModel(
            in_dim=cls.x.shape[1],
            hidden_dim=64,
            embed_dim=32,
            decoder_type="mlp",
            dropout=0.0
        )

    def test_01_graph_loading_integrity(self):
        """Verifies graph node and edge counts match Phase 3 output."""
        self.assertGreaterEqual(self.multi_graph.number_of_nodes(), 1000)
        self.assertGreaterEqual(self.multi_graph.number_of_edges(), 5000)
        self.assertEqual(len(self.loader.node_to_idx), self.multi_graph.number_of_nodes())

    def test_02_node_feature_matrix_integrity(self):
        """Verifies dense feature matrix shape, finite values, and absence of NaNs."""
        self.assertEqual(self.x.shape[0], len(self.loader.node_to_idx))
        self.assertGreaterEqual(self.x.shape[1], 25)
        self.assertFalse(torch.isnan(self.x).any(), "NaN detected in feature matrix")
        self.assertFalse(torch.isinf(self.x).any(), "Inf detected in feature matrix")

    def test_03_edge_type_preservation(self):
        """Verifies edge types, weights, and provenance fields are preserved."""
        edge_types = set()
        for _, _, d in self.multi_graph.edges(data=True):
            edge_types.add(d.get("edge_type"))
            self.assertIn("provenance_table", d)
            self.assertIn("provenance_record_id", d)
        self.assertIn("APPEARS_IN", edge_types)
        self.assertIn("CALLED", edge_types)
        self.assertIn("OBSERVES_ENTITY", edge_types)

    def test_04_candidate_generation_and_positive_exclusion(self):
        """Verifies candidate pairs contain positives and negatives, and exclude duplicate pairs."""
        labels = [c["label"] for c in self.candidates]
        self.assertIn(1, labels, "No positive links found")
        self.assertIn(0, labels, "No negative links found")

        # Ensure no negative is accidentally an observed positive
        pos_pairs = self.candidate_gen.observed_positive_pairs
        for c in self.candidates:
            if c["label"] == 0:
                pair = tuple(sorted([c["source"], c["target"]]))
                self.assertNotIn(pair, pos_pairs, f"Negative pair {pair} is an observed positive tie!")

    def test_05_negative_sampling_diversity_a_through_g(self):
        """Verifies all 7 negative categories (A through G) are present in the candidate dataset."""
        categories = {c.get("category") for c in self.candidates}
        expected_categories = {
            "POSITIVE",
            "NEG_A_RANDOM",
            "NEG_B_SAME_CASE_HARD",
            "NEG_C_CROSS_CASE_HARD",
            "NEG_D_SHARED_LOCATION",
            "NEG_E_SHARED_COMMERCIAL_VEHICLE",
            "NEG_F_SHARED_PUBLIC_IP",
            "NEG_G_HIGH_DEGREE_HUB"
        }
        for exp in expected_categories:
            self.assertIn(exp, categories, f"Negative category {exp} is missing from candidate pool")

    def test_06_case_aware_split_disclosure(self):
        """Verifies case-aware split correctly partitions case files and discloses entity overlaps."""
        split = self.case_split
        self.assertGreater(split["train_count"], 0)
        self.assertGreater(split["val_count"], 0)
        self.assertGreater(split["test_count"], 0)
        self.assertIn("leakage_disclosure", split)
        self.assertIsInstance(split["entity_overlap_count"], int)

    def test_07_strict_entity_disjoint_split(self):
        """MANDATORY GENERALIZATION BENCHMARK: Asserts zero entity overlap in entity-disjoint split."""
        split = self.entity_split
        self.assertTrue(split["is_strictly_entity_disjoint"])
        self.assertEqual(split["entity_overlap_count"], 0, "Entity overlap detected in entity-disjoint split!")

    def test_08_graphsage_encoder_forward_pass(self):
        """Verifies GraphSAGE forward pass computes normalized embeddings of shape (N, 32)."""
        self.model.eval()
        with torch.no_grad():
            z = self.model.encode(self.x, self.norm_adj)
        self.assertEqual(z.shape, (len(self.loader.node_to_idx), 32))
        
        # Verify L2 normalization
        norms = torch.norm(z, p=2, dim=-1)
        self.assertTrue(torch.allclose(norms, torch.ones_like(norms), atol=1e-5))

    def test_09_link_decoders_and_prediction_range(self):
        """Verifies Dot-Product, Cosine, and MLP decoders output valid probabilities in [0, 1]."""
        z = torch.randn(10, 32)
        u_idx = torch.tensor([0, 1, 2], dtype=torch.long)
        v_idx = torch.tensor([3, 4, 5], dtype=torch.long)

        for dec_type in ["mlp", "dot", "cosine"]:
            model = GraphSAGEModel(in_dim=self.x.shape[1], embed_dim=32, decoder_type=dec_type)
            model.eval()
            with torch.no_grad():
                preds = model.decode(z, u_idx, v_idx)
            self.assertEqual(preds.shape, (3,))
            self.assertTrue((preds >= 0.0).all() and (preds <= 1.0).all(), f"Decoder {dec_type} out of [0, 1]")

    def test_10_public_infrastructure_hard_negative_safety(self):
        """
        SAFETY TEST: Confirms pairs connected only by public Wi-Fi (103.21.244.18)
        are categorized as hard negatives with low average prediction scores.
        """
        pub_pairs = [c for c in self.candidates if c.get("category") == "NEG_F_SHARED_PUBLIC_IP"]
        self.assertGreater(len(pub_pairs), 0, "No public IP hard negatives found")
        
        u_idx = torch.tensor([self.loader.node_to_idx[p["source"]] for p in pub_pairs], dtype=torch.long)
        v_idx = torch.tensor([self.loader.node_to_idx[p["target"]] for p in pub_pairs], dtype=torch.long)
        
        with torch.no_grad():
            preds = self.model.decode(self.model.encode(self.x, self.norm_adj), u_idx, v_idx).numpy()
        
        mean_score = preds.mean()
        self.assertLess(mean_score, 0.70, "Public Wi-Fi hard negatives produced high average prediction scores!")

    def test_11_commercial_bus_hard_negative_safety(self):
        """
        SAFETY TEST: Confirms pairs connected only by commercial sleeper bus (VEH_026)
        are properly isolated as hard negatives.
        """
        bus_pairs = [c for c in self.candidates if c.get("category") == "NEG_E_SHARED_COMMERCIAL_VEHICLE"]
        self.assertGreater(len(bus_pairs), 0, "No commercial bus hard negatives found")

        u_idx = torch.tensor([self.loader.node_to_idx[p["source"]] for p in bus_pairs], dtype=torch.long)
        v_idx = torch.tensor([self.loader.node_to_idx[p["target"]] for p in bus_pairs], dtype=torch.long)
        with torch.no_grad():
            preds = self.model.decode(self.model.encode(self.x, self.norm_adj), u_idx, v_idx).numpy()

        mean_score = preds.mean()
        self.assertLess(mean_score, 0.70, "Commercial transit bus created high prediction scores!")

    def test_12_generic_location_hard_negative_safety(self):
        """
        SAFETY TEST: Confirms pairs sharing only generic city transit (LOC_Delhi_NCR)
        do not automatically receive high association scores.
        """
        loc_pairs = [c for c in self.candidates if c.get("category") == "NEG_D_SHARED_LOCATION"]
        self.assertGreater(len(loc_pairs), 0, "No generic location hard negatives found")

        u_idx = torch.tensor([self.loader.node_to_idx[p["source"]] for p in loc_pairs], dtype=torch.long)
        v_idx = torch.tensor([self.loader.node_to_idx[p["target"]] for p in loc_pairs], dtype=torch.long)
        with torch.no_grad():
            preds = self.model.decode(self.model.encode(self.x, self.norm_adj), u_idx, v_idx).numpy()

        mean_score = preds.mean()
        self.assertLess(mean_score, 0.70, "Generic city location produced high prediction scores!")

    def test_13_deterministic_inference(self):
        """Verifies deterministic forward pass produces identical embeddings under fixed seed."""
        torch.manual_seed(42)
        with torch.no_grad():
            z1 = self.model.encode(self.x, self.norm_adj)
        
        torch.manual_seed(42)
        with torch.no_grad():
            z2 = self.model.encode(self.x, self.norm_adj)
        
        self.assertTrue(torch.equal(z1, z2), "GraphSAGE inference is not deterministic!")

    def test_14_static_leakage_audit(self):
        """CRITICAL AUDIT: Asserts zero ground-truth tokens in Phase 4 code files and feature names."""
        auditor = LeakageAuditor()
        report = auditor.run_full_audit(self.feature_names)
        self.assertTrue(report["is_certified_leakage_free"], "Ground truth leakage detected in Phase 4!")

    def test_15_baseline_evaluator_runs_cleanly(self):
        """Verifies heuristic baselines evaluate without crashing."""
        evaluator = BaselineEvaluator(self.multi_graph)
        results = evaluator.evaluate_candidates(self.candidates[:50])
        self.assertIn("common_neighbors", results)
        self.assertIn("jaccard_similarity", results)
        self.assertIn("adamic_adar", results)
        self.assertIn("mrr", results["adamic_adar"])

    def test_16_edge_disjoint_and_temporal_splits_and_target_leakage_audit(self):
        """Verifies masked training graph removes held-out target edges with zero target-edge leakage."""
        edge_split = self.splitter.create_edge_disjoint_split()
        temporal_split = self.splitter.create_temporal_split(self.multi_graph)

        self.assertGreater(edge_split["held_out_edges_count"], 0)
        self.assertGreater(edge_split["test_count"], 0)
        self.assertGreater(temporal_split["test_count"], 0)

        held_out = edge_split["held_out_edges"]
        masked_g = self.loader.build_masked_graph(held_out)
        norm_adj_masked = self.loader.build_normalized_adj(excluded_edges=held_out, graph=masked_g)
        x_masked, _ = self.extractor.extract_node_features(
            masked_g, self.loader.node_to_idx, recompute_centrality=True
        )

        self.assertEqual(x_masked.shape, self.x.shape)
        self.assertFalse(torch.isnan(x_masked).any())

        leak_report = LeakageAuditor().audit_target_edge_leakage(
            norm_adj_masked, self.loader.node_to_idx, held_out
        )
        self.assertTrue(leak_report["zero_target_edge_leakage"])
        self.assertEqual(leak_report["leaked_count"], 0)

    def test_17_ranking_and_calibration_metrics_and_fair_baselines(self):
        """Verifies ranking (P@10, R@20, MRR) and calibration (Brier, ECE) metrics on masked split."""
        from phase4.evaluate import Phase4Evaluator
        evaluator = Phase4Evaluator(
            model=self.model,
            x=self.x,
            norm_adj=self.norm_adj,
            node_to_idx=self.loader.node_to_idx,
            multi_graph=self.multi_graph,
        )
        metrics = evaluator.evaluate_split(self.case_split["test_pairs"], split_name="UnitTest")
        for key in ["precision_at_10", "recall_at_20", "mrr", "brier_score", "ece"]:
            self.assertIn(key, metrics)
            self.assertGreaterEqual(metrics[key], 0.0)
            self.assertLessEqual(metrics[key], 1.0)

if __name__ == "__main__":
    unittest.main()
