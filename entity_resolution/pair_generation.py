"""
Pair Generation and Ground Truth Labeling Module.
Extracts candidate pairs, labels them against hidden ground truth (strictly for training/eval),
extracts feature vectors, and persists candidate datasets.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

from entity_resolution.config import EVIDENCE_DIR, GROUND_TRUTH_DIR, OUTPUT_DIR
from entity_resolution.candidate_generation import CandidateGenerator
from entity_resolution.feature_engineering import FeatureEngineer
from entity_resolution.embeddings import EmbeddingManager

class PairDatasetBuilder:
    def __init__(self, evidence_dir: Path = EVIDENCE_DIR, ground_truth_dir: Path = GROUND_TRUTH_DIR, output_dir: Path = OUTPUT_DIR):
        self.evidence_dir = Path(evidence_dir)
        self.ground_truth_dir = Path(ground_truth_dir)
        self.output_dir = Path(output_dir)
        self.candidate_gen = CandidateGenerator(evidence_dir=self.evidence_dir, ground_truth_dir=self.ground_truth_dir)
        self.embedding_mgr = EmbeddingManager()
        self.feature_eng = FeatureEngineer(embedding_manager=self.embedding_mgr)

    def load_ground_truth_mapping(self) -> Tuple[Dict[str, str], Set[Tuple[str, str]]]:
        """
        Loads the hidden ground-truth mapping: observational_person_id -> global_entity_id,
        and the set of hard-negative pair IDs.
        Used EXCLUSIVELY for generating evaluation/training labels.
        """
        gt_path = self.ground_truth_dir / "ground_truth.json"
        with open(gt_path, mode="r", encoding="utf-8") as f:
            gt = json.load(f)

        obs_to_global = {}
        obs_mapping = gt.get("observational_mapping", {})
        for gid, info in obs_mapping.items():
            if "case_instances" in info:
                for cid, inst in info["case_instances"].items():
                    obs_id = inst["observational_person_id"]
                    obs_to_global[obs_id] = gid

        # Load hard-negative pair set
        hn_list = gt.get("hard_negatives", [])
        hn_by_grp = {}
        for hn in hn_list:
            grp = hn["hard_negative_group"]
            gid = hn["global_id"]
            instances = obs_mapping.get(gid, {}).get("case_instances", {})
            p_ids = [inst["observational_person_id"] for inst in instances.values()]
            hn_by_grp.setdefault(grp, []).extend(p_ids)

        hard_neg_pairs = set()
        for grp, pids in hn_by_grp.items():
            for i in range(len(pids)):
                for j in range(i + 1, len(pids)):
                    id1, id2 = pids[i], pids[j]
                    # Verify they are from different global IDs
                    if obs_to_global.get(id1) != obs_to_global.get(id2):
                        hard_neg_pairs.add((id1, id2))
                        hard_neg_pairs.add((id2, id1))

        return obs_to_global, hard_neg_pairs

    def build_dataset(self) -> Dict[str, Any]:
        """
        Builds and exports candidate pairs and feature datasets.
        """
        profiles = self.candidate_gen.load_and_enrich_evidence()
        candidate_pairs = self.candidate_gen.generate_candidate_pairs()
        obs_to_global, hard_neg_pairs = self.load_ground_truth_mapping()

        rows = []
        pos_count = 0
        neg_count = 0
        hn_count = 0

        for p1_id, p2_id, meta in candidate_pairs:
            p1 = profiles[p1_id]
            p2 = profiles[p2_id]

            # Determine true label from ground truth mapping
            g1 = obs_to_global.get(p1_id)
            g2 = obs_to_global.get(p2_id)
            is_match = 1 if (g1 and g2 and g1 == g2) else 0

            # Determine if this pair is a hard negative
            is_hn = (p1_id, p2_id) in hard_neg_pairs or (p2_id, p1_id) in hard_neg_pairs
            if is_match == 1:
                pos_count += 1
            else:
                neg_count += 1
                if is_hn:
                    hn_count += 1

            # Extract observable features
            feats = self.feature_eng.extract_features_for_pair(p1, p2)

            row = {
                "person_id_a": p1_id,
                "person_id_b": p2_id,
                "case_id_a": p1["case_id"],
                "case_id_b": p2["case_id"],
                "name_a": p1["raw_name"],
                "name_b": p2["raw_name"],
                "alias_a": p1["raw_alias"],
                "alias_b": p2["raw_alias"],
                "blocking_reasons": ";".join(meta["blocking_reasons"]),
                "is_hard_negative": 1 if is_hn else 0,
                "same_entity": is_match,  # Ground-truth label for train/eval
            }
            row.update(feats)
            rows.append(row)

        # Save embedding cache
        self.embedding_mgr.save_cache()

        # Export candidate pairs and feature CSVs
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. candidate_pairs.csv (clean, unlabelled candidate catalog)
        cand_csv_path = self.output_dir / "candidate_pairs.csv"
        cand_fields = [
            "person_id_a", "person_id_b", "case_id_a", "case_id_b",
            "name_a", "name_b", "alias_a", "alias_b", "blocking_reasons"
        ]
        with open(cand_csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cand_fields)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r[k] for k in cand_fields})

        # 2. pair_features.csv (features + evaluation labels)
        feat_csv_path = self.output_dir / "pair_features.csv"
        all_fields = list(rows[0].keys()) if rows else []
        with open(feat_csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

        summary = {
            "total_candidate_pairs": len(rows),
            "positive_pairs": pos_count,
            "negative_pairs": neg_count,
            "hard_negative_pairs": hn_count,
            "feature_names": [k for k in all_fields if k not in cand_fields and k not in ["is_hard_negative", "same_entity"]],
            "num_features": len([k for k in all_fields if k not in cand_fields and k not in ["is_hard_negative", "same_entity"]]),
            "rows": rows
        }

        print("\n" + "="*50)
        print("Candidate Pair Dataset Built Successfully")
        print("="*50)
        print(f"Total Candidate Pairs: {len(rows)}")
        print(f"Positive Pairs (Same Entity): {pos_count}")
        print(f"Negative Pairs (Different Entity): {neg_count}")
        print(f"Hard Negative Pairs: {hn_count}")
        print(f"Pairwise Features Count: {summary['num_features']}")
        print("="*50 + "\n")

        return summary
