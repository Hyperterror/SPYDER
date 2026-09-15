"""
Explainability Module for Entity Resolution.
Generates human-readable, evidence-based rationales for match and non-match predictions
strictly from observable feature values (without exposing ground truth).
"""

from typing import Dict, List, Any

def generate_explanation(features: Dict[str, Any], prob: float, p1: Dict[str, Any] = None, p2: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generates human-readable supporting evidence and conflicting factors for a prediction.
    """
    supporting_reasons = []
    conflicting_reasons = []

    # 1. Phone match
    if features.get("phone_exact_match", 0.0) == 1.0:
        supporting_reasons.append("Exact phone number match across evidence records")
    elif features.get("phone_both_present", 0.0) == 1.0:
        conflicting_reasons.append("Different recorded phone numbers")

    # 2. IMEI / Device ID
    if features.get("imei_match", 0.0) == 1.0:
        supporting_reasons.append("Identical 15-digit device IMEI match")
    elif features.get("device_id_match", 0.0) == 1.0:
        supporting_reasons.append("Shared observational device identifier")

    # 3. Vehicle Registration
    if features.get("vehicle_reg_match", 0.0) == 1.0:
        supporting_reasons.append("Direct shared vehicle registration sighting in transit records")

    # 4. Name & Alias
    name_sim = features.get("name_levenshtein_sim", 0.0)
    jw_sim = features.get("name_jaro_winkler_sim", 0.0)
    best_name_sim = max(name_sim, jw_sim)

    if features.get("name_exact_match", 0.0) == 1.0:
        supporting_reasons.append("Exact normalized name match")
    elif best_name_sim >= 0.75:
        supporting_reasons.append(f"Strong name similarity score ({best_name_sim:.2f})")
    elif best_name_sim < 0.40:
        conflicting_reasons.append(f"Low name similarity score ({best_name_sim:.2f})")

    if features.get("alias_exact_match", 0.0) == 1.0:
        supporting_reasons.append("Identical alias recorded across case dossiers")
    elif features.get("name_alias_cross_match", 0.0) == 1.0:
        supporting_reasons.append("Recorded alias in one case matches observed name token in counterparty case")

    # 5. Semantic Profile (Sentence Transformer)
    cos_sim = features.get("context_embedding_cosine_sim", 0.0)
    if cos_sim >= 0.85:
        supporting_reasons.append(f"High semantic profile similarity ({cos_sim:.2f}) across observable context")
    elif cos_sim < 0.45:
        conflicting_reasons.append(f"Low semantic profile similarity ({cos_sim:.2f})")

    # 6. Public Infrastructure IP Warning
    if features.get("shared_ip_is_public_infra", 0.0) == 1.0:
        conflicting_reasons.append("Shared IP address is confirmed public transit infrastructure (lodge/kiosk hotspot) and does not indicate identity")

    # 7. Contacts & Communications
    if features.get("shared_contacts_count", 0.0) > 0:
        supporting_reasons.append(f"Shared mutual telecommunication counterparty contacts ({int(features['shared_contacts_count'])})")

    # Build final summary statement
    if prob >= 0.90:
        summary_statement = f"Likely same entity — {prob*100:.1f}% confidence"
    elif prob >= 0.70:
        summary_statement = f"Potential identity match (Requires investigator review) — {prob*100:.1f}% confidence"
    else:
        summary_statement = f"Likely different entities — {(1.0 - prob)*100:.1f}% confidence"

    return {
        "summary": summary_statement,
        "probability": round(prob, 4),
        "supporting_reasons": supporting_reasons if supporting_reasons else ["Limited corroborating digital identifiers"],
        "conflicting_reasons": conflicting_reasons if conflicting_reasons else ["No major contradictory evidence found"]
    }
