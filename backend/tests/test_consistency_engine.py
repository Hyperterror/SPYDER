"""
Phase 6B Test Suite: Statement-Evidence Consistency Engine.
Implements 26 comprehensive unit and integration tests using standard unittest.
Covers:
- Claim Normalization (person, phone, bank account, location, temporal window)
- Claim Extraction (predicates, negation, confidence scoring)
- Evidence Matching & Provenance (CDR, chat, financial, travel, device)
- High-Bar Contradiction Safeguards (device != human, public IP, shared bus)
- Multidimensional Confidence Breakdown (4 independent dimensions)
- Consistency Status Semantics (SUPPORTED, CONTRADICTED, UNVERIFIABLE, EVIDENCE_CONFLICT)
- Non-Prejudicial Terminology Enforcement
- Deterministic Evaluation
- Multi-Case RBAC Authorization & Data Isolation
- Ground-Truth Leakage Isolation Audit
"""

import inspect
import sys
import unittest
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.intelligence.claim_extractor import ClaimExtractor
from app.intelligence.claim_models import (
    AnalyzeStatementRequest,
    ClaimPredicate,
    ConfidenceBreakdown,
    ConsistencyStatus,
    EvidenceStrength,
    StructuredClaim,
)
from app.intelligence.claim_normalizer import ClaimNormalizer
from app.intelligence.consistency_engine import ConsistencyEngine
from app.intelligence.evidence_matcher import EvidenceMatcher


class TestConsistencyEngine(unittest.TestCase):
    """Complete Phase 6B Statement-Evidence Consistency verification test suite."""

    @classmethod
    def setUpClass(cls):
        cls.normalizer = ClaimNormalizer.get_instance()
        cls.extractor = ClaimExtractor(cls.normalizer)
        cls.matcher = EvidenceMatcher.get_instance()
        cls.engine = ConsistencyEngine.get_instance()

    # -------------------------------------------------------------------------
    # 1. Claim Normalization Tests (Tests 1-6)
    # -------------------------------------------------------------------------

    def test_01_claim_normalizer_person_case_scoped(self):
        """Verifies case-scoped entity resolution for known persons."""
        pid, conf, is_ambig = self.normalizer.normalize_person_entity("Aaarav Gupta", case_id="CASE_001")
        self.assertEqual(pid, "CASE_001_PER_01")
        self.assertGreaterEqual(conf, 0.90)
        self.assertFalse(is_ambig)

    def test_02_claim_normalizer_ambiguous_alias(self):
        """Verifies ambiguous alias across cases produces ambiguity flag and lower confidence."""
        pid, conf, is_ambig = self.normalizer.normalize_person_entity("Vicky")
        self.assertTrue(is_ambig)
        self.assertLess(conf, 0.90)

    def test_03_claim_normalizer_phone_standardization(self):
        """Verifies phone number formatting to standard international string."""
        self.assertEqual(self.normalizer.normalize_phone_number("9416927215"), "+919416927215")
        self.assertEqual(self.normalizer.normalize_phone_number("+91-9416927215"), "+919416927215")
        self.assertEqual(self.normalizer.normalize_phone_number("+919416927215"), "+919416927215")

    def test_04_claim_normalizer_account_standardization(self):
        """Verifies bank account normalization."""
        self.assertEqual(self.normalizer.normalize_bank_account("acc_can_8256_028"), "ACC_CAN_8256_028")
        self.assertEqual(self.normalizer.normalize_bank_account("ACC_BAN_1645_005"), "ACC_BAN_1645_005")
        self.assertIsNone(self.normalizer.normalize_bank_account("12345678"))

    def test_05_claim_normalizer_location_canonical(self):
        """Verifies location canonicalization."""
        self.assertEqual(self.normalizer.normalize_location("kolkata"), "Kolkata")
        self.assertEqual(self.normalizer.normalize_location("delhi ncr"), "Delhi NCR")
        self.assertEqual(self.normalizer.normalize_location("anand vihar"), "Anand Vihar")

    def test_06_claim_normalizer_time_window_parsing(self):
        """Verifies ISO 8601 interval extraction with adaptive tolerance."""
        t_start, t_end, conf = self.normalizer.parse_time_window("on 2025-02-10 at 14:00")
        self.assertIsNotNone(t_start)
        self.assertIsNotNone(t_end)
        self.assertIn("2025-02-10", t_start)
        self.assertGreaterEqual(conf, 0.85)

        t_s2, t_e2, conf2 = self.normalizer.parse_time_window("on February 10, 2025")
        self.assertIn("00:00:00", t_s2)
        self.assertIn("23:59:59", t_e2)

    # -------------------------------------------------------------------------
    # 2. Claim Extraction Tests (Tests 7-12)
    # -------------------------------------------------------------------------

    def test_07_claim_extractor_called_predicate(self):
        """Verifies extraction of CALLED predicate from statement."""
        claims = self.extractor.extract_claims(
            statement_text="I called +919987342561 on February 1, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.predicate, ClaimPredicate.CALLED)
        self.assertEqual(claim.object_entity_id, "+919987342561")
        self.assertFalse(claim.negated)
        self.assertGreaterEqual(claim.claim_extraction_confidence, 0.80)

    def test_08_claim_extractor_transferred_predicate(self):
        """Verifies extraction of TRANSFERRED_TO predicate from statement."""
        claims = self.extractor.extract_claims(
            statement_text="I transferred money to ACC_CAN_8256_028.",
            case_id="CASE_002",
            subject_entity_id="CASE_002_PER_02",
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.predicate, ClaimPredicate.TRANSFERRED_TO)
        self.assertEqual(claim.object_entity_id, "ACC_CAN_8256_028")
        self.assertFalse(claim.negated)

    def test_09_claim_extractor_travel_predicate(self):
        """Verifies extraction of TRAVELLED_TO predicate from statement."""
        claims = self.extractor.extract_claims(
            statement_text="I travelled to Gwalior on 2025-02-10.",
            case_id="CASE_002",
            subject_entity_id="CASE_002_PER_04",
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.predicate, ClaimPredicate.TRAVELLED_TO)
        self.assertEqual(claim.location_id, "Gwalior")
        self.assertFalse(claim.negated)

    def test_10_claim_extractor_location_predicate(self):
        """Verifies extraction of LOCATED_AT predicate from statement."""
        claims = self.extractor.extract_claims(
            statement_text="I was in Kolkata on 2025-02-15.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.predicate, ClaimPredicate.LOCATED_AT)
        self.assertEqual(claim.location_id, "Kolkata")

    def test_11_claim_extractor_negation_detection(self):
        """Verifies negation detection in various syntactic forms."""
        claims1 = self.extractor.extract_claims(
            statement_text="I did not call +911123010000 on 2025-02-01.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        self.assertEqual(len(claims1), 1)
        self.assertTrue(claims1[0].negated)

        claims2 = self.extractor.extract_claims(
            statement_text="I never travelled to Gwalior.",
            case_id="CASE_002",
            subject_entity_id="CASE_002_PER_04",
        )
        self.assertEqual(len(claims2), 1)
        self.assertTrue(claims2[0].negated)

    def test_12_claim_extractor_unparseable_statement(self):
        """Verifies handling of statements without recognizable predicates."""
        claims = self.extractor.extract_claims(
            statement_text="The tea at the station stall was hot.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        self.assertEqual(len(claims), 1)
        self.assertIsNone(claims[0].predicate)
        self.assertLessEqual(claims[0].claim_extraction_confidence, 0.60)

    # -------------------------------------------------------------------------
    # 3. Evidence Matching & Provenance Tests (Tests 13-15)
    # -------------------------------------------------------------------------

    def test_13_evidence_matcher_cdr_match(self):
        """Verifies that CDR evidence is accurately matched to telecom claim."""
        claim = self.extractor.extract_claims(
            statement_text="I called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )[0]
        matched, conflicts, conf, caveats = self.matcher.match_evidence_for_claim(claim)
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].source_table, "cdr.csv")
        self.assertTrue(matched[0].record_id.startswith("CDR_"))
        self.assertEqual(matched[0].case_id, "CASE_001")

    def test_13b_unattributed_subject_is_not_credited_with_case_records(self):
        """
        A subject with no observed phone number must NOT be credited with any CDR
        from the case. Attributing a record the subject is not party to would
        manufacture corroboration and yield a false SUPPORTED verdict.
        """
        claim = self.extractor.extract_claims(
            statement_text="I called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_04",  # holds no observed phone in the dossier
        )[0]
        matched, conflicts, conf, caveats = self.matcher.match_evidence_for_claim(claim)
        self.assertEqual(len(matched), 0, "Unattributed subject was credited with a case CDR")
        self.assertEqual(len(conflicts), 0)
        self.assertTrue(
            any("could not be attributed" in c for c in caveats),
            f"Missing attribution caveat; got {caveats}",
        )

    def test_14_evidence_matcher_financial_match(self):
        """Verifies that financial transaction records are matched with provenance."""
        claim = self.extractor.extract_claims(
            statement_text="Transferred funds to ACC_BAN_1645_005 on 2025-02-01.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )[0]
        matched, conflicts, conf, caveats = self.matcher.match_evidence_for_claim(claim)
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].source_table, "financial_transactions.csv")
        self.assertTrue(matched[0].record_id.startswith("TXN_"))

    def test_15_evidence_matcher_travel_match(self):
        """Verifies that travel movement records are matched."""
        claim = self.extractor.extract_claims(
            statement_text="I travelled to Gwalior on 2025-02-10.",
            case_id="CASE_002",
            subject_entity_id="CASE_002_PER_04",
        )[0]
        matched, conflicts, conf, caveats = self.matcher.match_evidence_for_claim(claim)
        self.assertGreater(len(matched), 0)
        self.assertEqual(matched[0].source_table, "travel_movements.csv")
        self.assertTrue(matched[0].record_id.startswith("MOV_"))

    # -------------------------------------------------------------------------
    # 4. Consistency Engine Decision Logic & Safeguards Tests (Tests 16-22)
    # -------------------------------------------------------------------------

    def test_16_consistency_status_supported(self):
        """Verifies SUPPORTED status on confirmed claim."""
        req = AnalyzeStatementRequest(
            statement_text="I called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        self.assertGreaterEqual(resp.total_claims_extracted, 1)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.SUPPORTED)
        self.assertGreater(len(res.matched_evidence), 0)
        self.assertGreaterEqual(res.confidence.consistency_confidence, 0.70)

    def test_17_consistency_status_contradicted(self):
        """Verifies CONTRADICTED status when high bar is satisfied."""
        req = AnalyzeStatementRequest(
            statement_text="I never called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.CONTRADICTED)
        self.assertGreater(len(res.conflicting_evidence), 0)

    def test_18_high_bar_device_location_safeguard(self):
        """
        Mandatory Correction 2: A device location alone does NOT prove person's physical location.
        Must not classify as CONTRADICTED; prefers UNVERIFIABLE with explicit caveat.
        """
        req = AnalyzeStatementRequest(
            statement_text="I was in Jaipur on 2025-02-15 11:24.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertNotEqual(res.status, ConsistencyStatus.CONTRADICTED)
        self.assertEqual(res.status, ConsistencyStatus.UNVERIFIABLE)
        self.assertTrue(len(res.caveats) > 0)

    def test_19_high_bar_public_ip_safeguard(self):
        """Verifies that public IP addresses generate caveats and do not assert exclusive presence."""
        req = AnalyzeStatementRequest(
            statement_text="I was in Patna when my phone connected to 103.21.244.18.",
            case_id="CASE_003",
            subject_entity_id="CASE_003_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.UNVERIFIABLE)
        self.assertTrue(any("public/shared IP" in c or "103.21.244.18" in c for c in res.caveats))

    def test_20_high_bar_shared_bus_safeguard(self):
        """Verifies that shared commercial buses (VEH_026) produce caveats."""
        req = AnalyzeStatementRequest(
            statement_text="I saw VEH_026 passing through Anand Vihar.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.UNVERIFIABLE)

    def test_21_consistency_status_evidence_conflict(self):
        """Verifies EVIDENCE_CONFLICT when genuine competing records exist."""
        req = AnalyzeStatementRequest(
            statement_text="I was in Siliguri on 2025-04-09.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_06",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.EVIDENCE_CONFLICT)
        self.assertGreater(len(res.matched_evidence), 0)
        self.assertGreater(len(res.conflicting_evidence), 0)

    def test_22_consistency_status_unverifiable_missing(self):
        """Verifies UNVERIFIABLE status when no empirical evidence exists."""
        req = AnalyzeStatementRequest(
            statement_text="I called +919999999999 on 2025-03-01.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        res = resp.results[0]
        self.assertEqual(res.status, ConsistencyStatus.UNVERIFIABLE)
        self.assertEqual(len(res.matched_evidence), 0)
        self.assertEqual(len(res.conflicting_evidence), 0)

    # -------------------------------------------------------------------------
    # 5. Multidimensional Confidence, Provenance, & Quality Tests (Tests 23-26)
    # -------------------------------------------------------------------------

    def test_23_multidimensional_confidence_breakdown(self):
        """Verifies that all 4 confidence dimensions are explicitly exposed and bounded [0.0, 1.0]."""
        req = AnalyzeStatementRequest(
            statement_text="I called +919987342561 on February 1, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        conf = resp.results[0].confidence
        self.assertIsInstance(conf, ConfidenceBreakdown)
        self.assertTrue(0.0 <= conf.claim_extraction_confidence <= 1.0)
        self.assertTrue(0.0 <= conf.entity_match_confidence <= 1.0)
        self.assertTrue(0.0 <= conf.evidence_match_confidence <= 1.0)
        self.assertTrue(0.0 <= conf.consistency_confidence <= 1.0)

    def test_24_provenance_traceability(self):
        """Verifies that every conclusion is fully traceable to underlying source tables."""
        req = AnalyzeStatementRequest(
            statement_text="I called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        resp = self.engine.analyze_statement(req)
        record = resp.results[0].matched_evidence[0]
        self.assertEqual(record.source_table, "cdr.csv")
        self.assertNotEqual(record.record_id, "Unavailable")
        self.assertEqual(record.case_id, "CASE_001")
        self.assertNotEqual(record.evidence_type, "Unavailable")
        self.assertGreater(len(record.match_rationale), 10)

    def test_25_non_prejudicial_terminology_and_determinism(self):
        """Verifies strictly neutral terminology and deterministic repeat execution."""
        req = AnalyzeStatementRequest(
            statement_text="I never called +911123010000 on February 1, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        res1 = self.engine.analyze_statement(req).results[0]
        res2 = self.engine.analyze_statement(req).results[0]
        # Determinism
        self.assertEqual(res1.status, res2.status)
        self.assertEqual(res1.confidence.consistency_confidence, res2.confidence.consistency_confidence)
        self.assertEqual(len(res1.conflicting_evidence), len(res2.conflicting_evidence))
        self.assertEqual(res1.explanation, res2.explanation)

        # Terminology check
        text_blob = (res1.explanation + " " + res1.recommended_action + " " + " ".join(res1.caveats)).lower()
        for forbidden in ["lying", "false person", "guilty", "criminal", "mastermind", "perjurer"]:
            self.assertNotIn(forbidden, text_blob)

    def test_26_rbac_case_isolation_and_leakage_audit(self):
        """Verifies that evidence from unauthorized cases is strictly hidden and zero ground truth leaks."""
        req = AnalyzeStatementRequest(
            statement_text="I called +918528419506 on June 3, 2025.",
            case_id="CASE_001",
            subject_entity_id="CASE_001_PER_01",
        )
        # Case 001 is authorized
        resp_auth = self.engine.analyze_statement(req, authorized_cases=["CASE_001"])
        self.assertGreater(len(resp_auth.results[0].matched_evidence), 0)

        # Case 001 is NOT authorized (user only has access to CASE_002)
        resp_unauth = self.engine.analyze_statement(req, authorized_cases=["CASE_002"])
        self.assertEqual(len(resp_unauth.results[0].matched_evidence), 0)
        self.assertEqual(resp_unauth.results[0].status, ConsistencyStatus.UNVERIFIABLE)

        # Ground truth isolation
        from app.intelligence import (
            claim_extractor,
            claim_models,
            claim_normalizer,
            consistency_engine,
            consistency_explanations,
            evidence_matcher,
        )
        modules = [
            claim_extractor,
            claim_models,
            claim_normalizer,
            consistency_engine,
            consistency_explanations,
            evidence_matcher,
        ]
        forbidden_tokens = ["ground_truth.json", "true_entities.json", "GLOBAL_ENTITY_ID", "true_role", "true_roles"]
        for m in modules:
            source = inspect.getsource(m)
            for token in forbidden_tokens:
                self.assertNotIn(token, source, f"Ground-truth token '{token}' leaked into {m.__name__}!")


if __name__ == "__main__":
    unittest.main()
