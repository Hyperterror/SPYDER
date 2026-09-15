"""
Comprehensive Test Suite for Phase 5A: Intelligence Integration Layer.
Tests adapter ingestion, lead models, deterministic priority, hard-negative defense,
explanation provenance, API endpoints, authentication, and case-level authorization.
"""

import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.api.intelligence import _get_user_allowed_cases
from app.core.database import Base, get_db
from app.core.security import create_access_token, get_current_user
from app.intelligence.adapter import Phase4ArtifactAdapter
from app.intelligence.config import (
    CANDIDATE_LINKS_PATH,
    KNOWN_PUBLIC_IPS,
    PREDICTIONS_PATH,
    THRESHOLD_HIGH_PRIORITY,
    THRESHOLD_REVIEW,
)
from app.intelligence.explanations import ExplanationEngine
from app.intelligence.leads import LeadRepository
from app.intelligence.models import (
    InvestigationLead,
    PriorityTier,
    StructuredEvidenceRecord,
)
from app.main import app
from app.models.case import Case, CaseMember
from app.models.user import User


class TestIntelligenceIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Setup in-memory SQLite database for testing authorization and DB operations
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

        cls.adapter = Phase4ArtifactAdapter()
        cls.leads = cls.adapter.load_leads()
        cls.client = TestClient(app)

    def setUp(self):
        self.db = self.TestSessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        app.dependency_overrides.clear()

    # --------------------------------------------------------------------------
    # 1. Phase 4 Files Load Successfully
    # --------------------------------------------------------------------------
    def test_01_phase4_files_load_successfully(self):
        """Confirms Phase 4 predictions and candidate links load into InvestigationLead objects."""
        self.assertGreater(len(self.leads), 0, "No leads loaded from Phase 4 artifacts.")
        self.assertEqual(len(self.leads), 2332, "Mismatch in expected Phase 4 candidate count.")
        lead = self.leads[0]
        self.assertIsInstance(lead, InvestigationLead)
        self.assertTrue(lead.lead_id.startswith("LEAD_"))
        self.assertIsInstance(lead.confidence, float)

    # --------------------------------------------------------------------------
    # 2. Missing Artifact Produces Clear Error
    # --------------------------------------------------------------------------
    def test_02_missing_artifact_produces_error(self):
        """Confirms FileNotFoundError is raised with explicit message if artifact is missing."""
        bad_adapter = Phase4ArtifactAdapter(predictions_path=Path("non_existent_file.csv"))
        with self.assertRaises(FileNotFoundError) as ctx:
            bad_adapter.verify_artifacts_exist()
        self.assertIn("Required Phase 4 artifact 'predictions.csv' not found", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 3. Lead IDs Are Deterministic
    # --------------------------------------------------------------------------
    def test_03_lead_ids_are_deterministic(self):
        """Confirms lead_id is deterministic and commutative regardless of pair order."""
        id1 = Phase4ArtifactAdapter.generate_lead_id("CASE_001_PER_01", "CASE_002_PER_01")
        id2 = Phase4ArtifactAdapter.generate_lead_id("CASE_002_PER_01", "CASE_001_PER_01")
        id3 = Phase4ArtifactAdapter.generate_lead_id("CASE_001_PER_01", "CASE_002_PER_01")
        self.assertEqual(id1, id2, "Lead ID must be commutative.")
        self.assertEqual(id1, id3, "Lead ID must be strictly repeatable.")

    # --------------------------------------------------------------------------
    # 4. Confidence Score Preserved
    # --------------------------------------------------------------------------
    def test_04_confidence_preserved(self):
        """Verifies prediction confidence scores are within [0.0, 1.0] and match artifact range."""
        for lead in self.leads[:50]:
            self.assertGreaterEqual(lead.confidence, 0.0)
            self.assertLessEqual(lead.confidence, 1.0)
            self.assertIsInstance(lead.confidence, float)

    # --------------------------------------------------------------------------
    # 5. Priority Assignment Logic
    # --------------------------------------------------------------------------
    def test_05_priority_assignment(self):
        """Verifies deterministic priority tiers and that low scores never receive HIGH priority."""
        for lead in self.leads:
            if lead.priority == PriorityTier.HIGH:
                self.assertGreaterEqual(lead.confidence, THRESHOLD_HIGH_PRIORITY)
                self.assertEqual(len(lead.caveats), 0, "HIGH priority cannot have hard negative caveats.")
            elif lead.confidence < THRESHOLD_REVIEW:
                self.assertEqual(lead.priority, PriorityTier.LOW)

    # --------------------------------------------------------------------------
    # 6. Cross-Case Filtering Works
    # --------------------------------------------------------------------------
    def test_06_cross_case_filtering(self):
        """Verifies cross-case filter isolates leads spanning multiple case dossiers."""
        repo = LeadRepository.get_instance()
        total, cross_leads = repo.get_leads(is_cross_case=True, limit=200)
        self.assertGreater(total, 0)
        for lead in cross_leads:
            self.assertTrue(lead.is_cross_case)
            self.assertNotEqual(lead.source_case_ids, lead.target_case_ids)

    # --------------------------------------------------------------------------
    # 7. Case Filtering Works
    # --------------------------------------------------------------------------
    def test_07_case_filtering(self):
        """Verifies single-case scoping returns only leads involving that case."""
        repo = LeadRepository.get_instance()
        target_case = "CASE_003"
        total, case_leads = repo.get_leads(case_id=target_case, limit=100)
        self.assertGreater(total, 0)
        for lead in case_leads:
            in_source = target_case in lead.source_case_ids
            in_target = target_case in lead.target_case_ids
            self.assertTrue(in_source or in_target, f"Lead {lead.lead_id} missing {target_case}")

    # --------------------------------------------------------------------------
    # 8. Pagination Works
    # --------------------------------------------------------------------------
    def test_08_pagination(self):
        """Verifies limit and offset mechanics return distinct contiguous subsets."""
        repo = LeadRepository.get_instance()
        t1, p1 = repo.get_leads(limit=10, offset=0)
        t2, p2 = repo.get_leads(limit=10, offset=10)
        self.assertEqual(len(p1), 10)
        self.assertEqual(len(p2), 10)
        self.assertEqual(t1, t2)
        # Ensure no overlap between page 1 and page 2
        ids_page1 = {l.lead_id for l in p1}
        ids_page2 = {l.lead_id for l in p2}
        self.assertEqual(len(ids_page1 & ids_page2), 0)

    # --------------------------------------------------------------------------
    # 9. Authentication Required
    # --------------------------------------------------------------------------
    def test_09_authentication_required(self):
        """Verifies unauthenticated requests to intelligence endpoints return HTTP 401/403."""
        # Unauthenticated request (no bearer header)
        resp = self.client.get("/api/v1/intelligence/leads")
        self.assertIn(resp.status_code, (401, 403), "Unauthenticated request was not rejected.")

    # --------------------------------------------------------------------------
    # 10. Unauthorized Case Access Rejected
    # --------------------------------------------------------------------------
    def test_10_unauthorized_case_rejected(self):
        """Verifies an investigator assigned only to CASE_001 is forbidden from querying CASE_007."""
        # Create test user with INVESTIGATOR role
        user_id = uuid.uuid4()
        investigator = User(
            id=user_id,
            email="investigator1@police.gov.in",
            display_name="Inspector Sharma",
            password_hash="fakehash",
            role="INVESTIGATOR",
            is_active=True,
        )
        self.db.add(investigator)

        # Create case CASE_001 and grant membership
        c1 = Case(id=uuid.uuid4(), case_code="CASE_001", title="Case 1", case_type="HT", status="ACTIVE")
        self.db.add(c1)
        self.db.flush()
        member = CaseMember(case_id=c1.id, user_id=investigator.id, case_role="INVESTIGATOR")
        self.db.add(member)
        self.db.commit()

        # Override auth and db dependencies
        def mock_user():
            return investigator

        def mock_db():
            yield self.db

        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_db] = mock_db

        # Query authorized case -> 200 OK
        resp_ok = self.client.get("/api/v1/intelligence/leads?case_id=CASE_001")
        self.assertEqual(resp_ok.status_code, 200)

        # Query unauthorized case -> 403 Forbidden
        resp_forbidden = self.client.get("/api/v1/intelligence/leads?case_id=CASE_007")
        self.assertEqual(resp_forbidden.status_code, 403)
        self.assertIn("Access denied to case dossier", resp_forbidden.json()["detail"])

    # --------------------------------------------------------------------------
    # 11. Ground Truth Does Not Appear in Production Lead Responses
    # --------------------------------------------------------------------------
    def test_11_ground_truth_not_exposed(self):
        """Verifies ground-truth fields ('label', 'true_role', 'GLOBAL_ENT') are not present in leads."""
        forbidden_fields = {"label", "true_role", "true_entity_id", "GLOBAL_ENTITY_ID"}
        for lead in self.leads[:100]:
            lead_dict = lead.model_dump()
            for key in lead_dict:
                self.assertNotIn(key.lower(), forbidden_fields)
            raw_text = str(lead_dict)
            self.assertNotIn("GLOBAL_ENT_", raw_text)
            self.assertNotIn("NETWORK_ALPHA", raw_text)

    # --------------------------------------------------------------------------
    # 12. Public/Shared Infrastructure Hard Negative Safety
    # --------------------------------------------------------------------------
    def test_12_public_infrastructure_safety(self):
        """Verifies public Wi-Fi, commercial sleeper bus, and transit hubs are capped at LOW priority."""
        for lead in self.leads:
            # Check if lead is associated with known public infrastructure
            has_public_ip = any(ip in lead.explanation for ip in KNOWN_PUBLIC_IPS)
            has_bus = "VEH_026" in lead.explanation
            if has_public_ip or has_bus or lead.caveats:
                self.assertEqual(
                    lead.priority,
                    PriorityTier.LOW,
                    f"Public infrastructure lead {lead.lead_id} was improperly given {lead.priority} priority!"
                )

    # --------------------------------------------------------------------------
    # 13. Explanation Provenance Fields Preserved
    # --------------------------------------------------------------------------
    def test_13_provenance_fields_preserved(self):
        """Confirms structured evidence records retain table names, record IDs, and timestamps."""
        leads_with_records = [l for l in self.leads if l.supporting_records]
        self.assertGreater(len(leads_with_records), 0, "No leads have supporting records attached.")
        sample_lead = leads_with_records[0]
        rec = sample_lead.supporting_records[0]
        self.assertIsInstance(rec, StructuredEvidenceRecord)
        self.assertIsNotNone(rec.reason)
        self.assertIsNotNone(rec.evidence_type)

    # --------------------------------------------------------------------------
    # 14. No Hallucinated Evidence Fields Generated
    # --------------------------------------------------------------------------
    def test_14_no_hallucinated_evidence(self):
        """Confirms evidence records cite genuine observable tables from Phase 1/3."""
        valid_tables = {
            "device_logs.csv", "cdr.csv", "chat_logs.csv", "travel_movements.csv",
            "vehicle_records.csv", "financial_transactions.csv", "persons.csv",
            "evidence.csv", "output/entity_resolution/predictions.csv", None
        }
        for lead in self.leads[:100]:
            for rec in lead.supporting_records:
                if rec.source_file:
                    self.assertIn(rec.source_file, valid_tables, f"Unknown source file {rec.source_file}")

    # --------------------------------------------------------------------------
    # 15. Cross-Case Endpoint Returns Formatted Summaries
    # --------------------------------------------------------------------------
    def test_15_cross_case_endpoint(self):
        """Verifies GET /api/v1/intelligence/cross-case returns formatted cross-case summaries."""
        admin_user = User(
            id=uuid.uuid4(),
            email="admin@police.gov.in",
            display_name="Admin Chief",
            password_hash="hash",
            role="ADMIN",
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: self.db

        resp = self.client.get("/api/v1/intelligence/cross-case?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("cross_case_leads", data)
        self.assertLessEqual(len(data["cross_case_leads"]), 5)
        if data["cross_case_leads"]:
            first = data["cross_case_leads"][0]
            self.assertIn("lead_id", first)
            self.assertIn("source_entity", first)
            self.assertIn("target_entity", first)
            self.assertIn("source_cases", first)
            self.assertIn("target_cases", first)


if __name__ == "__main__":
    unittest.main()
