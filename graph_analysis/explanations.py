"""
Evidence-Backed Explanation Generator.
Synthesizes plain-English, verifiable investigative explanations from graph paths
and supporting records without referencing latent ground truth or prejudicial labels.
"""

from typing import Dict, List, Set, Any

def generate_cross_case_explanation(
    source_case: str,
    target_case: str,
    path_nodes: List[str],
    relationship_types: List[str],
    supporting_evidence: List[Dict[str, Any]],
    connecting_entities: List[str],
    tier: str,
    reasons: List[str]
) -> str:
    """
    Generates a neutral, evidence-backed narrative explanation for a cross-case connection.
    Strictly cites observable artifacts: CDR records, device telemetry, financial transactions,
    vehicle sightings, and provisional entity resolution associations.
    """
    # Categorize evidence sources
    tables_cited = set(e.get("table") or e.get("source_table") for e in supporting_evidence if e.get("table") or e.get("source_table"))
    record_ids = [e.get("id") or e.get("source_id") for e in supporting_evidence if e.get("id") or e.get("source_id")]
    records_preview = ", ".join(record_ids[:4]) + (f" and {len(record_ids) - 4} others" if len(record_ids) > 4 else "")

    entity_str = ", ".join(connecting_entities[:3])
    if len(connecting_entities) > 3:
        entity_str += f" (+{len(connecting_entities) - 3} more)"

    # Describe connecting mechanism
    mechanisms = []
    if any("CALLED" in r for r in relationship_types):
        mechanisms.append("telecom call detail records (CDR)")
    if any("MESSAGED" in r for r in relationship_types):
        mechanisms.append("forensic chat logs")
    if any("USED_DEVICE" in r for r in relationship_types):
        mechanisms.append("shared hardware device/IMEI logs")
    if any("USED_VEHICLE" in r for r in relationship_types) or any("TRAVELLED_TO" in r for r in relationship_types):
        mechanisms.append("interstate transit/toll movements")
    if any("TRANSFERRED_MONEY" in r for r in relationship_types):
        mechanisms.append("financial bank ledger transactions")
    if any("OBSERVES_ENTITY" in r for r in relationship_types):
        mechanisms.append("provisional multi-modal entity resolution associations")

    mechanism_desc = "; ".join(mechanisms) if mechanisms else "shared observational evidence trails"

    # Assemble narrative
    narrative_parts = [
        f"Cases {source_case} and {target_case} are linked via a {len(path_nodes)-1}-hop evidence path "
        f"through connecting entity trail [{entity_str}]."
    ]

    narrative_parts.append(
        f"Connection mechanism relies on {mechanism_desc}. "
        f"Corroborating records include {len(supporting_evidence)} observable entries from {', '.join(sorted(list(tables_cited)))} "
        f"(such as {records_preview})."
    )

    if reasons:
        narrative_parts.append(f"Investigative priority assessed as {tier} based on: {'; '.join(reasons)}.")

    return " ".join(narrative_parts)
