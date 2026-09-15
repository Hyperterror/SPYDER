

# Phase 2: Entity Resolution Pipeline (SIH26189)

**AI-Powered Criminal Network Analysis System**
*Component: Cross-Case Identity Resolution from Fragmented Observable Evidence*

---

> [!IMPORTANT]
> **Legal & Data Disclaimers:**
> - The current dataset is synthetic and intended for prototype development and evaluation. It does not represent real NCRB/police data.
> - Model predictions are investigative leads and not legal determinations of identity, guilt, or criminal involvement.

---

## 1. Objective

The objective of Phase 2 is to build an explainable, multi-modal Entity Resolution system that determines whether two observational person records from different case files (e.g. `CASE_001_PER_01` and `CASE_003_PER_01`) represent the same underlying real-world entity.

The pipeline adheres to strict non-leakage constraints:
- **Zero Ground Truth at Inference:** `GLOBAL_ENTITY_ID`, `true_role`, and `syndicate_id` are never input features.
- **Case-Scoped Observational IDs:** `person_id` values are case-scoped observational identifiers rather than global keys.
- **Human-Reviewed Investigative Leads:** Entity Resolution outputs match probabilities, confidence tiers, and supporting evidence rather than automatic, permanent merges.

---

## 2. Pipeline Architecture

```
RAW PERSON OBSERVATIONS (persons.csv)
        ↓
Observable Evidence Enrichment (device_logs, vehicles, CDR, social, movements)
        ↓
Candidate Generation & Blocking (phone, IMEI, vehicle, name/alias similarity)
        ↓
Pairwise Multi-Modal Feature Extraction (28 features)
        ↓
Sentence Transformer Embeddings (all-MiniLM-L6-v2)
        ↓
XGBoost Pairwise Classifier (scale_pos_weight balanced)
        ↓
Calibrated Match Probability [0.0, 1.0]
        ↓
Confidence Tiers (HIGH >= 0.90, REVIEW REQUIRED 0.70-0.89, LOW < 0.70)
        ↓
Explainable Evidence-Based Reasons (Supporting & Conflicting)
        ↓
Evaluation & Hard-Negative Stress Testing
```

---

## 3. Observable Features (28 Features)

| Feature Category | Extracted Features |
| :--- | :--- |
| **Name Similarity** | `name_exact_match`, `name_levenshtein_sim`, `name_jaro_winkler_sim`, `name_token_jaccard`, `name_initial_match`, `name_length_diff` |
| **Alias Similarity** | `alias_both_present`, `alias_exact_match`, `alias_levenshtein_sim`, `alias_token_jaccard`, `name_alias_cross_match` |
| **Telecommunications** | `phone_shared_count`, `phone_exact_match`, `phone_both_present` |
| **Digital Identity** | `device_id_match`, `imei_match`, `imei_shared_count`, `shared_ip_count`, `shared_ip_is_public_infra`, `social_handle_match`, `email_match` |
| **Vehicular Logistics** | `vehicle_reg_match`, `shared_vehicle_count` |
| **Spatial & Demographic** | `shared_location_count`, `address_token_sim`, `same_age_group` |
| **Communications** | `shared_contacts_count` |
| **Contextual Text** | `context_embedding_cosine_sim` (Sentence Transformer cosine similarity) |

---

## 4. Case-Aware Train / Validation / Test Strategy

To prevent data leakage caused by entities appearing across multiple cases, candidate pairs are partitioned across case boundaries:
- **Train Set (60 pairs):** `CASE_001`, `CASE_003`, `CASE_002`, `CASE_005`, `CASE_004`
- **Validation Set (66 pairs):** `CASE_007`, `CASE_008`
- **Test Set (131 pairs):** `CASE_009`, `CASE_006`, `CASE_010`
- **Hard-Negative Evaluation Subset (9 pairs):** Adversarial pairs sharing names/aliases or public infrastructure.

---

## 5. Model Performance vs Baselines (Test Set)

| Method | Precision | Recall | F1 Score | False Merge Rate (FMR) | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline 1: Exact Identifier Match** | 0.1667 | 1.0000 | 0.2857 | 0.4132 | N/A |
| **Baseline 2: Name Similarity (>=0.85)** | 0.3750 | 0.6000 | 0.4615 | 0.0826 | N/A |
| **Sentence Transformer + XGBoost** | **1.0000** | **1.0000** | **1.0000** | **0.0000** | **1.0000** |

*Analysis of Baselines:*
- Baseline 1 achieves 100% recall but suffers a disastrous 41.3% False Merge Rate because shared burner phones and public cyber kiosk terminals cause innocent people to be merged.
- Baseline 2 suffers an 8.3% False Merge Rate on hard-negative lookalike names (e.g. Ramesh Chand vs Ramesh Chand) and misses entities using aliases/nicknames.
- The XGBoost + Sentence Transformer model learns to distinguish individual identity by synthesizing telecom, device, and contextual semantic similarity, achieving 0.0000 False Merge Rate.

---

## 6. Hard-Negative Evaluation Metrics

Evaluated specifically on lookalike names, aliases, and shared public IPs:
- **Hard-Negative Total Samples:** 9 pairs
- **False Merges on Hard Negatives:** **0** (False Merge Rate: 0.0000)
- Lookalike pairs (such as Ramesh Chand recruiter vs. Ramesh Chand tea vendor, or Vikramaditya alias Vicky vs. Vikram Rathore alias Vicky) are correctly recognized as distinct individuals.

---

## 7. How to Run

### Generate Pairs, Train Model & Evaluate:
```bash
python -m entity_resolution.train
```

### Run 15 Automated Validation Tests:
```bash
python -m unittest entity_resolution/test_entity_resolution.py -v
```

### Run Demonstration & Inspection Script:
```bash
python inspect_entity_resolution.py
```

---

## 8. Limitations & Boundary for Next Phases

1. **Synthetic Data Boundaries:** While calibrated with phonetic and alias noise, real-world data contains OCR errors, transcription noise, and unverified informant reports that will require fuzzy phonetic encoders (e.g. Double Metaphone / Indic Soundex).
2. **Phase Boundary:** This phase strictly produces candidate matches with probabilities, confidence tiers, and evidence explanations. It does not automatically merge entities or construct a knowledge graph. Permanent entity merges and cross-case network analysis will be handled in subsequent phases under human review.
