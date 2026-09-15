"""
Explainability Module for Phase 4 Link Predictions.
Deconstructs GraphSAGE predictions into human-interpretable topological and evidence-backed
structural rationales without referencing latent ground truth or prejudicial labels.
"""

from typing import Dict, List, Set, Any, Optional

def generate_prediction_explanation(
    source_node: str,
    target_node: str,
    score: float,
    tier: str,
    common_neighbors: List[Dict[str, str]],
    is_cross_case: bool,
    shared_modalities: List[str],
    penalty_reasons: Optional[List[str]] = None
) -> str:
    """
    Generates a clear, neutral investigative explanation for a predicted candidate association.
    """
    reasons = []

    # 1. Proximity & Modality Signals
    if common_neighbors:
        nbr_types = set(n["type"] for n in common_neighbors)
        nbr_names = [f"{n['id']} ({n['type']})" for n in common_neighbors[:3]]
        preview = ", ".join(nbr_names)
        if len(common_neighbors) > 3:
            preview += f" (+{len(common_neighbors) - 3} more)"
        reasons.append(f"{len(common_neighbors)} shared 2-hop structural intermediate(s) [{preview}]")

    if shared_modalities:
        reasons.append(f"convergent activity across {len(shared_modalities)} evidence modalities ({', '.join(shared_modalities)})")

    if is_cross_case:
        reasons.append("cross-case operational manifestation")
    else:
        reasons.append("co-occurrence within same case dossier")

    # 2. Penalty or Discount Warnings
    warnings = []
    if penalty_reasons:
        warnings.extend(penalty_reasons)

    if score < 0.40 and not warnings:
        warnings.append("weak structural affinity and absence of independent corroborating evidence")

    # Assemble narrative
    narrative = [
        f"Candidate association between {source_node} and {target_node} assessed as {tier} "
        f"(model confidence: {score:.3f})."
    ]

    if reasons:
        narrative.append(f"Supported by: {'; '.join(reasons)}.")

    if warnings:
        narrative.append(f"Investigative caveats: {'; '.join(warnings)}.")

    return " ".join(narrative)
