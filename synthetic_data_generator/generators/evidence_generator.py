"""
Evidence Generator: Generates evidence.csv.
Models forensic case chain of custody, seized digital artifacts, UFED forensic dumps,
and legal section disclosure records.
"""

import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from config import TARGET_CONFIG

EVIDENCE_TYPES = [
    ("Digital CDR Extraction", "Telecom Lawful Intercept Disclosure", "High (Forensically Verified)"),
    ("WhatsApp Chat Export", "Cellebrite UFED Forensic Dump", "High (Forensically Verified)"),
    ("FASTag Toll Transit Log", "Highway Authority Portal API Export", "High (Official Authority Record)"),
    ("Mobile Forensic Extraction Report (UFED)", "Physical Mobile Device Acquisition", "High (Forensically Verified)"),
    ("Bank Account Ledger", "Section 91 CrPC Bank Production", "High (Certified Bank Ledger)"),
    ("ANPR Camera Capture", "Traffic Surveillance Server Export", "Medium (Automated Plate Recognition)"),
    ("Seized Physical Diary / Ledger", "Physical Search & Seizure Memo", "Medium (Physical Notebook Recovery)"),
    ("Social Media OSINT Dump", "Cyber Crime Portal OSINT Capture", "Medium (Corroborated by IP)")
]

OFFICERS = [
    "Insp. A. K. Sen", "SI Vikram Rathore", "Insp. Meenakshi Sundaram",
    "DSP R. N. Mukherjee", "SI Pradeep Yadav", "Insp. S. K. Roy"
]

class EvidenceGenerator:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_evidence_metadata(self, ground_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Produces records for evidence.csv
        """
        cases = ground_truth["cases"]
        total_evidence = TARGET_CONFIG["num_evidence_records"]

        records = []
        base_time = datetime(2025, 2, 15, 11, 0, 0)

        for e_idx in range(1, total_evidence + 1):
            c_entry = self.rng.choice(cases)
            c_id = c_entry["case_id"]

            ev_type, ext_method, reliability = self.rng.choice(EVIDENCE_TYPES)
            c_lower = c_id.lower()
            file_token = f"{ev_type.lower().replace(' ', '_')[:15]}_{self.rng.randint(10, 99)}"
            source_file = f"case_dossier_{c_lower}_{file_token}.dat"

            time_offset = timedelta(
                days=self.rng.randint(0, 180),
                hours=self.rng.randint(0, 23),
                minutes=self.rng.randint(0, 59)
            )
            ev_dt = base_time + time_offset

            # Generate synthetic sha256 hash
            raw_data = f"{c_id}_{source_file}_{ev_dt.isoformat()}_{e_idx}"
            sha256_hash = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()

            officer = self.rng.choice(OFFICERS)
            chain = f"Seized by {officer} -> District Malkhana Custody -> Forensic Science Laboratory"

            records.append({
                "evidence_id": f"EVID_{e_idx:05d}",
                "case_id": c_id,
                "evidence_type": ev_type,
                "source_file": source_file,
                "timestamp": ev_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sha256_hash": sha256_hash,
                "extraction_method": ext_method,
                "reliability": reliability,
                "chain_of_custody": chain,
            })

        records.sort(key=lambda x: x["timestamp"])
        return records
