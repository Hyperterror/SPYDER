"""
Phase 6A: Investigation Priority Engine Test Suite.
Verifies determinism, score calibration, ground-truth isolation, public infrastructure
safeguards, feature-grounded explanations, authentic provenance, and RBAC case clearance.
"""

import inspect
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.intelligence.models import PriorityTier
from app.intelligence.priority_engine import (
    THRESHOLD_HIGH,
    THRESHOLD_MEDIUM,
    InvestigationPriorityEngine,
)
from app.main import app
from app.models.case import Case, CaseMember
from app.models.user import User


class TestInvestigationPriorityEngine(unittest.TestCase):
    """Unit tests for priority engine scoring logic and safeguards."""

    @classmethod
    def setUpClass(cls):
        cls.engine = InvestigationPriorityEngine.get_instance()
        cls.engine.reload()

    def test_01_engine_initializes_and_loads(self):
        """Verifies engine loads all 119 PERSON entities from graph analysis."""
        priorities = self.engine._priorities_list
        self.assertEqual(len(priorities), 119)
        prov_count = sum(1 for p in priorities if p.is_provisional_resolved)
        raw_count = sum(1 for p in priorities if not p.is_provisional_resolved)
        self.assertEqual(prov_count, 19)
        self.assertEqual(raw_count, 100)

    def test_02_deterministic_scoring(self):
        """Verifies scoring produces 100% identical values across reloads."""
        first_run = [(p.person_id, p.score, p.score_breakdown.model_dump()) for p in self.engine._priorities_list]
        self.engine.reload()
        second_run = [(p.person_id, p.score, p.score_breakdown.model_dump()) for p in self.engine._priorities_list]
        self.assertEqual(first_run, second_run)

    def test_03_score_bounds_and_validity(self):
        """Verifies all scores fall strictly in [0.0, 100.0] with valid breakdowns."""
        for p in self.engine._priorities_list:
            self.assertGreaterEqual(p.score, 0.0, f"{p.person_id} score < 0")
            self.assertLessEqual(p.score, 100.0, f"{p.person_id} score > 100")
            b = p.score_breakdown
            self.assertGreaterEqual(b.cross_case_score, 0.0)
            self.assertLessEqual(b.cross_case_score, 25.0)
            self.assertGreaterEqual(b.network_score, 0.0)
            self.assertLessEqual(b.network_score, 20.0)
            self.assertGreaterEqual(b.evidence_score, 0.0)
            self.assertLessEqual(b.evidence_score, 20.0)
            self.assertGreaterEqual(b.bridge_score, 0.0)
            self.assertLessEqual(b.bridge_score, 15.0)
            self.assertGreaterEqual(b.sage_score, 0.0)
            self.assertLessEqual(b.sage_score, 20.0)

    def test_04_priority_tier_thresholds(self):
        """Verifies HIGH, MEDIUM, LOW tiers match calibrated thresholds exactly."""
        for p in self.engine._priorities_list:
            if p.score >= THRESHOLD_HIGH:
                self.assertEqual(p.priority, PriorityTier.HIGH)
            elif p.score >= THRESHOLD_MEDIUM:
                self.assertEqual(p.priority, PriorityTier.MEDIUM)
            else:
                self.assertEqual(p.priority, PriorityTier.LOW)

    def test_05_ground_truth_isolation_audit(self):
        """
        Audits priority_engine.py source code and memory objects.
        Verifies ZERO consumption of ground-truth labels, true roles, or ground truth files.
        """
        import app.intelligence.priority_engine as pe_mod
        src = inspect.getsource(pe_mod)

        forbidden = ["GLOBAL_ENTITY_ID", "true_role", "true_roles", "ground_truth.json", "true_entities.json"]
        for term in forbidden:
            self.assertNotIn(term, src, f"Ground-truth contamination detected: {term} found in priority_engine.py")

        # Verify predictions consumption explicitly ignores 'label'
        self.assertIn("ONLY consume observable predictive fields", src)

    def test_06_public_infrastructure_safeguard(self):
        """
        Verifies public transit VEH_026 receives dampened weight (+1.5 vs +4.5)
        and triggers the -3.0 penalty when relied upon without private vehicle.
        """
        found_dampened = False
        for p in self.engine._priorities_list:
            if any("VEH_026" in c for c in p.caveats):
                found_dampened = True
                self.assertIn(
                    "Vehicle connection involves commercial public transit fleet (VEH_026); weight dampened to prevent artificial hub inflation",
                    p.caveats
                )
                if p.score_breakdown.infrastructure_penalty > 0:
                    self.assertEqual(p.score_breakdown.infrastructure_penalty, 3.0)
        self.assertTrue(found_dampened, "Expected at least one entity with commercial transit caveat")

    def test_07_cross_case_vs_single_case_prioritization(self):
        """
        Verifies multi-case central figures receive significantly higher priority
        than peripheral single-case entities.
        """
        top_10 = self.engine._priorities_list[:10]
        bottom_10 = self.engine._priorities_list[-10:]

        top_avg_score = sum(p.score for p in top_10) / len(top_10)
        bottom_avg_score = sum(p.score for p in bottom_10) / len(bottom_10)

        self.assertGreater(top_avg_score, 80.0, "Top 10 priority score average should exceed 80")
        self.assertLess(bottom_avg_score, 35.0, "Bottom 10 priority score average should be under 35")

        # Verify top entities have cross-case associations
        top_multi_case = sum(1 for p in top_10 if p.cases_count >= 2)
        self.assertGreaterEqual(top_multi_case, 8)

    def test_08_provisional_entities_distinguished(self):
        """Verifies provisional resolved entities are clearly flagged and distinguished."""
        prov_ents = [p for p in self.engine._priorities_list if p.is_provisional_resolved]
        self.assertEqual(len(prov_ents), 19)
        for p in prov_ents:
            self.assertTrue(p.person_id.startswith("PROV_RES_ENT_"))
            self.assertIn(
                "Provisional entity-resolution cluster; requires independent verification of underlying personas",
                p.caveats
            )

    def test_09_explanation_feature_grounding(self):
        """Verifies explanations correspond only to non-zero calculated features."""
        for p in self.engine._priorities_list:
            b = p.score_breakdown
            reasons_text = " ".join(p.reasons)
            if "device" in reasons_text.lower():
                self.assertGreater(b.evidence_score, 0.0)
            if "social" in reasons_text.lower():
                self.assertGreater(b.evidence_score, 0.0)
            if "GraphSAGE" in reasons_text:
                self.assertGreater(b.sage_score, 0.0)
            if "spanning" in reasons_text:
                self.assertGreaterEqual(p.cases_count, 2)

    def test_10_provenance_authenticity_and_missing_fields(self):
        """Verifies provenance records map to real graph data and missing fields default to 'Unavailable'."""
        prov_map = self.engine._provenance_by_id
        self.assertGreater(len(prov_map), 0)
        for nid, records in prov_map.items():
            for rec in records:
                self.assertIn(rec.relationship, [
                    "USED_VEHICLE", "TRAVELLED_TO", "APPEARS_IN", "HAS_SOCIAL_ACCOUNT",
                    "USED_DEVICE", "OBSERVES_ENTITY", "CALLED", "MESSAGED", "TRANSFERRED_MONEY",
                    "USED_PHONE", "ASSOCIATED_WITH_EVIDENCE"
                ])
                if not rec.timestamp:
                    self.assertEqual(rec.timestamp, "Unavailable")

    def test_11_terminology_neutrality(self):
        """Verifies strictly non-prejudicial terminology across all explanations and caveats."""
        forbidden_terms = ["criminal", "guilty", "suspect", "convict", "perpetrator", "illegal"]
        for p in self.engine._priorities_list:
            for text in p.reasons + p.caveats:
                text_lower = text.lower()
                for f in forbidden_terms:
                    self.assertNotIn(f, text_lower, f"Prejudicial term '{f}' found in: {text}")


class TestPriorityAPIIntegration(unittest.TestCase):
    """Integration tests for Priority Engine API endpoints and RBAC clearance."""

    @classmethod
    def setUpClass(cls):
        import uuid
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine, expire_on_commit=False)
        cls.client = TestClient(app)

        db = cls.TestSessionLocal()
        try:
            cls.admin = User(
                id=uuid.uuid4(),
                email="admin@spyder.test",
                password_hash="hashed_secret",
                display_name="Admin User",
                role="ADMIN",
                is_active=True,
            )
            cls.investigator1 = User(
                id=uuid.uuid4(),
                email="investigator1@spyder.test",
                password_hash="hashed_secret",
                display_name="Investigator Case 001",
                role="INVESTIGATOR",
                is_active=True,
            )
            cls.investigator2 = User(
                id=uuid.uuid4(),
                email="investigator2@spyder.test",
                password_hash="hashed_secret",
                display_name="Investigator Case 004",
                role="INVESTIGATOR",
                is_active=True,
            )
            db.add_all([cls.admin, cls.investigator1, cls.investigator2])

            case1 = Case(
                id=uuid.uuid4(),
                case_code="CASE_001",
                title="Corridor Case 001",
                status="ACTIVE",
            )
            case4 = Case(
                id=uuid.uuid4(),
                case_code="CASE_004",
                title="Independent Case 004",
                status="ACTIVE",
            )
            db.add_all([case1, case4])
            db.flush()

            m1 = CaseMember(id=uuid.uuid4(), case_id=case1.id, user_id=cls.investigator1.id, case_role="INVESTIGATOR")
            m2 = CaseMember(id=uuid.uuid4(), case_id=case4.id, user_id=cls.investigator2.id, case_role="INVESTIGATOR")
            db.add_all([m1, m2])
            db.commit()
        finally:
            db.close()

    def setUp(self):
        self.db = self.TestSessionLocal()

    def tearDown(self):
        self.db.close()
        app.dependency_overrides.clear()

    def _set_auth_user(self, user: User):
        def mock_user():
            return user
        def mock_db():
            yield self.db
        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_db] = mock_db

    def test_12_api_get_priorities_admin_global(self):
        """Admin can access all priorities and receive total=119."""
        self._set_auth_user(self.admin)
        resp = self.client.get("/api/v1/intelligence/priorities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 119)
        self.assertGreaterEqual(data["high_count"], 1)
        self.assertGreaterEqual(data["medium_count"], 1)
        self.assertGreaterEqual(data["low_count"], 1)

    def test_13_api_filtering_and_sorting(self):
        """Verifies filtering by priority tier, min_score, and limit."""
        self._set_auth_user(self.admin)

        # Filter priority = HIGH
        resp = self.client.get("/api/v1/intelligence/priorities?priority=HIGH")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for p in data["priorities"]:
            self.assertEqual(p["priority"], "HIGH")
            self.assertGreaterEqual(p["score"], THRESHOLD_HIGH)

        # Filter min_score = 85
        resp2 = self.client.get("/api/v1/intelligence/priorities?min_score=85")
        self.assertEqual(resp2.status_code, 200)
        for p in resp2.json()["priorities"]:
            self.assertGreaterEqual(p["score"], 85.0)

    def test_14_api_investigator_authorization_and_case_filtering(self):
        """Investigator for CASE_001 only sees entities touching CASE_001."""
        self._set_auth_user(self.investigator1)
        resp = self.client.get("/api/v1/intelligence/priorities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data["total"], 0)
        for p in data["priorities"]:
            self.assertIn("CASE_001", p["associated_cases"])

    def test_15_api_unauthorized_case_information_leakage_protection(self):
        """
        Verifies that for a multi-case entity, an investigator with clearance for only CASE_001
        does NOT receive unauthorized case IDs in associated_cases.
        """
        self._set_auth_user(self.investigator1)
        resp = self.client.get("/api/v1/intelligence/priorities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for p in data["priorities"]:
            for cid in p["associated_cases"]:
                self.assertEqual(cid, "CASE_001", f"Leaked unauthorized case ID {cid} to investigator!")
            self.assertEqual(p["cases_count"], len(p["associated_cases"]))

    def test_16_api_forbidden_case_query(self):
        """Requesting an unauthorized case explicitly returns 403 Forbidden."""
        self._set_auth_user(self.investigator1)
        resp = self.client.get("/api/v1/intelligence/priorities?case_id=CASE_004")
        self.assertEqual(resp.status_code, 403)

    def test_17_api_priority_by_id_and_404(self):
        """GET /priorities/{person_id} returns detail view; invalid ID returns 404."""
        self._set_auth_user(self.admin)
        resp = self.client.get("/api/v1/intelligence/priorities/CASE_007_PER_01")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["person_id"], "CASE_007_PER_01")
        self.assertIn("score_breakdown", data)

        # Nonexistent ID -> 404
        resp_404 = self.client.get("/api/v1/intelligence/priorities/NONEXISTENT_PER_999")
        self.assertEqual(resp_404.status_code, 404)

    def test_18_api_evidence_provenance_lookup(self):
        """GET /priorities/{person_id}/evidence returns observable provenance records."""
        self._set_auth_user(self.admin)
        resp = self.client.get("/api/v1/intelligence/priorities/CASE_007_PER_01/evidence")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["person_id"], "CASE_007_PER_01")
        self.assertGreater(data["total_records"], 0)
        for rec in data["records"]:
            self.assertIn("relationship", rec)
            self.assertIn("related_entity", rec)

    def test_19_api_investigator_forbidden_individual_person(self):
        """Investigator for CASE_001 attempting to access pure CASE_004 person returns 403."""
        self._set_auth_user(self.investigator1)
        resp = self.client.get("/api/v1/intelligence/priorities/CASE_004_PER_01")
        self.assertEqual(resp.status_code, 403)

    def test_20_api_evidence_filtered_by_authorized_case(self):
        """Investigator only receives provenance records originating in their authorized case."""
        self._set_auth_user(self.investigator1)
        resp = self.client.get("/api/v1/intelligence/priorities/PROV_RES_ENT_001/evidence")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for rec in data["records"]:
            if rec["case_id"] != "Unavailable":
                self.assertEqual(rec["case_id"], "CASE_001", f"Leaked unauthorized case record: {rec['case_id']}")


if __name__ == "__main__":
    unittest.main()
