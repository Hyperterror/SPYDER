"""
Lead Repository and in-memory cache manager.
Provides fast, thread-safe access, filtering, and pagination over Investigation Leads.
"""

from threading import Lock
from typing import Dict, List, Optional, Set, Tuple

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

    def get_leads(
        self,
        case_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
        priority: Optional[str] = None,
        is_cross_case: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> Tuple[int, List[InvestigationLead]]:
        """
        Retrieves filtered, paginated leads respecting case-level access permissions.
        """
        self.load_if_needed()

        filtered = self._leads

        # 1. Filter by specific case_id requested
        if case_id:
            filtered = [
                l for l in filtered
                if case_id in l.source_case_ids or case_id in l.target_case_ids
            ]

        # 2. RBAC Case authorization: restrict to cases user is authorized to view
        if user_allowed_cases is not None:
            filtered = [
                l for l in filtered
                if bool(set(l.source_case_ids) & user_allowed_cases) or bool(set(l.target_case_ids) & user_allowed_cases)
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

        total = len(filtered)
        paged = filtered[offset : offset + limit]
        return total, paged

    def get_lead_by_id(
        self,
        lead_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> Optional[InvestigationLead]:
        """
        Fetches single lead by ID, checking case access permissions.
        """
        self.load_if_needed()
        lead = self._lead_by_id.get(lead_id)
        if not lead:
            return None

        # Check authorization if restricted
        if user_allowed_cases is not None:
            has_source = bool(set(lead.source_case_ids) & user_allowed_cases)
            has_target = bool(set(lead.target_case_ids) & user_allowed_cases)
            if not (has_source or has_target):
                return None

        return lead

    def get_lead_evidence(
        self,
        lead_id: str,
        user_allowed_cases: Optional[Set[str]] = None,
    ) -> Optional[List[StructuredEvidenceRecord]]:
        """
        Returns structured provenance records for a lead.
        """
        lead = self.get_lead_by_id(lead_id, user_allowed_cases=user_allowed_cases)
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
    ) -> Tuple[int, List[CrossCaseLeadSummary]]:
        """
        Returns high-level summaries for leads crossing case boundaries.
        """
        total, leads = self.get_leads(
            is_cross_case=True,
            min_confidence=min_confidence,
            priority=priority,
            limit=limit,
            offset=offset,
            user_allowed_cases=user_allowed_cases,
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
            )
            for l in leads
        ]
        return total, summaries
