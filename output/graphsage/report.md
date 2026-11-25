# Phase 4 GraphSAGE & Link Prediction — Implementation & Evaluation Report

> [!IMPORTANT]
> **Investigative Hypothesis Disclaimer**:
> Model predictions represent **candidate structural associations and investigative leads**, NOT factual identities, criminal determinations, or legal proof of guilt. All inferences are hypotheses derived from graph topological patterns to assist human analysts.

> [!NOTE]
> **Prototype Validation Context**:
> The investigation dataset currently comprises 10 cases, 100 persons, and 2 active syndicates. Metrics below reflect strict anti-leakage holdout evaluations on this synthetic prototype; masked-graph splits strip all held-out target edges and recompute centralities strictly on the training subgraph.

---

## 1. GraphSAGE Architecture & Decoder Selection

- **Encoder**: 2-Layer GraphSAGE with typed node features ($d_{in} = 34$, hidden $d_h = 64$, embedding $d_z = 32$) with LayerNorm, ReLU, and Dropout ($0.2$).
- **Decoder Comparison (Validation Set)**:
  - MLP Decoder: ROC-AUC = `0.8033`, PR-AUC = `0.0582`
  - Dot-Product: ROC-AUC = `0.9617`, PR-AUC = `0.2083`
  - Cosine: ROC-AUC = `0.8416`, PR-AUC = `0.2305`
  - **Selected Decoder**: **`COSINE`**

---

## 2. Multi-Split Holdout Performance (with Ranking & Calibration)

| Split | Samples (Pos/Neg) | ROC-AUC | PR-AUC | F1 | P@10 | R@20 | MRR | Brier | ECE |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Case-Aware Test** | `935` (19/916) | `0.7167` | `0.0452` | `0.0612` | `0.0000` | `0.0000` | `0.0370` | `0.0781` | `0.1897` |
| **Strict Entity-Disjoint** | `142` (1/141) | `0.8369` | `0.0417` | `0.0000` | `0.0000` | `0.0000` | `0.0417` | `0.0615` | `0.1862` |
| **Edge-Disjoint (Masked)** | `577` (8/569) | `0.6522` | `0.0803` | `0.1091` | `0.1000` | `0.2500` | `0.3333` | `0.0713` | `0.1893` |
| **Temporal Holdout (Masked)** | `694` (10/684) | `0.5640` | `0.0378` | `0.0449` | `0.1000` | `0.1000` | `0.2000` | `0.0832` | `0.1946` |

---

## 3. Comparison with Topological Baselines

Comparative evaluation on the Case-Aware Test Set (plus masked-graph Adamic-Adar benchmarks):

| Method | ROC-AUC | PR-AUC | Precision | Recall | F1 Score | P@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **GraphSAGE (Case-Aware)** | **`0.7167`** | **`0.0452`** | **`0.0380`** | **`0.1579`** | **`0.0612`** | `0.0000` | `0.0370` |
| Common Neighbors | `0.8422` | `0.0763` | `0.0293` | `1.0000` | `0.0570` | `0.2000` | `0.5000` |
| Jaccard Coefficient | `0.9127` | `0.4322` | `0.0335` | `1.0000` | `0.0648` | `0.6000` | `1.0000` |
| Adamic-Adar (Case-Aware) | `0.9949` | `0.8471` | `0.0567` | `1.0000` | `0.1073` | `1.0000` | `1.0000` |
| Adamic-Adar (Edge-Disjoint Masked) | `0.8418` | `0.1569` | `0.0255` | `0.8750` | `0.0495` | `0.1000` | `0.5000` |
| Adamic-Adar (Temporal Masked) | `0.9113` | `0.0923` | `0.0207` | `1.0000` | `0.0405` | `0.0000` | `0.0909` |
| Preferential Attachment | `0.4596` | `0.0195` | `0.0222` | `0.3684` | `0.0418` | `0.0000` | `0.0116` |

> **Baseline Honesty Note**: On unmasked local neighborhoods where direct 2-hop bridges remain visible, Adamic-Adar naturally achieves high AUC because it directly rewards low-degree shared entities. Once held-out supporting edges are masked (`Edge-Disjoint` and `Temporal`), both GraphSAGE and topological heuristics drop realistically because hidden direct bridges are removed, isolating genuine 2+ hop structural generalization.

---

## 4. Public & Shared Infrastructure Robustness (Hard Negatives)

| Category | Count | False Positives | False Positive Rate | Mean Score | Max Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Shared Public Wi-Fi / IP** | `105` | `8` | **`0.0762`** | `0.2030` | `0.7558` |
| **Commercial Transit Bus (`VEH_026`)** | `16` | `1` | **`0.0625`** | `0.1910` | `0.5083` |
| **Generic Transit City (`Delhi NCR`, etc.)** | `1975` | `143` | **`0.0724`** | `0.1934` | `0.7578` |
| **High-Degree Hub Negatives** | `33` | `6` | **`0.1818`** | `0.2859` | `0.6881` |

- **Public Infrastructure False Positive Rate**: **`0.0725`**
- **Hub Negative False Positive Rate**: **`0.1818`**
