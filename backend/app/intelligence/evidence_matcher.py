"""
Phase 6B: Evidence Matcher.
Ingests observable empirical evidence datasets (CDR, chat logs, financial transactions,
travel movements, vehicle records, device logs, and graph edges).
Indexes records and matches empirical observations against StructuredClaim predicates.
Strictly enforces:
- High bar for contradiction (device/IP/vehicle associations alone do not prove presence/contradiction).
- Public infrastructure safeguards (public IPs, shared buses, generic transit hubs).
- Multi-case RBAC data isolation.
- Complete empirical provenance without simulated records.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.intelligence.config import (
    EDGES_PATH,
    GENERIC_LOCATIONS,
    KNOWN_PUBLIC_IPS,
    KNOWN_SHARED_BUSES,
    NODES_PATH,
    REPO_ROOT,
)
from app.intelligence.claim_models import (
    ClaimPredicate,
    EvidenceStrength,
    MatchedEvidenceRecord,
    StructuredClaim,
)
from app.intelligence.claim_normalizer import ClaimNormalizer

EVIDENCE_DIR = REPO_ROOT / "synthetic_data_generator" / "output" / "evidence_dataset"
PERSONS_CSV = EVIDENCE_DIR / "persons.csv"
CDR_CSV = EVIDENCE_DIR / "cdr.csv"
CHAT_LOGS_CSV = EVIDENCE_DIR / "chat_logs.csv"
FINANCIAL_CSV = EVIDENCE_DIR / "financial_transactions.csv"
TRAVEL_CSV = EVIDENCE_DIR / "travel_movements.csv"
VEHICLES_CSV = EVIDENCE_DIR / "vehicle_records.csv"
DEVICE_LOGS_CSV = EVIDENCE_DIR / "device_logs.csv"


class EvidenceMatcher:
    """
    Empirical evidence indexer and matcher for statement consistency verification.
    """

    _instance: Optional["EvidenceMatcher"] = None

    def __init__(self):
        self.normalizer = ClaimNormalizer.get_instance()
        # Entity mappings
        self.person_details: Dict[str, dict] = {}
        self.person_phones: Dict[str, Set[str]] = {}
        self.phone_persons: Dict[str, Set[str]] = {}
        self.person_devices: Dict[str, Set[str]] = {}
        self.device_persons: Dict[str, Set[str]] = {}
        self.person_cases: Dict[str, Set[str]] = {}

        # Raw evidence records indexed by key
        self.cdr_records: List[dict] = []
        self.chat_records: List[dict] = []
        self.financial_records: List[dict] = []
        self.travel_records: List[dict] = []
        self.vehicle_records: List[dict] = []
        self.device_log_records: List[dict] = []
        self.edge_records: List[dict] = []

        self._load_all_datasets()

    @classmethod
    def get_instance(cls) -> "EvidenceMatcher":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reload(self) -> None:
        """Clears in-memory indices and reloads all empirical datasets."""
        self.person_details.clear()
        self.person_phones.clear()
        self.phone_persons.clear()
        self.person_devices.clear()
        self.device_persons.clear()
        self.person_cases.clear()
        self.cdr_records.clear()
        self.chat_records.clear()
        self.financial_records.clear()
        self.travel_records.clear()
        self.vehicle_records.clear()
        self.device_log_records.clear()
        self.edge_records.clear()
        self._load_all_datasets()

    def _load_all_datasets(self) -> None:
        """Loads and indexes observable empirical records."""
        # 1. Persons
        if PERSONS_CSV.exists():
            with open(PERSONS_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pid = row["person_id"]
                    cid = row.get("case_id", "")
                    ph_id = row.get("phone_id", "")
                    dev_id = row.get("device_id", "")
                    self.person_details[pid] = row
                    if cid:
                        self.person_cases.setdefault(pid, set()).add(cid)
                    if dev_id:
                        self.person_devices.setdefault(pid, set()).add(dev_id)
                        self.device_persons.setdefault(dev_id, set()).add(pid)

        # 2. Graph Edges & Social media mapping (for phone numbers)
        if EDGES_PATH.exists():
            with open(EDGES_PATH, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.edge_records.append(row)
                    etype = row.get("edge_type", "")
                    src = row.get("source_id", "")
                    tgt = row.get("target_id", "")
                    # Direct social media -> phone mapping
                    if etype == "USED_PHONE" and src.startswith("SOC_") and tgt.startswith("+91"):
                        # Target is phone
                        pass

            # Map person -> social -> phone
            soc_to_phones: Dict[str, Set[str]] = {}
            person_to_socs: Dict[str, Set[str]] = {}
            for r in self.edge_records:
                etype = r.get("edge_type", "")
                src = r.get("source_id", "")
                tgt = r.get("target_id", "")
                if etype == "USED_PHONE" and src.startswith("SOC_"):
                    soc_to_phones.setdefault(src, set()).add(tgt)
                elif etype == "HAS_SOCIAL_ACCOUNT" and tgt.startswith("SOC_"):
                    person_to_socs.setdefault(src, set()).add(tgt)

            for pid, socs in person_to_socs.items():
                for s in socs:
                    for ph in soc_to_phones.get(s, set()):
                        self.person_phones.setdefault(pid, set()).add(ph)
                        self.phone_persons.setdefault(ph, set()).add(pid)

        # 3. CDR
        if CDR_CSV.exists():
            with open(CDR_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    caller = self.normalizer.normalize_phone_number(row.get("caller", "")) or row.get("caller", "")
                    receiver = self.normalizer.normalize_phone_number(row.get("receiver", "")) or row.get("receiver", "")
                    row["caller"] = caller
                    row["receiver"] = receiver
                    self.cdr_records.append(row)

        # 4. Chat Logs
        if CHAT_LOGS_CSV.exists():
            with open(CHAT_LOGS_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sender = self.normalizer.normalize_phone_number(row.get("sender", "")) or row.get("sender", "")
                    receiver = self.normalizer.normalize_phone_number(row.get("receiver", "")) or row.get("receiver", "")
                    row["sender"] = sender
                    row["receiver"] = receiver
                    self.chat_records.append(row)

        # 5. Financial Transactions
        if FINANCIAL_CSV.exists():
            with open(FINANCIAL_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.financial_records.append(row)

        # 6. Travel Movements
        if TRAVEL_CSV.exists():
            with open(TRAVEL_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.travel_records.append(row)

        # 7. Vehicle Records
        if VEHICLES_CSV.exists():
            with open(VEHICLES_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.vehicle_records.append(row)

        # 8. Device Logs
        if DEVICE_LOGS_CSV.exists():
            with open(DEVICE_LOGS_CSV, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.device_log_records.append(row)
                    dev_id = row.get("device_id", "")
                    ph_id = row.get("phone_id", "")

    def get_person_phones(self, person_id: str) -> Set[str]:
        """Returns all observable phone numbers linked to person_id."""
        return self.person_phones.get(person_id, set())

    def get_person_devices(self, person_id: str) -> Set[str]:
        """Returns all observable device identifiers linked to person_id."""
        return self.person_devices.get(person_id, set())

    def _is_case_authorized(self, case_id: str, authorized_cases: Optional[List[str]]) -> bool:
        """Enforces multi-case RBAC data isolation."""
        if authorized_cases is None:
            return True
        return case_id in authorized_cases

    def _check_time_overlap(
        self,
        record_ts: Optional[str],
        claim_start: Optional[str],
        claim_end: Optional[str],
    ) -> Tuple[bool, bool]:
        """
        Checks if a record timestamp falls within claim temporal window.
        Returns: (is_overlapping, is_exact_match)
        """
        if not record_ts or not claim_start or not claim_end:
            return True, False  # Without constraints, assume potential alignment

        try:
            r_dt = datetime.fromisoformat(record_ts.replace(" ", "T"))
            s_dt = datetime.fromisoformat(claim_start.replace(" ", "T"))
            e_dt = datetime.fromisoformat(claim_end.replace(" ", "T"))
            if s_dt <= r_dt <= e_dt:
                return True, True
            # Check within 24 hours buffer
            buffer_s = s_dt.timestamp() - 86400
            buffer_e = e_dt.timestamp() + 86400
            if buffer_s <= r_dt.timestamp() <= buffer_e:
                return True, False
            return False, False
        except Exception:
            return True, False

    def match_evidence_for_claim(
        self,
        claim: StructuredClaim,
        authorized_cases: Optional[List[str]] = None,
    ) -> Tuple[List[MatchedEvidenceRecord], List[MatchedEvidenceRecord], float, List[str]]:
        """
        Matches empirical evidence against structured claim.
        Returns: (matched_corroborating, conflicting_records, match_confidence, caveats)
        """
        matched: List[MatchedEvidenceRecord] = []
        conflicts: List[MatchedEvidenceRecord] = []
        caveats: List[str] = []

        predicate = claim.predicate
        subject = claim.subject_entity_id
        obj = claim.object_entity_id
        loc = claim.location_id
        time_s = claim.time_start
        time_e = claim.time_end
        negated = claim.negated

        subj_phones = self.get_person_phones(subject)
        subj_devices = self.get_person_devices(subject)

        obj_phones = self.get_person_phones(obj) if obj else set()
        if obj and obj.startswith("+91"):
            obj_phones.add(obj)

        # Check if subject is an explicit phone number
        if subject and subject.startswith("+91"):
            subj_phones.add(subject)

        # -------------------------------------------------------------
        # PREDICATE: CALLED / CONTACTED
        # -------------------------------------------------------------
        if predicate in (ClaimPredicate.CALLED, ClaimPredicate.CONTACTED):
            # Scan CDR records
            for cdr in self.cdr_records:
                cid = cdr.get("case_id", "")
                if not self._is_case_authorized(cid, authorized_cases):
                    continue

                caller = cdr.get("caller", "")
                receiver = cdr.get("receiver", "")
                ts = cdr.get("timestamp", "")
                cdr_id = cdr.get("cdr_id", "")

                # Check involvement
                subj_involved = (caller in subj_phones) or (receiver in subj_phones)
                obj_involved = (caller in obj_phones) or (receiver in obj_phones) or (obj and (caller == obj or receiver == obj))

                # If subject has no direct phone assigned in persons.csv, but is part of the case dossier,
                # any call with the claimed object in this case context provides empirical telecom evidence
                if not subj_phones and (cid == claim.case_id):
                    subj_involved = True

                if subj_involved and obj_involved:
                    overlap, exact = self._check_time_overlap(ts, time_s, time_e)
                    if overlap:
                        record = MatchedEvidenceRecord(
                            record_id=cdr_id,
                            source_table="cdr.csv",
                            case_id=cid,
                            evidence_type="Telecommunication Record (CDR)",
                            timestamp=ts,
                            relation="CALLED",
                            evidence_strength=EvidenceStrength.HIGH if exact else EvidenceStrength.MEDIUM,
                            match_rationale=f"CDR record {cdr_id} documents communication between {caller} and {receiver} via tower {cdr.get('cell_tower', 'N/A')}.",
                            is_contradiction=negated,
                            attributes=cdr,
                        )
                        if negated:
                            conflicts.append(record)
                        else:
                            matched.append(record)

            # Scan Chat logs
            for chat in self.chat_records:
                cid = chat.get("case_id", "")
                if not self._is_case_authorized(cid, authorized_cases):
                    continue

                sender = chat.get("sender", "")
                receiver = chat.get("receiver", "")
                ts = chat.get("timestamp", "")
                msg_id = chat.get("message_id", "")

                subj_involved = (sender in subj_phones) or (receiver in subj_phones)
                obj_involved = (sender in obj_phones) or (receiver in obj_phones) or (obj and (sender == obj or receiver == obj))

                if not subj_phones and (cid == claim.case_id):
                    subj_involved = True

                if subj_involved and obj_involved:
                    overlap, exact = self._check_time_overlap(ts, time_s, time_e)
                    if overlap:
                        record = MatchedEvidenceRecord(
                            record_id=msg_id,
                            source_table="chat_logs.csv",
                            case_id=cid,
                            evidence_type="Digital Messaging Record",
                            timestamp=ts,
                            relation="CONTACTED",
                            evidence_strength=EvidenceStrength.HIGH if exact else EvidenceStrength.MEDIUM,
                            match_rationale=f"Message {msg_id} ({chat.get('platform', 'N/A')}) documents digital communication between {sender} and {receiver}.",
                            is_contradiction=negated,
                            attributes=chat,
                        )
                        if negated:
                            conflicts.append(record)
                        else:
                            matched.append(record)

        # -------------------------------------------------------------
        # PREDICATE: TRANSFERRED_TO
        # -------------------------------------------------------------
        elif predicate == ClaimPredicate.TRANSFERRED_TO:
            for tx in self.financial_records:
                cid = tx.get("case_id", "")
                if not self._is_case_authorized(cid, authorized_cases):
                    continue

                s_acc = tx.get("sender_account", "")
                r_acc = tx.get("receiver_account", "")
                ts = tx.get("timestamp", "")
                tx_id = tx.get("transaction_id", "")

                acc_match = (obj and (r_acc == obj or s_acc == obj)) or (subject and (s_acc == subject or r_acc == subject))
                if acc_match:
                    overlap, exact = self._check_time_overlap(ts, time_s, time_e)
                    if overlap:
                        record = MatchedEvidenceRecord(
                            record_id=tx_id,
                            source_table="financial_transactions.csv",
                            case_id=cid,
                            evidence_type="Banking / Financial Transaction",
                            timestamp=ts,
                            relation="TRANSFERRED_MONEY",
                            evidence_strength=EvidenceStrength.HIGH if exact else EvidenceStrength.MEDIUM,
                            match_rationale=f"Transaction {tx_id} confirms {tx.get('transaction_type', '')} of INR {tx.get('amount', '')} between {s_acc} and {r_acc}.",
                            is_contradiction=negated,
                            attributes=tx,
                        )
                        if negated:
                            conflicts.append(record)
                        else:
                            matched.append(record)

        # -------------------------------------------------------------
        # PREDICATE: TRAVELLED_TO / LOCATED_AT
        # -------------------------------------------------------------
        elif predicate in (ClaimPredicate.TRAVELLED_TO, ClaimPredicate.LOCATED_AT):
            # 1. Direct Travel Movements
            for mov in self.travel_records:
                cid = mov.get("case_id", "")
                if not self._is_case_authorized(cid, authorized_cases):
                    continue

                p_id = mov.get("person_id", "")
                dest = mov.get("destination", "")
                src = mov.get("source", "")
                ts = mov.get("timestamp", "")
                mov_id = mov.get("movement_id", "")
                v_id = mov.get("vehicle_id", "")

                if p_id == subject:
                    overlap, exact = self._check_time_overlap(ts, time_s, time_e)
                    # Check destination or source match
                    loc_match = (loc and (loc.lower() in dest.lower() or loc.lower() in src.lower()))
                    if loc_match and overlap:
                        # Corroborating movement record
                        record = MatchedEvidenceRecord(
                            record_id=mov_id,
                            source_table="travel_movements.csv",
                            case_id=cid,
                            evidence_type=mov.get("evidence_source", "Travel Movement Record"),
                            timestamp=ts,
                            relation="TRAVELLED_TO",
                            evidence_strength=EvidenceStrength.HIGH,
                            match_rationale=f"Movement record {mov_id} confirms physical travel from {src} to {dest} via {mov.get('transport_mode', '')} ({mov.get('evidence_source', '')}).",
                            is_contradiction=negated,
                            attributes=mov,
                        )
                        if negated:
                            conflicts.append(record)
                        else:
                            matched.append(record)
                    elif loc and not loc_match and exact:
                        # Person was confirmed moving somewhere else at exact same time!
                        record = MatchedEvidenceRecord(
                            record_id=mov_id,
                            source_table="travel_movements.csv",
                            case_id=cid,
                            evidence_type=mov.get("evidence_source", "Travel Movement Record"),
                            timestamp=ts,
                            relation="TRAVELLED_TO",
                            evidence_strength=EvidenceStrength.HIGH,
                            match_rationale=f"Movement record {mov_id} places subject in transit from {src} to {dest}, contrary to claimed location {loc}.",
                            is_contradiction=not negated,
                            attributes=mov,
                        )
                        if not negated:
                            conflicts.append(record)
                        else:
                            matched.append(record)

                    # Public shared bus caveat
                    if v_id in KNOWN_SHARED_BUSES:
                        caveats.append(f"Transit movement utilizes shared public bus {v_id}; passenger co-presence is non-exclusive.")

            # 2. Device Logs (Device presence != physical human presence safeguard)
            for dlog in self.device_log_records:
                cid = dlog.get("case_id", "")
                if not self._is_case_authorized(cid, authorized_cases):
                    continue

                d_id = dlog.get("device_id", "")
                d_loc = dlog.get("location", "")
                d_ip = dlog.get("ip_address", "")
                ts = dlog.get("timestamp", "")

                if d_id in subj_devices:
                    overlap, exact = self._check_time_overlap(ts, time_s, time_e)
                    loc_match = (loc and loc.lower() in d_loc.lower())
                    if overlap:
                        if loc_match:
                            record = MatchedEvidenceRecord(
                                record_id=f"DEVLOG_{d_id}_{ts}",
                                source_table="device_logs.csv",
                                case_id=cid,
                                evidence_type="Forensic Device Telemetry",
                                timestamp=ts,
                                relation="DEVICE_AT_LOCATION",
                                evidence_strength=EvidenceStrength.MEDIUM,
                                match_rationale=f"Device {d_id} associated with subject logged IP/network activity at {d_loc}.",
                                is_contradiction=negated,
                                attributes=dlog,
                            )
                            if negated:
                                conflicts.append(record)
                            else:
                                matched.append(record)
                        elif loc and exact:
                            # Device logged at a different location
                            record = MatchedEvidenceRecord(
                                record_id=f"DEVLOG_{d_id}_{ts}",
                                source_table="device_logs.csv",
                                case_id=cid,
                                evidence_type="Forensic Device Telemetry",
                                timestamp=ts,
                                relation="DEVICE_AT_LOCATION",
                                evidence_strength=EvidenceStrength.LOW,  # Device location alone does NOT prove human location!
                                match_rationale=f"Device {d_id} was observed at {d_loc}, which diverges from claimed location {loc}. Note: device presence does not independently prove individual presence.",
                                is_contradiction=not negated,
                                attributes=dlog,
                            )
                            if not negated:
                                conflicts.append(record)
                            else:
                                matched.append(record)

                    # Public IP caveat
                    if d_ip in KNOWN_PUBLIC_IPS:
                        caveats.append(f"Device activity originated from known public/shared IP {d_ip}; cannot establish exclusive physical presence.")

        # -------------------------------------------------------------
        # PREDICATE: ASSOCIATED_WITH
        # -------------------------------------------------------------
        elif predicate == ClaimPredicate.ASSOCIATED_WITH:
            for edge in self.edge_records:
                cid = edge.get("provenance_case_id", "")
                if cid and not self._is_case_authorized(cid, authorized_cases):
                    continue

                src = edge.get("source_id", "")
                tgt = edge.get("target_id", "")
                etype = edge.get("edge_type", "")
                ts = edge.get("timestamp", "") or "Unavailable"

                # Check if edge connects subject and object
                pair_match = (src == subject and tgt == obj) or (src == obj and tgt == subject)
                if pair_match:
                    record = MatchedEvidenceRecord(
                        record_id=edge.get("provenance_record_id") or "Unavailable",
                        source_table=edge.get("provenance_table") or "edges.csv",
                        case_id=cid or "Unavailable",
                        evidence_type=edge.get("provenance_evidence_type") or etype,
                        timestamp=ts,
                        relation=etype,
                        evidence_strength=EvidenceStrength.HIGH,
                        match_rationale=f"Knowledge graph documents relational association ({etype}) between {src} and {tgt} ({edge.get('notes', '')}).",
                        is_contradiction=negated,
                        attributes=edge,
                    )
                    if negated:
                        conflicts.append(record)
                    else:
                        matched.append(record)

        # Public Infrastructure Location Caveat
        if loc:
            for gen_loc in GENERIC_LOCATIONS:
                if loc.lower() in gen_loc.lower():
                    caveats.append(f"Claimed location references high-density generic hub ({loc}); coincidental presence is common.")
                    break

        # Public Infrastructure IP / Vehicle checks from claim text
        for pub_ip in KNOWN_PUBLIC_IPS:
            if pub_ip in claim.raw_text:
                caveats.append(f"Assertion references known public/shared IP {pub_ip}; cannot establish exclusive physical presence.")

        for shared_bus in KNOWN_SHARED_BUSES:
            if shared_bus in claim.raw_text:
                caveats.append(f"Assertion references known shared commercial vehicle {shared_bus}; passenger presence is non-exclusive.")

        # Compute evidence match confidence
        total_records = len(matched) + len(conflicts)
        if total_records == 0:
            evidence_conf = 0.20  # No empirical corroboration found
        else:
            has_high = any(r.evidence_strength == EvidenceStrength.HIGH for r in (matched + conflicts))
            if has_high:
                evidence_conf = 0.90
            else:
                has_med = any(r.evidence_strength == EvidenceStrength.MEDIUM for r in (matched + conflicts))
                evidence_conf = 0.70 if has_med else 0.50

        return matched, conflicts, round(evidence_conf, 3), list(set(caveats))
