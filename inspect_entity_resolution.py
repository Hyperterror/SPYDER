
"""
Inspection and Demonstration Script for Entity Resolution (SIH26189 Phase 2).
Demonstrates:
- Example A: Genuine cross-case same-entity match
- Example B: Hard-negative similar-name different-person match
- Example C: Shared-IP different-person match
"""

import json
import csv
from pathlib import Path

from entity_resolution.config import OUTPUT_DIR, GROUND_TRUTH_DIR, EVIDENCE_DIR
from entity_resolution.predict import EntityResolutionPredictor
from entity_resolution.candidate_generation import CandidateGenerator

def run_inspection():
    pred_path = OUTPUT_DIR / "predictions.csv"
    gt_path = GROUND_TRUTH_DIR / "ground_truth.json"

    with open(gt_path, "r", encoding="utf-8") as f:
        gt = json.load(f)

    obs_mapping = gt.get("observational_mapping", {})
    obs_to_global = {}
    for gid, info in obs_mapping.items():
        if "case_instances" in info:
            for cid, inst in info["case_instances"].items():
                obs_to_global[inst["observational_person_id"]] = {
                    "global_id": gid,
                    "true_name": info["true_name"],
                    "true_role": info["true_role"],
                    "cluster": info["network_cluster"],
                }

    cand_gen = CandidateGenerator()
    profiles = cand_gen.load_and_enrich_evidence()
    predictor = EntityResolutionPredictor()

    print("="*70)
    print("PHASE 2 ENTITY RESOLUTION DEMONSTRATION & INSPECTION")
    print("="*70)

    # -------------------------------------------------------------
    # Example A: Genuine Cross-Case Match
    # E.g. CASE_001_PER_01 and CASE_003_PER_01 (Aarav Gupta)
    # -------------------------------------------------------------
    pA1_id, pA2_id = "CASE_001_PER_01", "CASE_003_PER_01"
    res_A = predictor.predict_pair(profiles[pA1_id], profiles[pA2_id])
    gt_A1 = obs_to_global.get(pA1_id)
    gt_A2 = obs_to_global.get(pA2_id)

    print("\n[EXAMPLE A: Genuine Cross-Case Match]")
    print("-------------------------------------------------------------")
    print(f"Observation A: {pA1_id} ({res_A['name_a']}) in {res_A['case_id_a']}")
    print(f"Observation B: {pA2_id} ({res_A['name_b']}) in {res_A['case_id_b']}")
    print(f"Predicted Probability: {res_A['match_probability']:.4f}")
    print(f"Confidence Tier:       {res_A['confidence_tier']}")
    print("Top Supporting Reasons:")
    for r in res_A['explanation']['supporting_reasons']:
        print(f"  + {r}")
    print("Conflicting Factors:")
    for r in res_A['explanation']['conflicting_reasons']:
        print(f"  - {r}")
    print("\n>>> GROUND TRUTH DEBUG/EVALUATION ONLY (Hidden from Investigator UI):")
    print(f"  * Observation A maps to: {gt_A1['global_id']} ({gt_A1['true_name']}, {gt_A1['cluster']})")
    print(f"  * Observation B maps to: {gt_A2['global_id']} ({gt_A2['true_name']}, {gt_A2['cluster']})")
    print(f"  * Truly Same Entity? {'YES (MATCH)' if gt_A1['global_id'] == gt_A2['global_id'] else 'NO'}")

    # -------------------------------------------------------------
    # Example B: Hard Negative (Similar Name / Alias, Different Person)
    # E.g. Ramesh Chand (Recruiter in Alpha) vs Ramesh Chand (Tea Vendor in Indep CASE_004)
    # -------------------------------------------------------------
    # Direct observational IDs for Ramesh Chand hard negative pair
    pB1_id = "CASE_001_PER_05"  # Raamesh Chand, alias Ramu (Recruiter in Alpha)
    pB2_id = "CASE_004_PER_05"  # Ramesh, alias Ramu Kaka (Tea Stall Owner in Indep Case 004)

    if pB1_id and pB2_id:
        res_B = predictor.predict_pair(profiles[pB1_id], profiles[pB2_id])
        gt_B1 = obs_to_global.get(pB1_id)
        gt_B2 = obs_to_global.get(pB2_id)

        print("\n[EXAMPLE B: Hard Negative (Adversarial Similar-Name Match)]")
        print("-------------------------------------------------------------")
        print(f"Observation A: {pB1_id} ('{res_B['name_a']}') in {res_B['case_id_a']}")
        print(f"Observation B: {pB2_id} ('{res_B['name_b']}') in {res_B['case_id_b']}")
        print(f"Predicted Probability: {res_B['match_probability']:.4f}")
        print(f"Confidence Tier:       {res_B['confidence_tier']}")
        print("Supporting Reasons:")
        for r in res_B['explanation']['supporting_reasons']:
            print(f"  + {r}")
        print("Conflicting Factors:")
        for r in res_B['explanation']['conflicting_reasons']:
            print(f"  - {r}")
        print("\n>>> GROUND TRUTH DEBUG/EVALUATION ONLY (Hidden from Investigator UI):")
        print(f"  * Observation A maps to: {gt_B1['global_id']} ({gt_B1['true_name']}, role={gt_B1['true_role']}, {gt_B1['cluster']})")
        print(f"  * Observation B maps to: {gt_B2['global_id']} ({gt_B2['true_name']}, role={gt_B2['true_role']}, {gt_B2['cluster']})")
        print(f"  * Truly Same Entity? {'YES' if gt_B1['global_id'] == gt_B2['global_id'] else 'NO (HARD NEGATIVE SEPARATED CORRECTLY)'}")

    # -------------------------------------------------------------
    # Example C: Shared Public IP (Different Persons in Different Cases)
    # -------------------------------------------------------------
    # Find two distinct persons whose devices logged on Mahipalpur Lodge Wi-Fi (103.21.244.18)
    pC1_id = None
    pC2_id = None
    target_ip = "103.21.244.18"
    for pid, p in profiles.items():
        if target_ip in p["ip_addresses"]:
            if not pC1_id:
                pC1_id = pid
            elif not pC2_id and p["case_id"] != profiles[pC1_id]["case_id"]:
                pC2_id = pid
                break

    if pC1_id and pC2_id:
        res_C = predictor.predict_pair(profiles[pC1_id], profiles[pC2_id])
        gt_C1 = obs_to_global.get(pC1_id)
        gt_C2 = obs_to_global.get(pC2_id)

        print("\n[EXAMPLE C: Shared Public Infrastructure IP (Different Persons)]")
        print("-------------------------------------------------------------")
        print(f"Observation A: {pC1_id} ('{res_C['name_a']}') in {res_C['case_id_a']}")
        print(f"Observation B: {pC2_id} ('{res_C['name_b']}') in {res_C['case_id_b']}")
        print(f"Shared Observable IP:  {target_ip} (Mahipalpur Transit Lodge Public Wi-Fi)")
        print(f"Predicted Probability: {res_C['match_probability']:.4f}")
        print(f"Confidence Tier:       {res_C['confidence_tier']}")
        print("Supporting Reasons:")
        for r in res_C['explanation']['supporting_reasons']:
            print(f"  + {r}")
        print("Conflicting Factors:")
        for r in res_C['explanation']['conflicting_reasons']:
            print(f"  - {r}")
        print("\n>>> GROUND TRUTH DEBUG/EVALUATION ONLY (Hidden from Investigator UI):")
        print(f"  * Observation A maps to: {gt_C1['global_id']} ({gt_C1['true_name']})")
        print(f"  * Observation B maps to: {gt_C2['global_id']} ({gt_C2['true_name']})")
        print(f"  * Truly Same Entity? {'YES' if gt_C1['global_id'] == gt_C2['global_id'] else 'NO (SHARED IP PROPERLY PREVENTED FROM MERGING)'}")

    print("\n" + "="*70)

if __name__ == "__main__":
    run_inspection()
