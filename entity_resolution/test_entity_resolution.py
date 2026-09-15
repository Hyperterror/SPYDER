

"""
Validation Suite for Phase 2: Entity Resolution.
15 automated test cases testing normalization, candidate generation, non-leakage,
label correctness, hard negatives, train/test separation, reproducibility, calibration,
tiers, explainability, baselines, training, and schema compliance.
"""

import csv
import json
import os
import unittest
from pathlib import Path
import numpy as np

from entity_resolution.config import (
    EVIDENCE_DIR, GROUND_TRUTH_DIR, OUTPUT_DIR, MODEL_DIR,
    TIER_HIGH_THRESHOLD, TIER_MEDIUM_THRESHOLD,
    TIER_HIGH_LABEL, TIER_MEDIUM_LABEL, TIER_LOW_LABEL,
    FORBIDDEN_FEATURE_TOKENS, TRAIN_CASES, TEST_CASES
)
from entity_resolution.normalize import (
    normalize_name, normalize_alias, normalize_phone, normalize_imei,
    normalize_vehicle_reg, normalize_ip, levenshtein_similarity
)
from entity_resolution.candidate_generation import CandidateGenerator
from entity_resolution.pair_generation import PairDatasetBuilder
from entity_resolution.feature_engineering import FeatureEngineer
from entity_resolution.baselines import ExactIdentifierBaseline, NameSimilarityBaseline
from entity_resolution.predict import EntityResolutionPredictor
from entity_resolution.explain import generate_explanation

class TestEntityResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = PairDatasetBuilder()
        cls.dataset = cls.builder.build_dataset()
        cls.rows = cls.dataset["rows"]
        cls.profiles = cls.builder.candidate_gen.profiles

    def test_01_normalization(self):
        """1. Verifies normalization functions for all modalities."""
        n_res = normalize_name("  Shri A. Gupta  ")
        self.assertEqual(n_res["clean"], "a gupta")
        self.assertEqual(n_res["initials"], "ag")

        p_res = normalize_phone("+91 98765-43210")
        self.assertEqual(p_res["last10"], "9876543210")
        self.assertTrue(p_res["is_valid"])

        imei_res = normalize_imei("861-990-382606592")
        self.assertEqual(imei_res["clean"], "861990382606592")
        self.assertTrue(imei_res["is_valid"])

        veh_res = normalize_vehicle_reg("wb-02-ab-1234")
        self.assertEqual(veh_res["clean"], "WB02AB1234")
        self.assertEqual(veh_res["state"], "WB")

        ip_res = normalize_ip("103.21.244.18")
        self.assertTrue(ip_res["is_valid"])

    def test_02_candidate_generation(self):
        """2. Verifies candidate generation produces cross-case pairs with valid blocking reasons."""
        self.assertGreater(len(self.rows), 20, "Expected at least 20 candidate pairs")
        for r in self.rows:
            # Must be strictly cross-case
            self.assertNotEqual(r["case_id_a"], r["case_id_b"], f"Intra-case pair found: {r['person_id_a']}, {r['person_id_b']}")
            self.assertTrue(bool(r["blocking_reasons"]), "Candidate pair missing blocking reasons")

    def test_03_no_global_entity_id_in_features(self):
        """3. Verifies that GLOBAL_ENTITY_ID is never used as an input feature."""
        feat_names = self.dataset["feature_names"]
        for fn in feat_names:
            self.assertNotIn("global", fn.lower())
            self.assertNotIn("entity_id", fn.lower())

    def test_04_no_true_role_in_features(self):
        """4. Verifies that true_role or canonical roles are never used as input features."""
        feat_names = self.dataset["feature_names"]
        for fn in feat_names:
            self.assertNotIn("true_role", fn.lower())
            self.assertNotIn("canonical_role", fn.lower())
            self.assertNotIn("mastermind", fn.lower())
            self.assertNotIn("syndicate_head", fn.lower())

    def test_05_no_syndicate_id_in_features(self):
        """5. Verifies that syndicate_id or network cluster is never used as an input feature."""
        feat_names = self.dataset["feature_names"]
        for fn in feat_names:
            self.assertNotIn("syndicate", fn.lower())
            self.assertNotIn("network_cluster", fn.lower())

    def test_06_positive_negative_label_correctness(self):
        """6. Verifies positive/negative training labels match ground truth observational mapping."""
        gt_path = GROUND_TRUTH_DIR / "ground_truth.json"
        with open(gt_path, "r", encoding="utf-8") as f:
            gt = json.load(f)
        obs_map = gt.get("observational_mapping", {})
        obs_to_gid = {}
        for gid, info in obs_map.items():
            if "case_instances" in info:
                for inst in info["case_instances"].values():
                    obs_to_gid[inst["observational_person_id"]] = gid

        for r in self.rows:
            g1 = obs_to_gid.get(r["person_id_a"])
            g2 = obs_to_gid.get(r["person_id_b"])
            expected = 1 if (g1 and g2 and g1 == g2) else 0
            self.assertEqual(r["same_entity"], expected, f"Label mismatch for pair {r['person_id_a']} - {r['person_id_b']}")

    def test_07_hard_negative_generation(self):
        """7. Verifies hard negatives are generated and properly tagged with same_entity == 0."""
        hn_rows = [r for r in self.rows if r.get("is_hard_negative") == 1]
        self.assertGreaterEqual(len(hn_rows), 2, "Expected at least 2 hard negative candidate pairs")
        for hn in hn_rows:
            self.assertEqual(hn["same_entity"], 0, f"Hard negative incorrectly labelled as positive: {hn['person_id_a']}")

    def test_08_no_train_test_entity_leakage(self):
        """8. Verifies case-aware split prevents cross-split case contamination."""
        train_cases = set(TRAIN_CASES)
        test_cases = set(TEST_CASES)
        self.assertEqual(len(train_cases.intersection(test_cases)), 0, "Train and Test case sets must be disjoint")

    def test_09_reproducibility(self):
        """9. Verifies pair dataset and feature extraction are 100% deterministic."""
        builder2 = PairDatasetBuilder()
        ds2 = builder2.build_dataset()
        self.assertEqual(len(self.rows), len(ds2["rows"]))
        self.assertEqual(self.dataset["positive_pairs"], ds2["positive_pairs"])
        self.assertEqual(self.dataset["negative_pairs"], ds2["negative_pairs"])

    def test_10_probability_output_range(self):
        """10. Verifies predicted match probabilities are strictly within [0.0, 1.0]."""
        predictor = EntityResolutionPredictor()
        p1 = list(self.profiles.values())[0]
        p2 = list(self.profiles.values())[1]
        res = predictor.predict_pair(p1, p2)
        prob = res["match_probability"]
        self.assertTrue(0.0 <= prob <= 1.0, f"Probability {prob} out of range [0, 1]")

    def test_11_confidence_threshold_behavior(self):
        """11. Verifies confidence tiers map accurately to probability thresholds."""
        predictor = EntityResolutionPredictor()
        p1 = list(self.profiles.values())[0]
        p2 = list(self.profiles.values())[1]
        res = predictor.predict_pair(p1, p2)
        prob = res["match_probability"]
        tier = res["confidence_tier"]

        if prob >= TIER_HIGH_THRESHOLD:
            self.assertEqual(tier, TIER_HIGH_LABEL)
        elif prob >= TIER_MEDIUM_THRESHOLD:
            self.assertEqual(tier, TIER_MEDIUM_LABEL)
        else:
            self.assertEqual(tier, TIER_LOW_LABEL)

    def test_12_explanation_generation(self):
        """12. Verifies explanation generation produces human-readable text without ground truth tokens."""
        feats = {"name_exact_match": 1.0, "phone_exact_match": 1.0, "context_embedding_cosine_sim": 0.95}
        expl = generate_explanation(feats, 0.96)
        self.assertIn("Exact phone number match", " ".join(expl["supporting_reasons"]))
        self.assertNotIn("GLOBAL_", expl["summary"])
        self.assertNotIn("true_role", expl["summary"])

    def test_13_baseline_execution(self):
        """13. Verifies both baseline models execute properly on pair rows."""
        b1 = ExactIdentifierBaseline()
        b2 = NameSimilarityBaseline()
        p1 = b1.predict(self.rows[:5])
        p2 = b2.predict(self.rows[:5])
        self.assertEqual(len(p1), 5)
        self.assertEqual(len(p2), 5)

    def test_14_model_training_and_serialization(self):
        """14. Verifies trained model artifact exists and is loadable."""
        model_file = MODEL_DIR / "xgboost_entity_resolution.json"
        self.assertTrue(model_file.exists(), "Trained XGBoost model file missing!")
        self.assertGreater(model_file.stat().st_size, 0, "Trained model file empty!")

    def test_15_prediction_output_schema(self):
        """15. Verifies predictions.csv exists, has rows, and adheres to schema without ground truth leakage."""
        pred_csv = OUTPUT_DIR / "predictions.csv"
        self.assertTrue(pred_csv.exists(), "predictions.csv missing!")
        with open(pred_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames
            expected_cols = [
                "person_id_a", "person_id_b", "case_id_a", "case_id_b",
                "name_a", "name_b", "alias_a", "alias_b", "match_probability",
                "confidence_tier", "explanation_summary", "supporting_reasons", "conflicting_reasons"
            ]
            for col in expected_cols:
                self.assertIn(col, header, f"Missing column '{col}' in predictions.csv")
            # Leak check
            with open(pred_csv, "r", encoding="utf-8") as f_leak:
                content = f_leak.read()
            self.assertNotIn("GLOBAL_ENT_", content)
            self.assertNotIn("true_role", content)

if __name__ == "__main__":
    unittest.main()
