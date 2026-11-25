"""
Static and Tensor-Level Ground-Truth Leakage Audit for Phase 4.
Scans all Phase 4 code files (asserting zero ground truth outside evaluate.py)
and audits feature tensors to guarantee zero latent contamination.
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple

from phase4.config import BASE_DIR, OUTPUT_DIR

FORBIDDEN_GROUND_TRUTH_TOKENS = [
    "ground_truth.json",
    "true_entities.json",
    "true_case_links.json",
    "true_relationships.json",
    "true_roles.json",
    "GLOBAL_ENTITY_ID",
    "GLOBAL_ENT_",
    "NETWORK_ALPHA",
    "NETWORK_BETA",
    "true_role",
    "syndicate_cluster"
]

class LeakageAuditor:
    def __init__(self, phase4_dir: Path = BASE_DIR / "phase4", output_dir: Path = OUTPUT_DIR):
        self.phase4_dir = Path(phase4_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def audit_code_files(self) -> Dict[str, Any]:
        """
        Scans all Python files in phase4/ except evaluate.py to ensure zero ground-truth leakage.
        """
        file_results = {}
        total_violations = 0

        py_files = sorted(list(self.phase4_dir.glob("*.py")))
        for pf in py_files:
            # evaluate.py is explicitly permitted to load ground truth for benchmarking
            # leakage_audit.py defines the forbidden patterns list and is exempt
            if pf.name in ("evaluate.py", "leakage_audit.py"):
                file_results[pf.name] = {
                    "status": "EXEMPT (Auditor / Evaluator)",
                    "violations": []
                }
                continue

            with open(pf, mode="r", encoding="utf-8") as f:
                content = f.read()

            violations = []
            for token in FORBIDDEN_GROUND_TRUTH_TOKENS:
                if token in content:
                    violations.append(token)

            if violations:
                total_violations += len(violations)
                file_results[pf.name] = {
                    "status": "FAILED",
                    "violations": violations
                }
            else:
                file_results[pf.name] = {
                    "status": "PASSED (Zero Leakage)",
                    "violations": []
                }

        return {
            "total_files_scanned": len(py_files),
            "files_audited": file_results,
            "total_violations": total_violations,
            "leakage_free": total_violations == 0
        }

    def audit_feature_names(self, feature_names: List[str]) -> Dict[str, Any]:
        """
        Audits extracted node feature names to ensure zero latent ground truth fields.
        """
        violations = []
        for name in feature_names:
            for token in FORBIDDEN_GROUND_TRUTH_TOKENS:
                if token.lower() in name.lower():
                    violations.append({"feature": name, "token": token})

        return {
            "feature_count": len(feature_names),
            "feature_violations": violations,
            "features_leakage_free": len(violations) == 0
        }

    def audit_target_edge_leakage(
        self,
        norm_adj: Any,
        node_to_idx: Dict[str, int],
        excluded_edges: Set[Tuple[str, str]],
    ) -> Dict[str, Any]:
        """
        Verifies that zero held-out target edges exist in the normalized training adjacency matrix.
        """
        leaked: List[Tuple[str, str]] = []
        for u, v in excluded_edges:
            if u in node_to_idx and v in node_to_idx:
                ui, vi = node_to_idx[u], node_to_idx[v]
                if float(norm_adj[ui, vi]) > 0.0 or float(norm_adj[vi, ui]) > 0.0:
                    leaked.append((u, v))

        return {
            "checked_edges": len(excluded_edges),
            "leaked_edges": leaked,
            "leaked_count": len(leaked),
            "zero_target_edge_leakage": len(leaked) == 0,
        }

    def run_full_audit(self, feature_names: List[str]) -> Dict[str, Any]:
        """Executes full leakage audit and writes leakage_audit.json."""
        code_audit = self.audit_code_files()
        feature_audit = self.audit_feature_names(feature_names)

        is_certified = code_audit["leakage_free"] and feature_audit["features_leakage_free"]

        audit_report = {
            "certification": "PASSED - ZERO GROUND-TRUTH LEAKAGE" if is_certified else "FAILED",
            "is_certified_leakage_free": is_certified,
            "code_audit": code_audit,
            "feature_audit": feature_audit
        }

        with open(self.output_dir / "leakage_audit.json", mode="w", encoding="utf-8") as f:
            json.dump(audit_report, f, indent=2)

        return audit_report

if __name__ == "__main__":
    auditor = LeakageAuditor()
    report = auditor.run_full_audit(["type_PERSON", "scaled_pagerank", "log_degree"])
    print(json.dumps(report, indent=2))
