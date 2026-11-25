# ML & GraphSAGE Validation Report

## 1. Anti-Leakage Architecture
- **Entity Resolution**: Production `entity_resolution/candidate_generation.py` contains zero references to `GROUND_TRUTH_DIR` or `ground_truth.json`; benchmark hard-negative injection occurs solely inside evaluation dataset builder `entity_resolution/pair_generation.py`.
- **GraphSAGE (`phase4/`)**:
  - `GraphLoader.build_masked_graph()` and `build_normalized_adj(excluded_edges=...)` strip all held-out supporting edges (`supporting_edge_keys`) before neighborhood message passing.
  - `FeatureExtractor.extract_node_features(..., recompute_centrality=True)` computes PageRank, degree centrality, and betweenness centrality strictly on the masked training graph instead of the full-graph CSV.
  - `LeakageAuditor.audit_target_edge_leakage()` verifies `0` leaked target edges across both Edge-Disjoint (`23` edges checked, `0` leaked) and Temporal (`19` edges checked, `0` leaked) splits.

## 2. Phase 4 GraphSAGE Multi-Split Metrics (Prototype Synthetic Dataset)
Measured from `python -m phase4.train` (`output/graphsage/test_metrics.json`, `baseline_metrics.json`):

| Split | Samples (Pos/Neg) | ROC-AUC | PR-AUC | F1 | FPR | P@10 | R@20 | MRR | Brier | ECE |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Case-Aware Test** | 935 (19/916) | 0.7167 | 0.0452 | 0.0612 | 0.0830 | 0.0000 | 0.0000 | 0.0370 | 0.0781 | 0.1897 |
| **Strict Entity-Disjoint** | 142 (1/141) | 0.8369 | 0.0417 | 0.0000 | 0.0496 | 0.0000 | 0.0000 | 0.0417 | 0.0615 | 0.1862 |
| **Edge-Disjoint (Masked)** | 577 (8/569) | 0.6522 | 0.0803 | 0.1091 | 0.0773 | 0.1000 | 0.2500 | 0.3333 | 0.0713 | 0.1893 |
| **Temporal Holdout (Masked)** | 694 (10/684) | 0.5640 | 0.0378 | 0.0449 | 0.1126 | 0.1000 | 0.1000 | 0.2000 | 0.0832 | 0.1946 |

### Baseline Comparison & Honest Assessment
On unmasked Case-Aware pairs, **Adamic-Adar** achieves ROC-AUC **0.9949** and PR-AUC **0.8471** (`P@10 = 1.0`, `MRR = 1.0`) because shared low-degree entity bridges remain directly observable. Under **Edge-Disjoint Masked** evaluation, Adamic-Adar drops to ROC-AUC **0.8418** / PR-AUC **0.1569** / MRR **0.5000** (`Temporal Masked`: ROC-AUC **0.9113** / PR-AUC **0.0923** / MRR **0.0909**). Adding calibrated scale+bias parameters to `CosineDecoder`/`DotProductDecoder` reduced GraphSAGE false-positive rate from `1.000` to `0.0773–0.0830` and Brier score from `0.4125` to `0.0713–0.0781`, while showing honestly that topological heuristics (`adamic_adar`) remain stronger rankers on this small 10-case synthetic graph when local bridges are sparse.

## 3. Entity Resolution Validation (`output/entity_resolution/strict_evaluation_results.json`)
- **Strict Entity-Disjoint (47 pairs, 14 pos / 33 neg)**: Precision `1.0000`, Recall `1.0000`, F1 `1.0000`, FMR `0.0000`, Brier `0.0027`, ECE `0.0522`.
- **Multi-Seed Stability (5 seeds: 42, 101, 202, 303, 404)**: Mean F1 `1.0000` (`std = 0.0000`), Mean ROC-AUC `1.0000`, Mean FMR `0.0000`.
- **Expanded Noisy Stress Benchmark (1,200 pairs with OCR typos, dropped phones, shared public IPs)**: ROC-AUC `0.9150`, Precision `1.0000`, Recall `0.4175`, F1 `0.5891`, FMR `0.0000`, Brier `0.1763`, ECE `0.1661`.
