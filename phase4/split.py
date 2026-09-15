"""
Dataset Splitting Module for Phase 4.
Implements:
1. Case-Aware Holdout (training on distinct case files, testing on unseen cases)
2. Strict Entity-Disjoint Holdout (no person entity overlaps between train and test)
3. Hard-Negative Benchmark Evaluation Set
Explicitly reports case IDs, entity counts, train/test entity overlaps, and class balances.
"""

from typing import Dict, List, Set, Any, Tuple, Optional
import random

from phase4.config import RANDOM_SEED

class DataSplitter:
    def __init__(self, candidates: List[Dict[str, Any]], random_seed: int = RANDOM_SEED):
        self.candidates = candidates
        self.rng = random.Random(random_seed)

    def create_case_aware_split(
        self,
        train_cases: Optional[Set[str]] = None,
        val_cases: Optional[Set[str]] = None,
        test_cases: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Splits candidate pairs by Case IDs:
        Train: CASE_001, CASE_002, CASE_004, CASE_005, CASE_006, CASE_008, CASE_010 (7 cases)
        Val:   CASE_003 (1 case)
        Test:  CASE_007, CASE_009 (2 cases)
        Discloses underlying entity overlaps between splits.
        """
        if train_cases is None:
            train_cases = {"CASE_001", "CASE_002", "CASE_004", "CASE_005", "CASE_006", "CASE_008", "CASE_010"}
        if val_cases is None:
            val_cases = {"CASE_003"}
        if test_cases is None:
            test_cases = {"CASE_007", "CASE_009"}

        train_pairs, val_pairs, test_pairs = [], [], []

        for c in self.candidates:
            c_src = set(c["source_cases"].split("; ")) if c.get("source_cases") else set()
            c_tgt = set(c["target_cases"].split("; ")) if c.get("target_cases") else set()
            all_c = c_src | c_tgt

            # Assign to test if both ends touch test cases
            if all_c & test_cases:
                test_pairs.append(c)
            elif all_c & val_cases:
                val_pairs.append(c)
            else:
                train_pairs.append(c)

        # Entity overlap audit
        train_entities = {p["source"] for p in train_pairs} | {p["target"] for p in train_pairs}
        test_entities = {p["source"] for p in test_pairs} | {p["target"] for p in test_pairs}
        overlap = train_entities & test_entities

        return {
            "name": "Case-Aware Split",
            "train_cases": sorted(list(train_cases)),
            "val_cases": sorted(list(val_cases)),
            "test_cases": sorted(list(test_cases)),
            "train_pairs": train_pairs,
            "val_pairs": val_pairs,
            "test_pairs": test_pairs,
            "train_count": len(train_pairs),
            "val_count": len(val_pairs),
            "test_count": len(test_pairs),
            "train_entities_count": len(train_entities),
            "test_entities_count": len(test_entities),
            "entity_overlap_count": len(overlap),
            "entity_overlap_entities": sorted(list(overlap)),
            "is_strictly_entity_disjoint": len(overlap) == 0,
            "leakage_disclosure": f"Case-aware split contains {len(overlap)} overlapping entities across cross-case boundaries." if overlap else "Zero entity overlap."
        }

    def create_entity_disjoint_split(
        self,
        test_entity_ratio: float = 0.25
    ) -> Dict[str, Any]:
        """
        Creates a strict entity-disjoint split:
        P_train ∩ P_test = ∅.
        Treated as the strongest generalization benchmark.
        """
        all_persons = sorted(list({c["source"] for c in self.candidates} | {c["target"] for c in self.candidates}))
        self.rng.shuffle(all_persons)

        num_test = int(len(all_persons) * test_entity_ratio)
        test_persons = set(all_persons[:num_test])
        train_persons = set(all_persons[num_test:])

        train_pairs = []
        test_pairs = []
        val_pairs = []

        # Pairs where both nodes are in train_persons go to train/val
        for c in self.candidates:
            u, v = c["source"], c["target"]
            if u in test_persons and v in test_persons:
                test_pairs.append(c)
            elif u in train_persons and v in train_persons:
                if self.rng.random() < 0.15:
                    val_pairs.append(c)
                else:
                    train_pairs.append(c)

        train_entities = {p["source"] for p in train_pairs} | {p["target"] for p in train_pairs}
        test_entities = {p["source"] for p in test_pairs} | {p["target"] for p in test_pairs}
        overlap = train_entities & test_entities

        return {
            "name": "Strict Entity-Disjoint Split",
            "train_pairs": train_pairs,
            "val_pairs": val_pairs,
            "test_pairs": test_pairs,
            "train_count": len(train_pairs),
            "val_count": len(val_pairs),
            "test_count": len(test_pairs),
            "train_entities_count": len(train_entities),
            "test_entities_count": len(test_entities),
            "entity_overlap_count": len(overlap),
            "is_strictly_entity_disjoint": len(overlap) == 0,
            "leakage_disclosure": "Strictly entity-disjoint: exactly zero person entity overlap between train and test."
        }

    def extract_hard_negative_evaluation_set(self) -> List[Dict[str, Any]]:
        """
        Extracts all structured hard negatives (Types D, E, F, G) for dedicated safety reporting.
        """
        hard_types = {
            "NEG_D_SHARED_LOCATION",
            "NEG_E_SHARED_COMMERCIAL_VEHICLE",
            "NEG_F_SHARED_PUBLIC_IP",
            "NEG_G_HIGH_DEGREE_HUB"
        }
        return [c for c in self.candidates if c.get("category") in hard_types]
