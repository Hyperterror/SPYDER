"""
Phase 6B: Consistency Explanations.
Generates objective, feature-grounded explanations, public infrastructure caveats,
and recommended investigative follow-up actions for statement consistency evaluations.
Strictly enforces neutral, non-prejudicial, non-judgmental language.
"""

from typing import List, Tuple

from app.intelligence.claim_models import (
    ConsistencyStatus,
    EvidenceStrength,
    MatchedEvidenceRecord,
    StructuredClaim,
)


class ConsistencyExplanationBuilder:
    """
    Constructs explainable, audit-compliant justifications and actionable recommendations.
    """

    @staticmethod
    def build_explanation(
        claim: StructuredClaim,
        status: ConsistencyStatus,
        matched: List[MatchedEvidenceRecord],
        conflicts: List[MatchedEvidenceRecord],
        caveats: List[str],
    ) -> Tuple[str, str]:
        """
        Builds neutral explanation text and recommended investigative action.
        Returns: (explanation, recommended_action)
        """
        pred_desc = claim.predicate.value if claim.predicate else "ASSERTED"
        subj = claim.subject_entity_id
        obj = claim.object_entity_id or claim.location_id or "unspecified entity"

        # 1. Explanation Construction
        if status == ConsistencyStatus.SUPPORTED:
            record_count = len(matched)
            top_record = matched[0]
            explanation = (
                f"Assertion regarding {pred_desc} with {obj} is corroboratingly aligned with "
                f"{record_count} empirical record(s) in case dossier. "
                f"Primary corroboration: {top_record.match_rationale}"
            )
            rec_action = (
                f"Document verified consistency in case file. "
                f"Cross-reference source record ({top_record.source_table} - {top_record.record_id}) "
                f"for official judicial submission."
            )

        elif status == ConsistencyStatus.CONTRADICTED:
            record_count = len(conflicts)
            top_record = conflicts[0]
            explanation = (
                f"Assertion regarding {pred_desc} with {obj} materially diverges from "
                f"{record_count} high-confidence empirical record(s). "
                f"Direct divergence observed: {top_record.match_rationale}"
            )
            rec_action = (
                f"Examine primary physical and telecommunication evidence "
                f"({top_record.source_table} - {top_record.record_id}) with senior investigative team. "
                f"Seek formal corroborative verification before drawing procedural inferences."
            )

        elif status == ConsistencyStatus.EVIDENCE_CONFLICT:
            explanation = (
                f"Investigative evidence exhibits internal divergence: {len(matched)} record(s) "
                f"corroborate the assertion while {len(conflicts)} independent record(s) indicate "
                f"opposing temporal, geographical, or relational indicators."
            )
            rec_action = (
                f"Initiate independent forensic verification to reconcile discrepancy between "
                f"competing records (e.g. comparing physical transit manifests against network telemetry)."
            )

        else:  # UNVERIFIABLE
            if not claim.predicate:
                explanation = (
                    "Statement content does not contain recognizable investigative relational "
                    "predicates (telecom, financial, transit, or physical presence) within system ontology."
                )
                rec_action = "Review manual statement documentation for qualitative investigative context."
            elif not matched and not conflicts:
                explanation = (
                    f"No empirical records (CDR, messaging, banking, transit, or device logs) "
                    f"were found matching {pred_desc} involving {subj} within the active case dossier."
                )
                rec_action = (
                    f"Issue targeted record requests (e.g., CDR preservation or bank transaction slips) "
                    f"for entity handles to enable verification."
                )
            else:
                explanation = (
                    f"Existing records regarding {pred_desc} provide inconclusive or indirect associations "
                    f"insufficient to establish factual alignment or material divergence."
                )
                rec_action = "Seek direct primary source evidence to resolve ambiguity."

        return explanation, rec_action
