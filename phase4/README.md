# Phase 4 — GraphSAGE / Graph Embedding + Link Prediction

The `phase4` module implements a native PyTorch typed-feature GraphSAGE architecture for **SIH26189: AI-Powered Criminal Network Analysis System**. It learns low-dimensional node embeddings from the Phase 3 Case Knowledge Graph and predicts candidate missing associations (`PERSON ↔ PERSON`) to provide actionable investigative hypothesis leads.

---

## Key Principles & Guardrails

1. **Investigative Hypothesis Framework**:
   Model outputs represent **candidate structural associations**, NOT confirmed facts, legal proofs, or guilt determinations. Terminology strictly follows objective standards:
   - *"predicted association"*
   - *"candidate link"*
   - *"investigative lead"*
   - *"model confidence"*
   - *"evidence-supported candidate"*

2. **Zero Ground-Truth Contamination**:
   Ground truth (`output/ground_truth/`) is strictly prohibited from feature engineering, candidate generation, graph construction, training, and inference. Ground truth is accessed **only** within `evaluate.py` for post-hoc benchmarking. A static and tensor-level audit (`leakage_audit.py`) guarantees zero contamination.

3. **Public Infrastructure & High-Fanout Robustness**:
   Prevents models from learning spurious associations driven by ambient transit hubs (e.g. `LOC_Delhi_NCR`), commercial transit sleeper buses (`VEH_026`), or public lodge Wi-Fi hotspots (`103.21.244.18`). Seven structured negative categories (Types A through G) enforce this safety guarantee.

4. **Strict Entity-Disjoint Evaluation**:
   Generalization is benchmarked on a strictly entity-disjoint split ($P_{train} \cap P_{test} = \emptyset$) to evaluate whether GraphSAGE can identify associations between completely unseen identities.

---

## Architecture Overview

```
Phase 3 Knowledge Graph (Nodes, Edges, Provenance)
               │
               ▼
       [GraphLoader] ────► Adjacency Tensor (Normalized)
               │
       [FeatureExtractor] ─► Typed Observable Feature Matrix (11 Node Types, Centrality, Centrality Ratios)
               │
               ▼
       [CandidateGenerator] ─► Positives + Negatives (Types A–G)
               │
               ▼
         [DataSplitter] ────► Case-Aware Split & Strict Entity-Disjoint Split
               │
               ▼
      [GraphSAGEEncoder] ──► 2-Layer Neighborhood Aggregation (d_in -> 64 -> 32)
               │
               ▼
        [LinkDecoder] ─────► MLP Decoder / Dot-Product / Cosine
               │
               ▼
       [LinkPredictor] ────► node_embeddings.csv, candidate_links.csv, predictions.csv
               │
               ▼
     [Phase4Evaluator] ────► report.md, baseline comparison, hard-negative safety
```

---

## Negative Sampling Categories (Types A through G)

- **Type A (Random Negatives)**: Random unlinked person pairs across arbitrary cases.
- **Type B (Same-Case Hard Negatives)**: Unconnected individuals appearing in the same case dossier.
- **Type C (Cross-Case Hard Negatives)**: Unconnected individuals across different case dossiers with similar roles.
- **Type D (Shared-Location Negatives)**: Individuals whose sole mutual tie is co-occurring at an ambient transit city (`LOC_Delhi_NCR`).
- **Type E (Shared-Commercial-Vehicle Negatives)**: Individuals whose sole mutual tie is passenger travel on high-fanout commercial sleeper bus (`VEH_026`).
- **Type F (Shared-Public-IP Negatives)**: Individuals whose sole mutual tie is logging into public transit Wi-Fi (`103.21.244.18`).
- **Type G (High-Degree Hub Negatives)**: High-degree individuals with zero mutual structural ties.

---

## Deliverables in `output/graphsage/`

- `node_embeddings.csv`: 32-dimensional L2-normalized embeddings for all graph nodes.
- `candidate_links.csv`: Generated candidate pairs with labels and negative categories.
- `predictions.csv`: Model predictions ranked by score with confidence tiers and narrative explanations.
- `train_metrics.json`: Training loss history and convergence trajectory.
- `validation_metrics.json`: Comparative validation metrics across link decoders.
- `test_metrics.json`: Test metrics on Case-Aware and Entity-Disjoint splits.
- `hard_negative_metrics.json`: Dedicated safety metrics on public IP, bus, and location negatives.
- `baseline_metrics.json`: Benchmark comparison against Common Neighbors, Jaccard, and Adamic-Adar.
- `leakage_audit.json`: Static code and tensor audit certification.
- `model/graphsage_model.pt`: Serialized PyTorch model weights and configuration.
- `report.md`: Comprehensive scientific report and prototype limitations.

---

## Running Inspection and Tests

```bash
# Run Phase 4 training, evaluation, and inspection pipeline
python inspect_phase4.py

# Run Phase 4 test suite
python -m unittest discover -s phase4 -p "test_*.py"

# Run leakage audit independently
python -m phase4.leakage_audit

# Run all test suites (Phases 1 through 4)
python -m unittest discover -s synthetic_data_generator/tests -p "test_*.py"
python -m unittest discover -s entity_resolution -p "test_*.py"
python -m unittest discover -s graph_analysis -p "test_*.py"
python -m unittest discover -s phase4 -p "test_*.py"
```
