# Phase 3 — Global Case Knowledge Graph & Network Analysis

The `graph_analysis` module constructs an evidence-backed, multi-case Knowledge Graph and network analysis pipeline for SIH26189 (*AI-Powered Criminal Network Analysis System*).

---

## Key Principles & Architectural Safeguards

1. **Zero Ground-Truth Contamination in Graph Construction**:
   The Knowledge Graph, node attributes, edges, centrality metrics, community partitions, and path explanations are generated **purely from observable evidence CSVs** (`synthetic_data_generator/output/evidence_dataset/`) and **Phase 2 entity resolution predictions** (`output/entity_resolution/predictions.csv`). Latent ground truth is accessed strictly inside `evaluation.py` for post-hoc validation.

2. **Resolved Entity Clustering Safety (Safeguard 1)**:
   - High-confidence ER pairs ($p \ge 0.90$) form provisional clusters (`PROV_RES_ENT_xxx`).
   - Clusters are treated as **investigative hypotheses**, never as immutable factual identities.
   - For every cluster, underlying pairwise links, probabilities, cluster diameter, and cohesion scores are explicitly preserved.
   - Long transitive chains (diameter > 2) and clusters with low internal affinity are flagged for manual investigator review.
   - If an evaluated pair within a proposed cluster has low confidence ($p < 0.50$) or conflicting evidence, the pipeline rejects silent merging.

3. **Context-Aware Identifier Reliability (Safeguard 2)**:
   - Avoids naive hardcoding of identifier reliability.
   - Dynamically evaluates identifier confidence based on:
     - Recurrence and frequency across events
     - Temporal consistency and duration of usage
     - Multi-person sharing/fan-out (shared fleet vehicles or ambiguous accounts are penalized)
     - Known public infrastructure (public lodge Wi-Fi IPs, IRCTC ticketing portal, public helplines receive heavy penalties)
     - Multi-modal corroboration across independent evidence modalities (CDR, device telemetry, finance, transit).

4. **Objective, Non-Prejudicial Terminology**:
   Avoids labels such as "mastermind", "criminal", "syndicate", or "guilty". Uses neutral analytical classifications:
   - *"High-connectivity entity"*
   - *"Cross-case bridge entity"*
   - *"High-priority investigative lead"*
   - *"Investigative cluster / Connected group"*

---

## Knowledge Graph Schema

### 10 Observable Node Types
1. `PERSON`: Observational persons (`CASE_xxx_PER_yy`) and provisional resolved entities (`PROV_RES_ENT_xxx`).
2. `VICTIM`: Observational victim records (`CASE_xxx_VIC_yy`).
3. `CASE`: Police case dossiers (`CASE_001` .. `CASE_010`).
4. `PHONE`: Observed telephone numbers.
5. `DEVICE`: Forensic device hardware IDs and IMEIs.
6. `VEHICLE`: Vehicle registration numbers.
7. `BANK_ACCOUNT`: Bank account identifiers.
8. `SOCIAL_ACCOUNT`: Social media platform profiles.
9. `LOCATION`: Geographic waypoints, transit terminals, and cellular towers.
10. `EVIDENCE`: Seized physical and digital evidence records (`EVID_xxx`).

### Observable Edge Types & Provenance
- `PERSON --APPEARS_IN--> CASE`
- `VICTIM --APPEARS_IN--> CASE`
- `PERSON --USED_PHONE--> PHONE`
- `PERSON --USED_DEVICE--> DEVICE`
- `PERSON --USED_VEHICLE--> VEHICLE`
- `PERSON --TRAVELLED_TO--> LOCATION`
- `PERSON --HAS_SOCIAL_ACCOUNT--> SOCIAL_ACCOUNT`
- `PHONE --CALLED--> PHONE` (CDR)
- `PHONE --MESSAGED--> PHONE` (Chat logs)
- `BANK_ACCOUNT --TRANSFERRED_MONEY--> BANK_ACCOUNT` (Financial transactions)
- `CASE --ASSOCIATED_WITH_EVIDENCE--> EVIDENCE`
- `PERSON --OBSERVES_ENTITY--> PROV_RES_ENT` (Provisional ER cluster link)

Every edge strictly preserves:
`source_table`, `source_id`, `case_id`, `timestamp`, `evidence_type`, `confidence`, and `notes`.

---

## Analytics Pipeline

```
Evidence Tables + ER Predictions
               │
               ▼
       [GraphBuilder] ──────► MultiDiGraph (Full Provenance)
               │
               ▼
      [Projected Graph]
         ├── [TemporalEngine]     (Time-window filtering & timelines)
         ├── [CentralityAnalyzer] (Degree, Betweenness, PageRank)
         ├── [CommunityAnalyzer]  (Modularity / Louvain clustering)
         ├── [CrossCaseDetector]  (Multi-hop path search & scoring)
         └── [Explanations]       (Evidence-backed narrative generation)
               │
               ▼
        [GraphExporter] ────► output/graph_analysis/
               │
               ▼
     [KnowledgeGraphEvaluator] ─► evaluation_report.md (Ground-Truth Benchmarking)
```

---

## Deliverables in `output/graph_analysis/`

- `nodes.csv`: All graph nodes with attributes, case memberships, and provisional entity links.
- `edges.csv`: All evidence-backed relationships with complete provenance.
- `case_graph.json`: Global multi-directed knowledge graph in Node-Link JSON format.
- `cross_case_connections.csv`: Discovered cross-case leads ranked by priority score.
- `node_metrics.csv`: Degree, betweenness, PageRank, and analytical roles per node.
- `communities.csv`: Investigative clusters profiled by composition and evidence types.
- `graph_summary.json`: Structural graph metrics and node/edge type tallies.
- `evaluation_report.md`: Internal evaluation benchmarking against ground truth.

---

## Running Inspection and Tests

```bash
# Run complete inspection pipeline
python inspect_graph_analysis.py

# Run Phase 3 test suite
python -m unittest discover -s graph_analysis -p "test_*.py"

# Run all test suites (Phases 1, 2, and 3)
python -m unittest discover -s synthetic_data_generator/tests -p "test_*.py"
python -m unittest discover -s entity_resolution -p "test_*.py"
python -m unittest discover -s graph_analysis -p "test_*.py"
```
