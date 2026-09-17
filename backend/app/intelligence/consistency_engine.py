"""
Phase 6B: Consistency Engine.
Core coordination engine for Statement-Evidence Consistency Analysis.
Evaluates structured investigative assertions against observable case evidence.
Strictly implements:
- High bar for CONTRADICTED (direct, high-strength empirical evidence required).
- Suppression of false contradictions from device logs, shared IPs, or shared transport.
- Four distinct confidence dimensions (extraction, entity resolution, evidence match, consistency).
- Deterministic evaluation and strictly non-prejudicial terminology.
"""

import hashlib
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

from app.intelligence.claim_extractor import ClaimExtractor
from app.intelligence.claim_models import (
    AnalyzeStatementRequest,
    AnalyzeStatementResponse,
    ClaimPredicate,
    ConfidenceBreakdown,
    ConsistencyAnalysisResult,
    ConsistencyListResponse,
    ConsistencyStatus,
    EvidenceStrength,
    MatchedEvidenceRecord,
    StructuredClaim,
)
from app.intelligence.claim_normalizer import ClaimNormalizer
from app.intelligence.consistency_explanations import ConsistencyExplanationBuilder
from app.intelligence.evidence_matcher import EvidenceMatcher


class ConsistencyEngine:
    """
    Evaluates claims extracted from statements against empirical dossier evidence.
    """

    _instance: Optional["ConsistencyEngine"] = None
    _lock = Lock()

    def __init__(
        self,
        extractor: Optional[ClaimExtractor] = None,
        normalizer: Optional[ClaimNormalizer] = None,
        matcher: Optional[EvidenceMatcher] = None,
    ):
        self.normalizer = normalizer or ClaimNormalizer.get_instance()
        self.extractor = extractor or ClaimExtractor(self.normalizer)
        self.matcher = matcher or EvidenceMatcher.get_instance()
        self.explanation_builder = ConsistencyExplanationBuilder()

        # Thread-safe in-memory cache of analysis results
        self._results_cache: Dict[str, ConsistencyAnalysisResult] = {}

    @classmethod
    def get_instance(cls) -> "ConsistencyEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def analyze_statement(
        self,
        request: AnalyzeStatementRequest,
        authorized_cases: Optional[List[str]] = None,
    ) -> AnalyzeStatementResponse:
        """
        Parses statement text into structured claims and evaluates each claim against evidence.
        """
        claims = self.extractor.extract_claims(
            statement_text=request.statement_text,
            case_id=request.case_id,
            subject_entity_id=request.subject_entity_id,
            source_document_id=request.source_document_id or "Unavailable",
        )

        results: List[ConsistencyAnalysisResult] = []
        for claim in claims:
            result = self.evaluate_claim(claim, authorized_cases=authorized_cases)
            results.append(result)
            with self._lock:
                self._results_cache[result.result_id] = result

        return AnalyzeStatementResponse(
            statement_text=request.statement_text,
            case_id=request.case_id,
            total_claims_extracted=len(claims),
            results=results,
        )

    def evaluate_claim(
        self,
        claim: StructuredClaim,
        authorized_cases: Optional[List[str]] = None,
    ) -> ConsistencyAnalysisResult:
        """
        Evaluates a single StructuredClaim against case evidence enforcing high contradiction bar.
        """
        # If predicate was not recognized or extracted
        if not claim.predicate:
            status = ConsistencyStatus.UNVERIFIABLE
            confidence = ConfidenceBreakdown(
                claim_extraction_confidence=claim.claim_extraction_confidence,
                entity_match_confidence=claim.entity_match_confidence,
                evidence_match_confidence=0.0,
                consistency_confidence=0.20,
            )
            explanation, rec_action = self.explanation_builder.build_explanation(
                claim=claim,
                status=status,
                matched=[],
                conflicts=[],
                caveats=[],
            )
            result_id = f"RES_{claim.claim_id}"
            return ConsistencyAnalysisResult(
                result_id=result_id,
                claim=claim,
                status=status,
                confidence=confidence,
                overall_evidence_strength=EvidenceStrength.LOW,
                matched_evidence=[],
                conflicting_evidence=[],
                explanation=explanation,
                caveats=["No relational predicate recognized in text."],
                recommended_action=rec_action,
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Match empirical evidence records
        matched, conflicts, evidence_conf, caveats = self.matcher.match_evidence_for_claim(
            claim=claim,
            authorized_cases=authorized_cases,
        )

        # Determine overall evidence strength
        all_records = matched + conflicts
        if any(r.evidence_strength == EvidenceStrength.HIGH for r in all_records):
            overall_strength = EvidenceStrength.HIGH
        elif any(r.evidence_strength == EvidenceStrength.MEDIUM for r in all_records):
            overall_strength = EvidenceStrength.MEDIUM
        else:
            overall_strength = EvidenceStrength.LOW

        # =========================================================================
        # DECISION RULES & HIGH BAR FOR CONTRADICTED
        # =========================================================================
        # Rule 1: Both corroborating and conflicting evidence exist -> EVIDENCE_CONFLICT
        if matched and conflicts:
            # Check if conflicting evidence is merely indirect device/public telemetry
            high_conflicts = [c for c in conflicts if c.evidence_strength == EvidenceStrength.HIGH]
            high_matched = [m for m in matched if m.evidence_strength == EvidenceStrength.HIGH]
            if high_conflicts and high_matched:
                status = ConsistencyStatus.EVIDENCE_CONFLICT
            elif high_matched and not high_conflicts:
                # Strong corroboration with only weak/indirect contradiction
                status = ConsistencyStatus.SUPPORTED
                caveats.append("Minor divergent telemetry observed but superseded by primary physical evidence.")
            elif high_conflicts and not high_matched:
                if claim.entity_match_confidence >= 0.80:
                    status = ConsistencyStatus.CONTRADICTED
                else:
                    status = ConsistencyStatus.EVIDENCE_CONFLICT
            else:
                status = ConsistencyStatus.EVIDENCE_CONFLICT

        # Rule 2: Only conflicting evidence exists
        elif conflicts and not matched:
            # MANDATORY CORRECTION 2: HIGH BAR FOR CONTRADICTED
            # Must satisfy:
            # - entity_match_confidence >= 0.80 (strong entity match, not provisional)
            # - At least one HIGH strength conflict (e.g. CCTV, reservation chart, direct CDR)
            # - Must not be based solely on device location, shared IP, or vehicle association
            has_high_direct = any(
                c.evidence_strength == EvidenceStrength.HIGH
                and c.source_table not in ("device_logs.csv", "vehicle_records.csv")
                for c in conflicts
            )

            # Direct check for CDR/Chat direct contradiction
            if claim.predicate in (ClaimPredicate.CALLED, ClaimPredicate.CONTACTED) and any(
                c.evidence_strength == EvidenceStrength.HIGH for c in conflicts
            ):
                has_high_direct = True

            # Direct check for financial transaction contradiction
            if claim.predicate == ClaimPredicate.TRANSFERRED_TO and any(
                c.evidence_strength == EvidenceStrength.HIGH for c in conflicts
            ):
                has_high_direct = True

            if has_high_direct and claim.entity_match_confidence >= 0.80:
                status = ConsistencyStatus.CONTRADICTED
            else:
                # Does NOT meet high bar for CONTRADICTED! Fall back to UNVERIFIABLE
                status = ConsistencyStatus.UNVERIFIABLE
                caveats.append(
                    "Conflicting telemetry (device ping, shared IP, or provisional entity) "
                    "does not meet the threshold for definitive contradiction."
                )

        # Rule 3: Only corroborating evidence exists
        elif matched and not conflicts:
            status = ConsistencyStatus.SUPPORTED

        # Rule 4: No evidence found
        else:
            status = ConsistencyStatus.UNVERIFIABLE

        # Compute multi-dimensional confidence breakdown
        # consistency_confidence: explainable composite score
        if status == ConsistencyStatus.SUPPORTED:
            base_cons = 0.25 * claim.claim_extraction_confidence + 0.35 * claim.entity_match_confidence + 0.40 * evidence_conf
        elif status == ConsistencyStatus.CONTRADICTED:
            base_cons = 0.20 * claim.claim_extraction_confidence + 0.40 * claim.entity_match_confidence + 0.40 * evidence_conf
        elif status == ConsistencyStatus.EVIDENCE_CONFLICT:
            base_cons = 0.50  # Moderate certainty due to empirical conflict
        else:  # UNVERIFIABLE
            base_cons = 0.25

        confidence = ConfidenceBreakdown(
            claim_extraction_confidence=round(claim.claim_extraction_confidence, 3),
            entity_match_confidence=round(claim.entity_match_confidence, 3),
            evidence_match_confidence=round(evidence_conf, 3),
            consistency_confidence=round(min(1.0, max(0.1, base_cons)), 3),
        )

        explanation, rec_action = self.explanation_builder.build_explanation(
            claim=claim,
            status=status,
            matched=matched,
            conflicts=conflicts,
            caveats=caveats,
        )

        result_id = f"RES_{claim.claim_id}"
        return ConsistencyAnalysisResult(
            result_id=result_id,
            claim=claim,
            status=status,
            confidence=confidence,
            overall_evidence_strength=overall_strength,
            matched_evidence=matched,
            conflicting_evidence=conflicts,
            explanation=explanation,
            caveats=list(set(caveats)),
            recommended_action=rec_action,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_result(
        self,
        result_id: str,
        authorized_cases: Optional[List[str]] = None,
    ) -> Optional[ConsistencyAnalysisResult]:
        """Retrieves a cached result by ID, enforcing case authorization."""
        with self._lock:
            res = self._results_cache.get(result_id)
        if not res:
            return None
        if authorized_cases is not None and res.claim.case_id not in authorized_cases:
            return None
        return res

    def list_results(
        self,
        case_id: Optional[str] = None,
        status: Optional[ConsistencyStatus] = None,
        limit: int = 50,
        offset: int = 0,
        authorized_cases: Optional[List[str]] = None,
    ) -> ConsistencyListResponse:
        """Lists cached analysis results with filtering, pagination, and RBAC."""
        with self._lock:
            all_res = list(self._results_cache.values())

        # RBAC filter
        if authorized_cases is not None:
            all_res = [r for r in all_res if r.claim.case_id in authorized_cases]

        # Case filter
        if case_id:
            all_res = [r for r in all_res if r.claim.case_id == case_id]

        # Status filter
        if status:
            all_res = [r for r in all_res if r.status == status]

        total = len(all_res)
        supported_count = sum(1 for r in all_res if r.status == ConsistencyStatus.SUPPORTED)
        contradicted_count = sum(1 for r in all_res if r.status == ConsistencyStatus.CONTRADICTED)
        unverifiable_count = sum(1 for r in all_res if r.status == ConsistencyStatus.UNVERIFIABLE)
        conflict_count = sum(1 for r in all_res if r.status == ConsistencyStatus.EVIDENCE_CONFLICT)

        paginated = all_res[offset : offset + limit]

        return ConsistencyListResponse(
            total=total,
            limit=limit,
            offset=offset,
            supported_count=supported_count,
            contradicted_count=contradicted_count,
            unverifiable_count=unverifiable_count,
            conflict_count=conflict_count,
            results=paginated,
        )
