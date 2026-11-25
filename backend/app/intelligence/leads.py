"""
Lead Repository and in-memory cache manager.
Provides fast, thread-safe access, filtering, and pagination over Investigation Leads
with strict multi-case RBAC isolation.
"""

from threading import Lock
from typing import Dict, List, Optional, Set, Tuple

from app.core.authz import all_cases_authorized
from app.intelligence.adapter import Phase4ArtifactAdapter
from app.intelligence.models import (
    CrossCaseLeadSummary,
    InvestigationLead,
    PriorityTier,
    StructuredEvidenceRecord,
)


class LeadRepository:
    """
    Singleton repository managing in-memory cache of investigation leads.
    Avoids reading large CSV files on every API request.
    """

    _instance: Optional["LeadRepository"] = None
    _lock: Lock = Lock()

    def __init__(self, adapter: Optional[Phase4ArtifactAdapter] = None):
        self.adapter = adapter or Phase4ArtifactAdapter()
        self._leads: List[InvestigationLead] = []
        self._lead_by_id: Dict[str, InvestigationLead] = {}
        self._loaded: bool = False
        self._load_lock: Lock = Lock()

    @classmethod
    def get_instance(cls) -> "LeadRepository":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def load_if_needed(self) -> None:
        """Loads Phase 4 leads into cache once thread-safely."""
        if self._loaded:
            return
        with self._load_lock:
            if not self._loaded:
                leads = self.adapter.load_leads()
                self._leads = leads
                self._lead_by_id = {l.lead_id: l for l in leads}
                self._loaded = True

    def reload(self) -> None:
        """Forces reload of cache (useful during testing or data refresh)."""
        with self._load_lock:
            leads = self.adapter.load_leads()
            self._leads = leads
            self._lead_by_id = {l.lead_id: l for l in leads}
            self._loaded = True

    @staticmethod
    def _lead_is_authorized(lead: InvestigationLead, user_allowed_cases: Optional[Set[str]]) -> bool:
        """
        Strict cross-case authorization policy (PRD 8.2):
        Full cross-case lead details are accessible ONLY when the user has permission
        for EVERY case involved in the lead (source and target).
        """
        if user_allowed_cases is None:
            return True
        all_cases = set(lead.source_case_ids) | set(lead.target_case_ids)
        return all_cases_authorized(all_cases, user_allowed_cases)

    @staticmethod
    def _sanitize_lead_records(
        lead: InvestigationLead,
        user_allowed_cases: Optional[Set[str]],
    ) -> InvestigationLead:
        if user_allowed_cases is None:
            return lead
        allowed_records = [
            rec for rec in lead.supporting_records
            if not rec.case_id or rec.case_id in user_allowed_cases
        ]
        if len(allowed_records) == len(lead.supporting_records):
            return lead
        copy = lead.model_copy(deep=True)
        copy.supporting_records = allowed_records
        return copy

    def get_leads(
        self,
        case_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
        priority: Optional[str] = None,
        is_cross_case: Optional[bool] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_allowed_cases: Optional[Set[str]] = None,
        db=None,
    ) -> Tuple[int, List[InvestigationLead]]:
        """
        Retrieves filtered, paginated leads combining Phase 4 artifacts and live DB
        IntelligenceLeadRecords, respecting strict multi-case access permissions.
        """
        self.load_if_needed()

        combined_by_id: Dict[str, InvestigationLead] = {}
        artifact_by_id: Dict[str, InvestigationLead] = {l.lead_id: l for l in self._leads}

        if db is not None:
            from app.models.intelligence import IntelligenceLeadRecord
            db_rows = (
                db.query(IntelligenceLeadRecord)
                .order_by(IntelligenceLeadRecord.created_at.desc())
                .all()
            )
            for row in db_rows:
                sup_recs = [
                    StructuredEvidenceRecord(
                        reason=r.get("reason") or f"Observed {r.get('record_type', 'EVIDENCE')} record in {r.get('source_file', 'source')}",
                        evidence_type=r.get("evidence_type") or r.get("record_type") or "PERSONS",
                        case_id=r.get("case_id"),
                        record_id=r.get("record_id") or r.get("evidence_id"),
                        source_file=r.get("source_file"),
                        source_row=r.get("source_row"),
                        timestamp=r.get("timestamp"),
                    ) if isinstance(r, dict) else r
                    for r in (row.supporting_records or [])
                ]
                conf_recs = [
                    StructuredEvidenceRecord(
                        reason=r.get("reason", "Conflicting observation"),
                        evidence_type=r.get("evidence_type", "ENTITY_RESOLUTION"),
                        case_id=r.get("case_id"),
                        record_id=r.get("record_id"),
                        source_file=r.get("source_file"),
                        source_row=r.get("source_row"),
                        timestamp=r.get("timestamp"),
                    )
                    for r in (row.conflicting_records or [])
                    if isinstance(r, dict)
                ]
                try:
                    prio = PriorityTier(row.priority_tier)
                except ValueError:
                    prio = PriorityTier.REVIEW

                base_existing = artifact_by_id.get(row.lead_code)
                if base_existing is not None:
                    updated = base_existing.model_copy(deep=True)
                    updated.status = row.status
                    updated.reviewed_by = str(row.reviewed_by) if row.reviewed_by else None
                    updated.decision_rationale = row.decision_rationale
                    artifact_by_id[row.lead_code] = updated
                else:
                    from app.intelligence.models import EvidenceStrength, PredictionType
                    try:
                        ev_str = EvidenceStrength(row.evidence_strength)
                    except ValueError:
                        ev_str = EvidenceStrength.MODERATE
                    combined_by_id[row.lead_code] = InvestigationLead(
                        lead_id=row.lead_code,
                        source_entity=row.source_entity,
                        target_entity=row.target_entity,
                        source_case_ids=list(row.source_case_ids or []),
                        target_case_ids=list(row.target_case_ids or []),
                        is_cross_case=bool(row.is_cross_case),
                        confidence=float(row.prediction_score),
                        priority=prio,
                        prediction_type=PredictionType.POTENTIAL_ASSOCIATION,
                        evidence_strength=ev_str,
                        explanation=row.explanation,
                        supporting_modalities=list(row.supporting_modalities or []),
                        common_intermediates_count=len(row.common_intermediates or []),
                        common_intermediates=list(row.common_intermediates or []),
                        caveats=list(row.caveats or []),
                        supporting_records=sup_recs,
                        conflicting_records=conf_recs,
                        status=row.status,
                        model_version=row.model_version,
                        reviewed_by=str(row.reviewed_by) if row.reviewed_by else None,
                        decision_rationale=row.decision_rationale,
                        created_at=row.created_at.isoformat(),
                    )

        for lid, lead_obj in artifact_by_id.items():
            combined_by_id.setdefault(lid, lead_obj)

        filtered = list(combined_by_id.values())

        # 1. Filter by specific case_id requested
        if case_id:
            filtered = [
                l for l in filtered
                if case_id in l.source_case_ids or case_id in l.target_case_ids
            ]

        # 2. Strict RBAC Case authorization: user must be authorized for EVERY case in the lead
        if user_allowed_cases is not None:
            filtered = [
                self._sanitize_lead_records(l, user_allowed_cases)
                for l in filtered
                if self._lead_is_authorized(l, user_allowed_cases)
            ]

        # 3. Filter by minimum confidence score
        if min_confidence is not None:
            filtered = [l for l in filtered if l.confidence >= min_confidence]

        # 4. Filter by priority tier
        if priority:
            p_upper = priority.strip().upper()
            filtered = [l for l in filtered if l.priority.value == p_upper]

        # 5. Filter by cross-case flag
        if is_cross_case is not None:
            filtered = [l for l in filtered if l.is_cross_case is is_cross_case]

        # 6. Filter by review status
        if status_filter:
            s_upper = status_filter.strip().upper()
            filtered = [l for l in filtered if l.status.upper() == s_upper]

        total = len(filtered)
        paged = filtered[offset : offset + limit]
        return total, paged

    def get_lead_by_id(
        self,
        lead_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
        db=None,
    ) -> Optional[InvestigationLead]:
        """
        Fetches single lead by ID, enforcing strict multi-case clearance.
        """
        self.load_if_needed()
        _, all_leads = self.get_leads(limit=100000, offset=0, user_allowed_cases=None, db=db)
        lead = next((l for l in all_leads if l.lead_id == lead_id), None)
        if not lead:
            return None

        if not self._lead_is_authorized(lead, user_allowed_cases):
            return None

        return self._sanitize_lead_records(lead, user_allowed_cases)

    def get_lead_evidence(
        self,
        lead_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
        db=None,
    ) -> Optional[List[StructuredEvidenceRecord]]:
        """
        Returns structured provenance records for a lead.
        """
        lead = self.get_lead_by_id(lead_id, user_allowed_cases=user_allowed_cases, db=db)
        if not lead:
            return None
        return lead.supporting_records

    def get_cross_case_leads(
        self,
        min_confidence: Optional[float] = None,
        priority: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_allowed_cases: Optional[Set[str]] = None,
        db=None,
    ) -> Tuple[int, List[CrossCaseLeadSummary]]:
        """
        Returns high-level summaries for leads crossing case boundaries where the
        user holds clearance for all participating cases.
        """
        total, leads = self.get_leads(
            is_cross_case=True,
            min_confidence=min_confidence,
            priority=priority,
            limit=limit,
            offset=offset,
            user_allowed_cases=user_allowed_cases,
            db=db,
        )
        summaries = [
            CrossCaseLeadSummary(
                lead_id=l.lead_id,
                source_entity=l.source_entity,
                target_entity=l.target_entity,
                source_cases=l.source_case_ids,
                target_cases=l.target_case_ids,
                confidence=l.confidence,
                priority=l.priority,
                supporting_modalities=l.supporting_modalities,
                common_intermediates_count=l.common_intermediates_count,
                caveats=l.caveats,
                status=l.status,
            )
            for l in leads
        ]
        return total, summaries
