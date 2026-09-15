"""
Deterministic Explanation Engine for Investigation Leads.
Generates structured reasons and human-readable narrative summaries based solely
on concrete graph evidence and observed modalities. STRICTLY NO LLM.
"""

from typing import List, Optional
from app.intelligence.models import InvestigationLead, StructuredEvidenceRecord


class ExplanationEngine:
    """
    Deterministic explanation synthesizer.
    Builds both narrative summaries and structured provenance records from real evidence.
    """

    @staticmethod
    def generate_narrative_explanation(
        source_entity: str,
        target_entity: str,
        confidence: float,
        priority: str,
        common_intermediates: List[str],
        supporting_modalities: List[str],
        is_cross_case: bool,
        caveats: List[str],
    ) -> str:
        """
        Synthesizes a neutral, non-prejudicial investigative narrative.
        """
        clauses = []

        # 1. Structural intermediates
        if common_intermediates:
            sample = common_intermediates[:3]
            sample_str = ", ".join(sample)
            if len(common_intermediates) > 3:
                sample_str += f" (+{len(common_intermediates) - 3} more)"
            clauses.append(f"{len(common_intermediates)} shared 2-hop intermediate entity(ies) [{sample_str}]")

        # 2. Modalities
        if supporting_modalities:
            clauses.append(f"corroboration across {len(supporting_modalities)} evidence modality(ies) ({', '.join(supporting_modalities)})")

        # 3. Cross-case vs same-case
        if is_cross_case:
            clauses.append("cross-case operational manifestation")
        else:
            clauses.append("co-occurrence within single case dossier")

        summary = (
            f"Candidate association between {source_entity} and {target_entity} assessed as {priority} "
            f"(model confidence: {confidence:.3f})."
        )
        if clauses:
            summary += f" Supported by: {'; '.join(clauses)}."

        if caveats:
            summary += f" Investigative caveats: {'; '.join(caveats)}."

        return summary

    @staticmethod
    def extract_structured_evidence(
        lead: InvestigationLead,
    ) -> List[StructuredEvidenceRecord]:
        """
        Returns structured provenance records supporting the lead.
        All fields map strictly to observable evidence, returning None where unavailable.
        """
        if lead.supporting_records:
            return lead.supporting_records

        records = []
        for inter in lead.common_intermediates[:5]:
            records.append(
                StructuredEvidenceRecord(
                    reason=f"Shared 2-hop topological intermediate: {inter}",
                    evidence_type="GRAPH_INTERMEDIATE",
                    case_id=lead.source_case_ids[0] if lead.source_case_ids else None,
                    record_id=None,
                    source_file=None,
                    source_row=None,
                    timestamp=None,
                )
            )
        return records
