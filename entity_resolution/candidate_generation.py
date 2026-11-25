"""
Candidate Generation and Evidence Enrichment for Entity Resolution.
Constructs observable multi-modal profiles for each person observation and generates
plausible cross-case candidate pairs using conservative blocking rules.
"""

import csv
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional

from entity_resolution.config import EVIDENCE_DIR
from entity_resolution.normalize import (
    normalize_name, normalize_alias, normalize_phone, normalize_imei,
    normalize_vehicle_reg, normalize_account_id, normalize_ip,
    levenshtein_similarity, token_jaccard_similarity
)

class CandidateGenerator:
    def __init__(self, evidence_dir: Path = EVIDENCE_DIR, ground_truth_dir: Optional[Path] = None):
        self.evidence_dir = Path(evidence_dir)
        # Note: ground_truth_dir is intentionally ignored in production candidate generation
        # to enforce strict observable-evidence isolation. Evaluation label builders inject
        # benchmark hard negatives solely inside entity_resolution/pair_generation.py.
        self._unused_gt_dir = ground_truth_dir
        self.profiles: Dict[str, Dict[str, Any]] = {}

    def load_and_enrich_evidence(self) -> Dict[str, Dict[str, Any]]:
        """
        Enriches observational person records from persons.csv with observable signals
        from all other evidence tables (without using any hidden ground-truth fields).
        """
        # 1. Load persons.csv
        persons_path = self.evidence_dir / "persons.csv"
        with open(persons_path, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = row["person_id"]
                norm_name = normalize_name(row["name"])
                norm_alias = normalize_alias(row["alias"])
                self.profiles[pid] = {
                    "person_id": pid,
                    "case_id": row["case_id"],
                    "raw_name": row["name"],
                    "norm_name": norm_name["clean"],
                    "name_tokens": norm_name["tokens"],
                    "name_initials": norm_name["initials"],
                    "raw_alias": row["alias"],
                    "norm_alias": norm_alias["clean"],
                    "alias_tokens": norm_alias["tokens"],
                    "age_group": row["age_group"],
                    "role": row["role"],  # Procedural police role (Suspect, Witness, etc.)
                    "occupation": row["occupation"],
                    "address": row["address"],
                    "phone_id": row["phone_id"],
                    "device_id": row["device_id"],
                    "phones": set(),
                    "phone_last10s": set(),
                    "imeis": set(),
                    "ip_addresses": set(),
                    "locations": set(),
                    "vehicles": set(),
                    "bank_accounts": set(),
                    "social_handles": set(),
                    "emails": set(),
                    "contacts": set(),
                }
                if row.get("address"):
                    parts = row["address"].split(",")
                    if parts:
                        self.profiles[pid]["locations"].add(parts[-1].strip())

        # 2. Enrich with device_logs.csv
        device_logs_path = self.evidence_dir / "device_logs.csv"
        if device_logs_path.exists():
            with open(device_logs_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    dev_id = row["device_id"]
                    phone_id = row["phone_id"]
                    imei = normalize_imei(row["imei"])["clean"]
                    ip = normalize_ip(row["ip_address"])["clean"]
                    loc = row["location"]
                    
                    # Associate with any profile sharing this device_id or phone_id
                    for pid, p in self.profiles.items():
                        if p["device_id"] == dev_id or p["phone_id"] == phone_id:
                            if imei:
                                p["imeis"].add(imei)
                            if ip:
                                p["ip_addresses"].add(ip)
                            if loc:
                                p["locations"].add(loc)

        # 3. Enrich with vehicle_records.csv
        vehicle_path = self.evidence_dir / "vehicle_records.csv"
        if vehicle_path.exists():
            with open(vehicle_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    v_reg = normalize_vehicle_reg(row["registration_no"])["clean"]
                    owner_id = row["owner_id"]
                    driver_id = row["driver_id"]
                    if owner_id in self.profiles and v_reg:
                        self.profiles[owner_id]["vehicles"].add(v_reg)
                    if driver_id in self.profiles and v_reg:
                        self.profiles[driver_id]["vehicles"].add(v_reg)

        # 4. Enrich with travel_movements.csv
        travel_path = self.evidence_dir / "travel_movements.csv"
        if travel_path.exists():
            with open(travel_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pid = row["person_id"]
                    if pid in self.profiles:
                        if row.get("source"):
                            self.profiles[pid]["locations"].add(row["source"])
                        if row.get("destination"):
                            self.profiles[pid]["locations"].add(row["destination"])

        # 5. Enrich with social_media.csv (via case or profile match)
        social_path = self.evidence_dir / "social_media.csv"
        if social_path.exists():
            with open(social_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    handle = row["username"].strip().lower()
                    phone = normalize_phone(row["linked_phone"])["last10"]
                    email = row["linked_email"].strip().lower()
                    cid = row["case_id"]
                    # Link by phone or case name match
                    for pid, p in self.profiles.items():
                        if p["case_id"] == cid:
                            # Match if username contains alias or first name
                            if p["norm_alias"] and p["norm_alias"] in handle:
                                p["social_handles"].add(handle)
                                if email:
                                    p["emails"].add(email)
                                if phone:
                                    p["phones"].add(phone)
                                    p["phone_last10s"].add(phone)

        # 6. Enrich with cdr.csv (call records)
        cdr_path = self.evidence_dir / "cdr.csv"
        if cdr_path.exists():
            with open(cdr_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    caller = normalize_phone(row["caller"])["last10"]
                    receiver = normalize_phone(row["receiver"])["last10"]
                    cid = row["case_id"]
                    # Map to profiles in that case that use these phones
                    for pid, p in self.profiles.items():
                        if p["case_id"] == cid and (caller in p["phone_last10s"] or receiver in p["phone_last10s"]):
                            counterparty = receiver if caller in p["phone_last10s"] else caller
                            if counterparty:
                                p["contacts"].add(counterparty)

        return self.profiles

    def generate_candidate_pairs(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        Generates candidate pairs across different cases using conservative multi-modal blocking.
        Returns list of (person_id_a, person_id_b, candidate_metadata).
        """
        if not self.profiles:
            self.load_and_enrich_evidence()

        pids = sorted(list(self.profiles.keys()))
        candidate_pairs = []
        seen_pairs: Set[Tuple[str, str]] = set()

        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                p1_id, p2_id = pids[i], pids[j]
                p1 = self.profiles[p1_id]
                p2 = self.profiles[p2_id]

                # Only evaluate cross-case pairs
                if p1["case_id"] == p2["case_id"]:
                    continue

                pair_key = (p1_id, p2_id)

                # Blocking Criteria Check:
                reasons = []

                # 1. Exact or normalized phone match
                shared_phones = p1["phone_last10s"].intersection(p2["phone_last10s"])
                if shared_phones:
                    reasons.append(f"shared_phone:{list(shared_phones)[0]}")

                # 2. Device ID or IMEI match
                if p1["device_id"] and p1["device_id"] == p2["device_id"] and p1["device_id"] != "DEV_UNVERIFIED":
                    reasons.append(f"shared_device_id:{p1['device_id']}")
                shared_imeis = p1["imeis"].intersection(p2["imeis"])
                if shared_imeis:
                    reasons.append(f"shared_imei:{list(shared_imeis)[0]}")

                # 3. Vehicle registration match
                shared_vehs = p1["vehicles"].intersection(p2["vehicles"])
                if shared_vehs:
                    reasons.append(f"shared_vehicle:{list(shared_vehs)[0]}")

                # 4. Name similarity (Levenshtein >= 0.65 or token Jaccard >= 0.5 or same last name + initial)
                lev_sim = levenshtein_similarity(p1["norm_name"], p2["norm_name"])
                tok_sim = token_jaccard_similarity(p1["name_tokens"], p2["name_tokens"])
                
                name_match = False
                if lev_sim >= 0.65 or tok_sim >= 0.5:
                    name_match = True
                elif p1["name_tokens"] and p2["name_tokens"] and p1["name_tokens"][-1] == p2["name_tokens"][-1]:
                    # Same surname with same initial
                    if p1["name_initials"] and p2["name_initials"] and p1["name_initials"][0] == p2["name_initials"][0]:
                        name_match = True

                if name_match:
                    reasons.append(f"name_similarity:lev={lev_sim:.2f},tok={tok_sim:.2f}")

                # 5. Alias match / similarity
                if p1["norm_alias"] and p2["norm_alias"]:
                    alias_lev = levenshtein_similarity(p1["norm_alias"], p2["norm_alias"])
                    if alias_lev >= 0.75:
                        reasons.append(f"alias_similarity:{p1['norm_alias']}-{p2['norm_alias']}")

                # 6. Social handles / email overlap
                shared_soc = p1["social_handles"].intersection(p2["social_handles"])
                if shared_soc:
                    reasons.append(f"shared_social:{list(shared_soc)[0]}")

                # Candidate criteria: triggered by at least one strong observable reason
                # (Note: Shared IP alone is NEVER used as a blocking reason!)
                if reasons:
                    candidate_pairs.append((
                        p1_id,
                        p2_id,
                        {
                            "blocking_reasons": reasons,
                            "is_hard_negative": False
                        }
                    ))
                    seen_pairs.add(pair_key)

        return candidate_pairs
