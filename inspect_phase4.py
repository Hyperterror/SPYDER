"""
Inspection and Execution Script for Phase 4:
GraphSAGE / Graph Embedding + Link Prediction.
Executes the full pipeline: graph loading, feature extraction, candidate generation,
splitting, decoder comparison, training, evaluation, baseline comparison, explanation,
leakage audit, and exports deliverables to output/graphsage/.
"""

import sys
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase4.train import GraphSAGETrainer
from phase4.evaluate import Phase4Evaluator
from phase4.predict import LinkPredictor
from phase4.leakage_audit import LeakageAuditor
from phase4.config import EMBED_DIM

def run_phase4_pipeline():
    print("\n" + "=" * 80)
    print(" " * 15 + "PHASE 4: GRAPHSAGE EMBEDDING + LINK PREDICTION")
    print("=" * 80)

    # 1. Initialize Trainer, Graph, Features, and Candidates
    print("\n[1/6] Loading Phase 3 Graph & Extracting Typed Observable Features...")
    trainer = GraphSAGETrainer(random_seed=42)
    print(f" -> Total Graph Nodes: {trainer.multi_graph.number_of_nodes():,}")
    print(f" -> Total Graph Edges: {trainer.multi_graph.number_of_edges():,}")
    print(f" -> Node Feature Dimension: {trainer.x.shape[1]} (Typed Observable Features)")
    print(f" -> Total Generated Candidates: {len(trainer.candidates):,}")

    # Category breakdown
    cat_counts = {}
    for c in trainer.candidates:
        cat_counts[c["category"]] = cat_counts.get(c["category"], 0) + 1
    print("\nCandidate Link Distribution:")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"    - {cat:<32}: {cnt:>5}")

    # 2. Splits Audit & Disclosure
    print("\n[2/6] Auditing Data Splits & Entity Disjointness...")
    cs = trainer.case_split
    es = trainer.entity_split

    print(f"\nA. Case-Aware Split:")
    print(f"    - Train Cases: {', '.join(cs['train_cases'])} ({cs['train_count']} pairs)")
    print(f"    - Val Cases  : {', '.join(cs['val_cases'])} ({cs['val_count']} pairs)")
    print(f"    - Test Cases : {', '.join(cs['test_cases'])} ({cs['test_count']} pairs)")
    print(f"    - Train Entities: {cs['train_entities_count']} | Test Entities: {cs['test_entities_count']}")
    print(f"    - Entity Overlap: {cs['entity_overlap_count']} entities")
    print(f"    - Disclosure    : {cs['leakage_disclosure']}")

    print(f"\nB. Strict Entity-Disjoint Split:")
    print(f"    - Train Pairs: {es['train_count']} | Val Pairs: {es['val_count']} | Test Pairs: {es['test_count']}")
    print(f"    - Train Entities: {es['train_entities_count']} | Test Entities: {es['test_entities_count']}")
    print(f"    - Entity Overlap: {es['entity_overlap_count']} entities (Strictly Disjoint: {es['is_strictly_entity_disjoint']})")
    print(f"    - Disclosure    : {es['leakage_disclosure']}")

    # 3. Decoder Comparison & Model Training
    print("\n[3/6] Comparing Link Decoders & Training GraphSAGE Model...")
    dec_results = trainer.train_decoder_comparison()
    print("Decoder Validation Comparison:")
    for d_name in ["mlp", "dot", "cosine"]:
        print(f"    - {d_name.upper():<8}: Val ROC-AUC = {dec_results[d_name]['val_roc_auc']:.4f}, Val PR-AUC = {dec_results[d_name]['val_pr_auc']:.4f}")
    selected_decoder = dec_results["selected_decoder"]
    print(f" -> Selected Decoder: {selected_decoder.upper()}")

    model, train_metrics = trainer.train_final_model(decoder_type=selected_decoder)
    print(f" -> Final Training Loss: {train_metrics['final_train_loss']:.5f} (Epochs: {train_metrics['num_epochs']})")

    # 4. Evaluation and Baseline Comparison
    print("\n[4/6] Running Holdout Evaluation & Baseline Benchmarking...")
    evaluator = Phase4Evaluator(
        model=model,
        x=trainer.x,
        norm_adj=trainer.norm_adj,
        node_to_idx=trainer.loader.node_to_idx,
        multi_graph=trainer.multi_graph
    )
    eval_results = evaluator.run_full_evaluation(cs, es, trainer.hard_negatives, dec_results)

    c_test = eval_results["case_test"]
    e_test = eval_results["entity_test"]
    b_test = eval_results["baselines"]
    h_test = eval_results["hard_negatives"]

    print("\n" + "=" * 80)
    print(" " * 25 + "EVALUATION SUMMARY")
    print("=" * 80)
    print(f"{'Method / Split':<30} {'ROC-AUC':<10} {'PR-AUC':<10} {'F1':<10} {'FPR':<10}")
    print("-" * 80)
    print(f"{'GraphSAGE (Case-Aware)':<30} {c_test['roc_auc']:<10.4f} {c_test['pr_auc']:<10.4f} {c_test['f1_score']:<10.4f} {c_test['false_positive_rate']:<10.4f}")
    print(f"{'GraphSAGE (Entity-Disjoint)':<30} {e_test['roc_auc']:<10.4f} {e_test['pr_auc']:<10.4f} {e_test['f1_score']:<10.4f} {e_test['false_positive_rate']:<10.4f}")
    for b_name, b_m in b_test.items():
        print(f"{b_name.replace('_', ' ').title() + ' (Baseline)':<30} {b_m['roc_auc']:<10.4f} {b_m['pr_auc']:<10.4f} {b_m['f1']:<10.4f} {'-':<10}")

    print("\nHard Negative Robustness (Public Infrastructure & Ambient Hubs):")
    for cat in ["NEG_F_SHARED_PUBLIC_IP", "NEG_E_SHARED_COMMERCIAL_VEHICLE", "NEG_D_SHARED_LOCATION", "NEG_G_HIGH_DEGREE_HUB"]:
        if cat in h_test:
            info = h_test[cat]
            print(f"    - {cat:<32}: Count = {info['count']:<4} | FPR = {info['false_positive_rate']:.4f} | Mean Score = {info['mean_prediction_score']:.4f} | Max = {info['max_prediction_score']:.4f}")

    summary_h = h_test["summary"]
    print(f"\n -> Public Infrastructure False Positive Rate : {summary_h['public_infrastructure_false_positive_rate']:.4f}")
    print(f" -> Hub Negative False Positive Rate          : {summary_h['hub_negative_false_positive_rate']:.4f}")

    # 5. Link Prediction Inference & Explanation Export
    print("\n[5/6] Generating Link Predictions, Explanations & Node Embeddings...")
    predictor = LinkPredictor(
        model=model,
        x=trainer.x,
        norm_adj=trainer.norm_adj,
        node_to_idx=trainer.loader.node_to_idx,
        idx_to_node=trainer.loader.idx_to_node,
        multi_graph=trainer.multi_graph
    )
    predictor.export_node_embeddings()
    predictions = predictor.predict_and_explain_candidates(trainer.candidates)

    print(f" -> Exported node_embeddings.csv ({trainer.x.shape[0]} nodes, {EMBED_DIM} dimensions)")
    print(f" -> Exported candidate_links.csv and predictions.csv ({len(predictions)} pairs)")

    print("\nTop 3 Predicted Candidate Associations (High-Priority Leads):")
    for idx, p in enumerate(predictions[:3], 1):
        print(f"\n--- Lead #{idx} [{p['confidence_tier']}] (Score: {p['prediction_score']:.4f}) ---")
        print(f"Pair: {p['source_node']} <-> {p['target_node']} (Cross-Case: {p['is_cross_case']})")
        print(f"Explanation:\n{p['explanation']}")

    # 6. Leakage Audit
    print("\n[6/6] Executing Static & Tensor-Level Ground-Truth Leakage Audit...")
    auditor = LeakageAuditor()
    audit_report = auditor.run_full_audit(trainer.feature_names)
    print(f" -> Leakage Audit Status: {audit_report['certification']}")
    print(f" -> Code Files Scanned  : {audit_report['code_audit']['total_files_scanned']} (Violations: {audit_report['code_audit']['total_violations']})")
    print(f" -> Feature Names Audited: {audit_report['feature_audit']['feature_count']} (Violations: {len(audit_report['feature_audit']['feature_violations'])})")
    print(" -> Detailed audit written to output/graphsage/leakage_audit.json")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_phase4_pipeline()
