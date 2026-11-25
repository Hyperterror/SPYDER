"""
Validation and Test Suite for Synthetic Criminal Network Data Generator.
Verifies file existence, column schemas, referential integrity, record count targets,
ground-truth isolation, cross-case entity ratios, hard negatives, and 100% reproducibility.
"""

import csv
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import sys
TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from config import DEFAULT_SEED, EVIDENCE_DIR, GROUND_TRUTH_DIR, NETWORK_CLUSTERS
from generate_dataset import run_pipeline
from derive_organizations import derive as derive_organizations, write_tables as write_org_tables

EXPECTED_EVIDENCE_FILES = [
    "cases.csv", "persons.csv", "victims.csv", "cdr.csv", "chat_logs.csv",
    "travel_movements.csv", "vehicle_records.csv", "device_logs.csv",
    "financial_transactions.csv", "social_media.csv", "evidence.csv",
    "organizations.csv", "org_affiliations.csv"
]

# Files written by run_pipeline() itself. The two organization tables are derived
# from the generated evidence, so they are excluded from generation-only checks.
GENERATED_EVIDENCE_FILES = EXPECTED_EVIDENCE_FILES[:-2]

EXPECTED_GROUND_TRUTH_FILES = [
    "ground_truth.json", "true_entities.json", "true_relationships.json",
    "true_case_links.json", "true_roles.json"
]

REQUIRED_SCHEMAS = {
    "cases.csv": [
        "case_id", "case_type", "reported_date", "incident_date",
        "origin_location", "destination_location", "status", "agency", "priority"
    ],
    "persons.csv": [
        "person_id", "name", "alias", "age_group", "role",
        "phone_id", "device_id", "address", "occupation", "case_id"
    ],
    "victims.csv": [
        "victim_id", "case_id", "age_group", "reported_location",
        "last_known_location", "recruitment_channel", "status", "sensitive_flag"
    ],
    "cdr.csv": [
        "cdr_id", "timestamp", "caller", "receiver",
        "duration_sec", "call_type", "cell_tower", "case_id"
    ],
    "chat_logs.csv": [
        "message_id", "timestamp", "sender", "receiver",
        "message_text", "platform", "language", "case_id"
    ],
    "travel_movements.csv": [
        "movement_id", "person_id", "vehicle_id", "timestamp",
        "source", "destination", "transport_mode", "evidence_source", "case_id"
    ],
    "vehicle_records.csv": [
        "vehicle_id", "registration_no", "vehicle_type", "owner_id",
        "driver_id", "timestamp", "location", "case_id"
    ],
    "device_logs.csv": [
        "device_id", "imei", "phone_id", "ip_address",
        "timestamp", "location", "case_id"
    ],
    "financial_transactions.csv": [
        "transaction_id", "timestamp", "sender_account", "receiver_account",
        "amount", "transaction_type", "reference", "case_id"
    ],
    "social_media.csv": [
        "account_id", "username", "platform", "linked_phone",
        "linked_email", "created_date", "location", "case_id"
    ],
    "evidence.csv": [
        "evidence_id", "case_id", "evidence_type", "source_file",
        "timestamp", "sha256_hash", "extraction_method", "reliability", "chain_of_custody"
    ],
    "organizations.csv": [
        "org_id", "name", "org_type", "sector",
        "registered_office_city", "registration_no", "case_id"
    ],
    "org_affiliations.csv": [
        "affiliation_id", "org_id", "entity_id", "entity_type", "relation",
        "since_date", "source_table", "source_record_id", "case_id"
    ]
}

class TestDatasetGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate into an isolated temporary directory. Regenerating in place would
        # overwrite the frozen evidence CSVs that every downstream artifact (entity
        # resolution, knowledge graph, GraphSAGE) is keyed to.
        cls._tmp_dir = Path(tempfile.mkdtemp(prefix="spyder_dataset_"))
        temp_evidence = cls._tmp_dir / "evidence_dataset"
        temp_ground_truth = cls._tmp_dir / "ground_truth"

        run_pipeline(seed=DEFAULT_SEED, evidence_dir=temp_evidence, ground_truth_dir=temp_ground_truth)
        # Organization tables are derived from the evidence, not generated with it,
        # so they must be rebuilt after any (re)generation to stay consistent.
        write_org_tables(*derive_organizations(temp_evidence), evidence_dir=temp_evidence)

        # Point the module-level constants at the generated fixture for the rest of the suite
        module_globals = globals()
        module_globals["EVIDENCE_DIR"] = temp_evidence
        module_globals["GROUND_TRUTH_DIR"] = temp_ground_truth

        cls.addClassCleanup(shutil.rmtree, cls._tmp_dir, True)

    def test_expected_files_exist(self):
        """Verifies that every evidence CSV (including derived organization tables) exists."""
        for fname in EXPECTED_EVIDENCE_FILES:
            fpath = EVIDENCE_DIR / fname
            self.assertTrue(fpath.exists(), f"Evidence file missing: {fname}")
            self.assertGreater(fpath.stat().st_size, 0, f"Evidence file empty: {fname}")

        for gname in EXPECTED_GROUND_TRUTH_FILES:
            gpath = GROUND_TRUTH_DIR / gname
            self.assertTrue(gpath.exists(), f"Ground truth file missing: {gname}")
            self.assertGreater(gpath.stat().st_size, 0, f"Ground truth file empty: {gname}")

    def test_column_schemas(self):
        """Verifies exact column schema compliance for all 11 evidence tables."""
        for fname, expected_cols in REQUIRED_SCHEMAS.items():
            fpath = EVIDENCE_DIR / fname
            with open(fpath, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(header, expected_cols, f"Schema mismatch in {fname}")

    def test_primary_key_uniqueness(self):
        """Verifies that primary key IDs are strictly unique within their respective tables."""
        pk_map = {
            "cases.csv": "case_id",
            "persons.csv": "person_id",
            "victims.csv": "victim_id",
            "cdr.csv": "cdr_id",
            "chat_logs.csv": "message_id",
            "travel_movements.csv": "movement_id",
            "financial_transactions.csv": "transaction_id",
            "social_media.csv": "account_id",
            "evidence.csv": "evidence_id"
        }

        for fname, pk_col in pk_map.items():
            fpath = EVIDENCE_DIR / fname
            with open(fpath, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen = set()
                for row in reader:
                    val = row[pk_col]
                    self.assertNotIn(val, seen, f"Duplicate primary key {val} in {fname}")
                    seen.add(val)

    def test_foreign_key_and_case_linkage(self):
        """Verifies all evidence records reference valid cases in cases.csv."""
        with open(EVIDENCE_DIR / "cases.csv", mode="r", encoding="utf-8") as f:
            valid_cases = {row["case_id"] for row in csv.DictReader(f)}

        self.assertEqual(len(valid_cases), 10, "Expected exactly 10 cases")

        tables_with_case_id = [f for f in EXPECTED_EVIDENCE_FILES]
        for fname in tables_with_case_id:
            with open(EVIDENCE_DIR / fname, mode="r", encoding="utf-8") as f:
                for idx, row in enumerate(csv.DictReader(f)):
                    self.assertIn(
                        row["case_id"], valid_cases,
                        f"Invalid case_id '{row['case_id']}' in {fname} at row {idx+1}"
                    )

    def test_timestamp_validity(self):
        """Verifies that timestamps are properly formatted and parseable."""
        tables_with_ts = {
            "cases.csv": ["reported_date", "incident_date"],
            "cdr.csv": ["timestamp"],
            "chat_logs.csv": ["timestamp"],
            "travel_movements.csv": ["timestamp"],
            "vehicle_records.csv": ["timestamp"],
            "device_logs.csv": ["timestamp"],
            "financial_transactions.csv": ["timestamp"],
            "social_media.csv": ["created_date"],
            "evidence.csv": ["timestamp"],
        }

        for fname, ts_cols in tables_with_ts.items():
            with open(EVIDENCE_DIR / fname, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    for col in ts_cols:
                        ts_val = row[col]
                        if not ts_val:
                            continue
                        parsed = False
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                datetime.strptime(ts_val, fmt)
                                parsed = True
                                break
                            except ValueError:
                                pass
                        self.assertTrue(parsed, f"Invalid timestamp format '{ts_val}' in {fname}:{col}")

    def test_target_record_counts(self):
        """Verifies that generated evidence record counts align with target ranges."""
        def count_rows(fname):
            with open(EVIDENCE_DIR / fname, mode="r", encoding="utf-8") as f:
                return sum(1 for _ in csv.DictReader(f))

        counts = {fname: count_rows(fname) for fname in EXPECTED_EVIDENCE_FILES}

        self.assertEqual(counts["cases.csv"], 10)
        self.assertTrue(90 <= counts["persons.csv"] <= 120, f"Persons count {counts['persons.csv']} out of range")
        self.assertTrue(20 <= counts["victims.csv"] <= 30, f"Victims count {counts['victims.csv']} out of range")
        self.assertTrue(1800 <= counts["cdr.csv"] <= 2200, f"CDRs count {counts['cdr.csv']} out of range")
        self.assertTrue(900 <= counts["chat_logs.csv"] <= 1100, f"Chats count {counts['chat_logs.csv']} out of range")
        self.assertTrue(450 <= counts["travel_movements.csv"] <= 550, f"Movements count {counts['travel_movements.csv']} out of range")
        self.assertTrue(180 <= counts["vehicle_records.csv"] <= 220, f"Vehicles count {counts['vehicle_records.csv']} out of range")
        self.assertTrue(900 <= counts["financial_transactions.csv"] <= 1100, f"Transactions count {counts['financial_transactions.csv']} out of range")
        self.assertTrue(90 <= counts["social_media.csv"] <= 110, f"Social count {counts['social_media.csv']} out of range")
        self.assertTrue(180 <= counts["evidence.csv"] <= 220, f"Evidence count {counts['evidence.csv']} out of range")

    def test_ground_truth_isolation(self):
        """
        STRICT ISOLATION TEST:
        Verifies that no global entity IDs (e.g. GLOBAL_ENT_xxx, GLOBAL_VIC_xxx)
        or ground-truth file names leak into the evidence CSVs.
        """
        for fname in EXPECTED_EVIDENCE_FILES:
            fpath = EVIDENCE_DIR / fname
            with open(fpath, mode="r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("GLOBAL_ENT_", content, f"Leak detected in {fname}: GLOBAL_ENT_ found!")
                self.assertNotIn("GLOBAL_VIC_", content, f"Leak detected in {fname}: GLOBAL_VIC_ found!")
                self.assertNotIn("ground_truth", content, f"Leak detected in {fname}: ground_truth keyword found!")

    def test_cross_case_entities_ratio(self):
        """Verifies that between 20% and 35% of latent entities appear in multiple cases."""
        with open(GROUND_TRUTH_DIR / "true_entities.json", mode="r", encoding="utf-8") as f:
            entities = json.load(f)

        multi_case_entities = [e for e in entities if len(e["case_memberships"]) > 1]
        ratio = len(multi_case_entities) / len(entities)
        self.assertTrue(
            0.20 <= ratio <= 0.35,
            f"Cross-case entity ratio {ratio:.2%} is outside target [20%, 35%]"
        )

    def test_hard_negatives_presence(self):
        """Verifies that hard negative entities are present in ground truth and evidence."""
        with open(GROUND_TRUTH_DIR / "ground_truth.json", mode="r", encoding="utf-8") as f:
            gt = json.load(f)

        hn_registry = gt.get("hard_negatives", [])
        self.assertGreaterEqual(len(hn_registry), 4, "Expected at least 4 hard negative entities")

        # Verify distinct global IDs sharing surface attributes
        groups = {}
        for hn in hn_registry:
            groups.setdefault(hn["hard_negative_group"], []).append(hn)

        for grp_name, members in groups.items():
            self.assertGreaterEqual(len(members), 2, f"Group {grp_name} has fewer than 2 entities")
            global_ids = {m["global_id"] for m in members}
            self.assertEqual(len(global_ids), len(members), f"Entities in {grp_name} must have distinct global IDs")

    def test_independent_cases_unrelated(self):
        """Verifies that independent cases have 0 links to syndicates in true_case_links.json."""
        with open(GROUND_TRUTH_DIR / "true_case_links.json", mode="r", encoding="utf-8") as f:
            links = json.load(f)

        indep_cases = set(NETWORK_CLUSTERS["INDEPENDENT"]["cases"])

        for link in links:
            c_a, c_b = link["case_a"], link["case_b"]
            if c_a in indep_cases or c_b in indep_cases:
                self.assertFalse(
                    link["is_linked"],
                    f"Independent case pair ({c_a}, {c_b}) was incorrectly marked as linked!"
                )
                self.assertEqual(
                    link["shared_global_entities_count"], 0,
                    f"Independent case pair ({c_a}, {c_b}) shares entities in error!"
                )

    def test_reproducibility(self):
        """Verifies that two runs with the same seed generate bit-for-bit identical outputs."""
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
            ev1 = Path(temp_dir1) / "evidence"
            gt1 = Path(temp_dir1) / "gt"
            ev2 = Path(temp_dir2) / "evidence"
            gt2 = Path(temp_dir2) / "gt"

            run_pipeline(seed=777, evidence_dir=ev1, ground_truth_dir=gt1)
            run_pipeline(seed=777, evidence_dir=ev2, ground_truth_dir=gt2)

            for fname in GENERATED_EVIDENCE_FILES:
                h1 = hashlib.sha256((ev1 / fname).read_bytes()).hexdigest()
                h2 = hashlib.sha256((ev2 / fname).read_bytes()).hexdigest()
                self.assertEqual(h1, h2, f"Evidence file {fname} is not reproducible with fixed seed!")

            for gname in EXPECTED_GROUND_TRUTH_FILES:
                h1 = hashlib.sha256((gt1 / gname).read_bytes()).hexdigest()
                h2 = hashlib.sha256((gt2 / gname).read_bytes()).hexdigest()
                self.assertEqual(h1, h2, f"Ground truth file {gname} is not reproducible with fixed seed!")

    def test_role_leakage_prevention(self):
        """
        STRICT ROLE LEAKAGE AUDIT TEST:
        Fails if canonical true_roles or direct equivalents appear as a direct label
        in evidence columns (e.g. role or occupation in persons.csv).
        """
        FORBIDDEN_LABELS = [
            "coordinator", "recruiter", "transporter", "financier",
            "document_facilitator", "local_associate", "mastermind",
            "syndicate head", "hawala operator"
        ]
        with open(EVIDENCE_DIR / "persons.csv", mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                r_val = row["role"].lower().strip()
                o_val = row["occupation"].lower().strip()
                for label in FORBIDDEN_LABELS:
                    self.assertNotEqual(
                        r_val, label,
                        f"CRITICAL ROLE LEAK: Forbidden canonical role '{label}' exposed in persons.csv role column!"
                    )
                    self.assertNotIn(
                        label, o_val,
                        f"CRITICAL ROLE LEAK: Forbidden role keyword '{label}' found in occupation '{row['occupation']}'!"
                    )

    def test_device_logs_presence_and_structure(self):
        """
        DEVICE DATA AUDIT TEST:
        Verifies device_logs.csv exists, has records, and adheres to schema:
        device_id, imei, phone_id, ip_address, timestamp, location, case_id.
        Verifies valid 15-digit IMEIs and presence of both shared and private IPs.
        """
        dev_file = EVIDENCE_DIR / "device_logs.csv"
        self.assertTrue(dev_file.exists(), "device_logs.csv missing!")
        
        with open(dev_file, mode="r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        
        self.assertGreaterEqual(len(rows), 300, f"Expected >= 300 device logs, found {len(rows)}")
        
        # Check field structure and values
        ip_counts = {}
        for row in rows:
            self.assertTrue(row["device_id"].startswith("DEV_"), f"Invalid device_id: {row['device_id']}")
            self.assertTrue(row["imei"].isdigit() and len(row["imei"]) == 15, f"Invalid 15-digit IMEI: {row['imei']}")
            self.assertTrue(row["phone_id"].startswith("PH_"), f"Invalid phone_id: {row['phone_id']}")
            self.assertTrue(row["case_id"].startswith("CASE_"), f"Invalid case_id: {row['case_id']}")
            ip = row["ip_address"]
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        # Confirm that shared IPs exist (appearing multiple times) as well as private dynamic IPs
        shared_ips = [ip for ip, cnt in ip_counts.items() if cnt > 10]
        self.assertGreaterEqual(len(shared_ips), 1, "Expected at least 1 shared infrastructure IP in device logs")

    def test_cross_case_identifier_overlap_distributions(self):
        """
        IDENTIFIER OVERLAP AUDIT TEST:
        Audits cross-case overlap for:
        - phone numbers
        - IMEI/device IDs
        - vehicle registrations
        - bank accounts
        - IP addresses
        Verifies that:
        1. Connected syndicate cases have strong true overlaps
        2. Independent cases remain uncoupled (at most coincidental shared hotlines/shared public IPs)
        3. A shared IP alone does not imply identity
        """
        from collections import defaultdict
        
        # Helper to collect identifiers per case
        def collect_by_case(fname, col_names):
            case_map = defaultdict(set)
            with open(EVIDENCE_DIR / fname, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row["case_id"]
                    for col in col_names:
                        val = row[col].strip()
                        if val:
                            case_map[cid].add(val)
            return case_map

        phones_by_case = collect_by_case("cdr.csv", ["caller", "receiver"])
        imeis_by_case = collect_by_case("device_logs.csv", ["imei"])
        vehicles_by_case = collect_by_case("vehicle_records.csv", ["registration_no"])
        accounts_by_case = collect_by_case("financial_transactions.csv", ["sender_account", "receiver_account"])
        ips_by_case = collect_by_case("device_logs.csv", ["ip_address"])

        # 1. Syndicate Alpha pair (CASE_001 and CASE_003) must show strong, informative overlap
        c1_c3_phones = len(phones_by_case["CASE_001"].intersection(phones_by_case["CASE_003"]))
        c1_c3_imeis = len(imeis_by_case["CASE_001"].intersection(imeis_by_case["CASE_003"]))
        c1_c3_vehicles = len(vehicles_by_case["CASE_001"].intersection(vehicles_by_case["CASE_003"]))
        c1_c3_accounts = len(accounts_by_case["CASE_001"].intersection(accounts_by_case["CASE_003"]))

        self.assertGreater(c1_c3_phones, 0, "Syndicate Alpha must share phone numbers across cases")
        self.assertLessEqual(c1_c3_phones, 20, f"Phone overlap {c1_c3_phones} is unnaturally overwhelming")
        self.assertGreater(c1_c3_imeis, 0, "Syndicate Alpha must share IMEIs")
        self.assertGreater(c1_c3_vehicles, 0, "Syndicate Alpha must share vehicle observations")
        self.assertGreater(c1_c3_accounts, 0, "Syndicate Alpha must share bank accounts")

        # 2. Independent pair (CASE_001 and CASE_004) must NOT share syndicate entities
        c1_c4_vehicles = len(vehicles_by_case["CASE_001"].intersection(vehicles_by_case["CASE_004"]))
        self.assertEqual(c1_c4_vehicles, 0, "Independent cases must have 0 shared syndicate vehicles")

        c1_c4_imeis = len(imeis_by_case["CASE_001"].intersection(imeis_by_case["CASE_004"]))
        self.assertLessEqual(c1_c4_imeis, 1, "Independent cases should only share at most coincidental shared terminal")

        c1_c4_accounts = len(accounts_by_case["CASE_001"].intersection(accounts_by_case["CASE_004"]))
        self.assertLessEqual(c1_c4_accounts, 1, "Independent cases should only share at most coincidental rail portal account")

        # 3. Verify that shared IPs exist across independent cases (shared public infrastructure)
        c1_c4_ips = len(ips_by_case["CASE_001"].intersection(ips_by_case["CASE_004"]))
        self.assertGreater(c1_c4_ips, 0, "Shared infrastructure IPs should appear across cases without implying identity")


class TestOrganizationDerivation(unittest.TestCase):
    """Organizations are derived from the frozen evidence, deterministically."""

    @classmethod
    def setUpClass(cls):
        # Self-contained fixture: derive from a freshly generated isolated dataset so
        # this suite never depends on (or mutates) the frozen evidence directory.
        cls._tmp_dir = Path(tempfile.mkdtemp(prefix="spyder_orgs_"))
        temp_evidence = cls._tmp_dir / "evidence_dataset"
        temp_ground_truth = cls._tmp_dir / "ground_truth"
        run_pipeline(seed=DEFAULT_SEED, evidence_dir=temp_evidence, ground_truth_dir=temp_ground_truth)

        cls.evidence_dir = temp_evidence
        cls.organizations, cls.affiliations = derive_organizations(temp_evidence)
        cls.persons = cls._ids("persons.csv", "person_id")
        cls.cases = cls._ids("cases.csv", "case_id")
        cls.evidence = cls._ids("evidence.csv", "evidence_id")

        cls.addClassCleanup(shutil.rmtree, cls._tmp_dir, True)

    @classmethod
    def _ids(cls, filename, column):
        with open(cls.evidence_dir / filename, mode="r", encoding="utf-8") as f:
            return {row[column] for row in csv.DictReader(f)}

    def test_01_organizations_present(self):
        self.assertGreater(len(self.organizations), 0, "No organizations were derived")
        org_types = {o["org_type"] for o in self.organizations}
        for expected in (
            "PLACEMENT_AGENCY",
            "TRAVEL_AGENCY",
            "LAW_ENFORCEMENT_AGENCY",
            "FORENSIC_LABORATORY",
        ):
            self.assertIn(expected, org_types, f"Organization type {expected} not derived")

    def test_02_deterministic_and_idempotent(self):
        again_orgs, again_affs = derive_organizations(self.evidence_dir)
        self.assertEqual(self.organizations, again_orgs, "Organization derivation is not deterministic")
        self.assertEqual(self.affiliations, again_affs, "Affiliation derivation is not deterministic")

    def test_03_affiliations_reference_real_entities(self):
        valid = {"PERSON": self.persons, "CASE": self.cases, "EVIDENCE": self.evidence}
        org_ids = {o["org_id"] for o in self.organizations}
        for aff in self.affiliations:
            self.assertIn(aff["org_id"], org_ids, f"Unknown org {aff['org_id']}")
            self.assertIn(aff["entity_id"], valid[aff["entity_type"]],
                          f"Affiliation points at unknown {aff['entity_type']} {aff['entity_id']}")
            self.assertTrue(aff["source_table"])
            self.assertTrue(aff["source_record_id"])

    def test_04_no_ground_truth_leakage(self):
        forbidden = ["GLOBAL_ENT", "GLOBAL_ENTITY", "syndicate", "mastermind"]
        for org in self.organizations:
            blob = " ".join(str(v) for v in org.values()).lower()
            for token in forbidden:
                self.assertNotIn(token.lower(), blob, f"Ground truth token {token} leaked into an organization")

    def test_05_organization_ids_are_unique(self):
        org_ids = [o["org_id"] for o in self.organizations]
        self.assertEqual(len(org_ids), len(set(org_ids)), "Duplicate org_id values derived")


if __name__ == "__main__":
    unittest.main()
