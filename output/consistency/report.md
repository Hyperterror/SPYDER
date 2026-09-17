# Phase 6B: Statement-Evidence Consistency Verification Benchmark Report

## Executive Summary
- **Evaluation Dataset:** 100 synthetically constructed, grounded investigative statements.
- **Overall Classification Accuracy:** 78.00%
- **Macro F1-Score:** 0.7937
- **Total Evidence Matches Retrieved:** 617
- **Runtime Inference Latency:** 0.65 ms/statement
- **Leakage Audit Status:** PASS (Zero Ground-Truth Contamination)

## Performance by Consistency Class
| Class | Support | Precision | Recall | F1-Score |
| :--- | :--- | :--- | :--- | :--- |
| **SUPPORTED** | 30 | 0.9565 | 0.7333 | 0.8302 |
| **CONTRADICTED** | 30 | 0.8889 | 0.5333 | 0.6667 |
| **UNVERIFIABLE** | 20 | 0.5128 | 1.0000 | 0.6780 |
| **EVIDENCE_CONFLICT** | 20 | 1.0000 | 1.0000 | 1.0000 |
| **Macro Average** | 100 | 0.8396 | 0.8166 | 0.7937 |

## Confusion Matrix
| True \ Predicted | SUPPORTED | CONTRADICTED | UNVERIFIABLE | EVIDENCE_CONFLICT |
| :--- | :--- | :--- | :--- | :--- |
| **SUPPORTED** | 22 | 2 | 6 | 0 |
| **CONTRADICTED** | 1 | 16 | 13 | 0 |
| **UNVERIFIABLE** | 0 | 0 | 20 | 0 |
| **EVIDENCE_CONFLICT** | 0 | 0 | 0 | 20 |

## Safeguards & High-Bar Enforcement Verification
1. **Device Location vs Human Physical Presence:** Successfully prevented false contradictions when device ping disagreed with claimed human location; downgraded to UNVERIFIABLE with explicit caveat.
2. **Public Infrastructure Safeguards:** Shared public IPs (e.g. `103.21.244.18`) and shared buses (`VEH_026`) flagged with caveats and prevented from asserting sole contradictions.
3. **Multi-Case RBAC Isolation:** Strict filtering prevents cross-case dossier contamination.
4. **Observable Provenance:** 100% of matched evidence records link directly to real underlying files (`cdr.csv`, `chat_logs.csv`, `financial_transactions.csv`, `travel_movements.csv`, `device_logs.csv`).
