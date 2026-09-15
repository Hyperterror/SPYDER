"""
Edge Builder for Global Case Knowledge Graph.
Extracts evidence-backed relationships across all observable tables, attaching complete
provenance metadata and evaluating context-aware identifier reliability.
"""

import csv
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from collections import Counter

from graph_analysis.config import (
    EVIDENCE_DIR, KNOWN_PUBLIC_IPS, KNOWN_PUBLIC_ACCOUNTS, KNOWN_PUBLIC_PHONES,
    IDENTIFIER_BASE_RELIABILITY
)
from graph_analysis.schema import EdgeType, GraphEdge, ProvenanceRecord, GraphNode

class EdgeBuilder:
    def __init__(self, nodes: Dict[str, GraphNode], evidence_dir: Path = EVIDENCE_DIR):
        self.nodes = nodes
        self.evidence_dir = Path(evidence_dir)
        self.edges: List[GraphEdge] = []
        
        # Phone to person mappings (from social media, person records)
        self.phone_to_persons: Dict[str, Set[str]] = {}
        self.device_to_persons: Dict[str, Set[str]] = {}
        self.imei_to_devices: Dict[str, Set[str]] = {}
        
        # Identifier frequency counts for fan-out / sharing analysis
        self.identifier_usage_counts: Counter = Counter()

    def _build_cross_references(self):
        """Indexes observable device/phone links to persons."""
        # From persons.csv
        persons_path = self.evidence_dir / "persons.csv"
        if persons_path.exists():
            with open(persons_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pid = row["person_id"]
                    dev = row.get("device_id")
                    ph = row.get("phone_id")
                    if dev:
                        self.device_to_persons.setdefault(dev, set()).add(pid)
                    if ph:
                        self.phone_to_persons.setdefault(ph, set()).add(pid)

        # From social_media.csv
        social_path = self.evidence_dir / "social_media.csv"
        if social_path.exists():
            with open(social_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    phone = row.get("linked_phone")
                    cid = row.get("case_id")
                    handle = row.get("username", "").lower()
                    if phone and cid:
                        # Find person in case matching alias/name or case
                        for pid, n in self.nodes.items():
                            if n.case_ids == {cid} and n.node_type.value == "PERSON":
                                alias = (n.attributes.get("alias") or "").lower()
                                if alias and alias in handle:
                                    self.phone_to_persons.setdefault(phone, set()).add(pid)

        # From device_logs.csv
        device_logs_path = self.evidence_dir / "device_logs.csv"
        if device_logs_path.exists():
            with open(device_logs_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    dev = row.get("device_id")
                    ph = row.get("phone_id")
                    imei = row.get("imei")
                    if dev and imei:
                        self.imei_to_devices.setdefault(f"IMEI_{imei}", set()).add(dev)
                    if ph and dev:
                        for p in self.device_to_persons.get(dev, set()):
                            self.phone_to_persons.setdefault(ph, set()).add(p)

    def _compute_contextual_confidence(self, identifier_type: str, identifier_val: str, direct: bool = True) -> float:
        """
        Calculates context-aware identifier strength based on Safeguard 2:
        - Base reliability
        - Known public infrastructure penalty
        - Fan-out / multi-person sharing penalty
        - Direct vs indirect link
        """
        base = IDENTIFIER_BASE_RELIABILITY.get(identifier_type, 0.60)
        
        # Check known public infrastructure
        if identifier_val in KNOWN_PUBLIC_IPS or identifier_val in KNOWN_PUBLIC_ACCOUNTS or identifier_val in KNOWN_PUBLIC_PHONES:
            return 0.15  # Extremely low confidence for confirmed public transit/hotspot infrastructure

        # Check fan-out (if used by >= 4 distinct persons/cases, it is ambiguous)
        usage = self.identifier_usage_counts.get(identifier_val, 1)
        if usage > 6:
            base *= 0.40
        elif usage > 3:
            base *= 0.70

        if not direct:
            base *= 0.85

        return max(0.10, min(0.99, base))

    def build_all_edges(self) -> List[GraphEdge]:
        """Builds all observable evidence-backed edges with complete provenance."""
        self._build_cross_references()

        # 1. PERSON -> APPEARS_IN -> CASE & OBSERVES_ENTITY -> PROVISIONAL_RESOLVED_ENTITY
        persons_path = self.evidence_dir / "persons.csv"
        if persons_path.exists():
            with open(persons_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pid = row["person_id"]
                    cid = row["case_id"]
                    dev = row.get("device_id")
                    ph = row.get("phone_id")
                    
                    # APPEARS_IN
                    prov = ProvenanceRecord(
                        source_table="persons.csv",
                        source_id=pid,
                        case_id=cid,
                        evidence_type="Case Dossier Record",
                        confidence=1.0,
                        notes=f"Procedural role: {row.get('role')}"
                    )
                    self.edges.append(GraphEdge(
                        source_id=pid,
                        target_id=cid,
                        edge_type=EdgeType.APPEARS_IN,
                        provenance=prov,
                        weight=1.0
                    ))

                    # OBSERVES_ENTITY (provisional cluster link)
                    node = self.nodes.get(pid)
                    if node and node.resolved_entity_id:
                        res_id = node.resolved_entity_id
                        prov_er = ProvenanceRecord(
                            source_table="output/entity_resolution/predictions.csv",
                            source_id=f"{pid}->{res_id}",
                            case_id=cid,
                            evidence_type="Provisional Entity Association",
                            confidence=node.attributes.get("cohesion_score", 0.95),
                            notes="High-confidence association (Safeguard 1: provisional, not factual identity)"
                        )
                        self.edges.append(GraphEdge(
                            source_id=pid,
                            target_id=res_id,
                            edge_type=EdgeType.OBSERVES_ENTITY,
                            provenance=prov_er,
                            weight=node.attributes.get("cohesion_score", 0.95)
                        ))

                    # USED_DEVICE
                    if dev and dev in self.nodes:
                        self.identifier_usage_counts[dev] += 1
                        conf = self._compute_contextual_confidence("DEVICE", dev, direct=True)
                        prov_dev = ProvenanceRecord(
                            source_table="persons.csv",
                            source_id=pid,
                            case_id=cid,
                            evidence_type="Forensic Device Association",
                            confidence=conf,
                            notes=f"Device assigned in FIR dossier: {dev}"
                        )
                        self.edges.append(GraphEdge(
                            source_id=pid,
                            target_id=dev,
                            edge_type=EdgeType.USED_DEVICE,
                            provenance=prov_dev,
                            weight=conf
                        ))

        # 2. VICTIM -> APPEARS_IN -> CASE
        victims_path = self.evidence_dir / "victims.csv"
        if victims_path.exists():
            with open(victims_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    vid = row["victim_id"]
                    cid = row["case_id"]
                    prov = ProvenanceRecord(
                        source_table="victims.csv",
                        source_id=vid,
                        case_id=cid,
                        evidence_type="Victim Recovery Statement",
                        confidence=1.0,
                        notes=f"Status: {row.get('status')}"
                    )
                    self.edges.append(GraphEdge(
                        source_id=vid,
                        target_id=cid,
                        edge_type=EdgeType.APPEARS_IN,
                        provenance=prov,
                        weight=1.0
                    ))

        # 3. DEVICE -> HAS_IMEI & DEVICE -> USED_PHONE
        device_logs_path = self.evidence_dir / "device_logs.csv"
        if device_logs_path.exists():
            with open(device_logs_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    dev = row.get("device_id")
                    imei = row.get("imei")
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    ip = row.get("ip_address")
                    loc = row.get("location")
                    
                    if dev and imei:
                        imei_id = f"IMEI_{imei}"
                        self.identifier_usage_counts[imei] += 1
                        conf = self._compute_contextual_confidence("IMEI", imei, direct=True)
                        prov = ProvenanceRecord(
                            source_table="device_logs.csv",
                            source_id=f"{dev}_{imei}",
                            case_id=cid,
                            timestamp=ts,
                            evidence_type="Hardware Telemetry Log",
                            confidence=conf,
                            notes=f"IMEI hardware signature extracted at {loc}"
                        )
                        self.edges.append(GraphEdge(
                            source_id=dev,
                            target_id=imei_id,
                            edge_type=EdgeType.USED_DEVICE,
                            provenance=prov,
                            timestamp=ts,
                            weight=conf,
                            attributes={"ip_address": ip, "location": loc}
                        ))

                    # Also link Device to Location
                    if dev and loc:
                        loc_id = f"LOC_{loc.replace(' ', '_').replace('/', '_')}"
                        if loc_id in self.nodes:
                            prov_loc = ProvenanceRecord(
                                source_table="device_logs.csv",
                                source_id=dev,
                                case_id=cid,
                                timestamp=ts,
                                evidence_type="Cellular Network Sighting",
                                confidence=0.70
                            )
                            self.edges.append(GraphEdge(
                                source_id=dev,
                                target_id=loc_id,
                                edge_type=EdgeType.TRAVELLED_TO,
                                provenance=prov_loc,
                                timestamp=ts,
                                weight=0.70
                            ))

        # 4. VEHICLE -> USED_VEHICLE (From vehicle_records.csv)
        vehicle_path = self.evidence_dir / "vehicle_records.csv"
        if vehicle_path.exists():
            with open(vehicle_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    vid = row["vehicle_id"]
                    reg = row["registration_no"]
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    loc = row.get("location")
                    owner = row.get("owner_id")
                    driver = row.get("driver_id")
                    
                    self.identifier_usage_counts[reg] += 1
                    conf = self._compute_contextual_confidence("VEHICLE_REG", reg, direct=True)

                    for pid, role_desc in [(owner, "Owner"), (driver, "Driver")]:
                        if pid and pid in self.nodes:
                            prov = ProvenanceRecord(
                                source_table="vehicle_records.csv",
                                source_id=vid,
                                case_id=cid,
                                timestamp=ts,
                                evidence_type="FASTag / Transport Authority Record",
                                confidence=conf,
                                notes=f"{role_desc} of {reg} ({row.get('vehicle_type')}) sighted at {loc}"
                            )
                            self.edges.append(GraphEdge(
                                source_id=pid,
                                target_id=vid,
                                edge_type=EdgeType.USED_VEHICLE,
                                provenance=prov,
                                timestamp=ts,
                                weight=conf,
                                attributes={"role": role_desc, "location": loc}
                            ))

        # 5. TRAVEL MOVEMENTS (travel_movements.csv)
        travel_path = self.evidence_dir / "travel_movements.csv"
        if travel_path.exists():
            with open(travel_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    m_id = row["movement_id"]
                    pid = row["person_id"]
                    vid = row.get("vehicle_id")
                    ts = row.get("timestamp")
                    cid = row["case_id"]
                    src = row.get("source")
                    dst = row.get("destination")
                    mode = row.get("transport_mode")
                    ev_src = row.get("evidence_source")

                    if pid and pid in self.nodes:
                        # Link to destination location
                        if dst:
                            loc_id = f"LOC_{dst.replace(' ', '_').replace('/', '_')}"
                            if loc_id in self.nodes:
                                prov = ProvenanceRecord(
                                    source_table="travel_movements.csv",
                                    source_id=m_id,
                                    case_id=cid,
                                    timestamp=ts,
                                    evidence_type=ev_src or "Transit Manifest",
                                    confidence=0.80,
                                    notes=f"Travel from {src} to {dst} via {mode}"
                                )
                                self.edges.append(GraphEdge(
                                    source_id=pid,
                                    target_id=loc_id,
                                    edge_type=EdgeType.TRAVELLED_TO,
                                    provenance=prov,
                                    timestamp=ts,
                                    weight=0.80,
                                    attributes={"origin": src, "mode": mode}
                                ))

                        # Link to vehicle if used
                        if vid and vid in self.nodes:
                            prov_v = ProvenanceRecord(
                                source_table="travel_movements.csv",
                                source_id=m_id,
                                case_id=cid,
                                timestamp=ts,
                                evidence_type=ev_src or "Transit Manifest",
                                confidence=0.85,
                                notes=f"Passenger transit on {mode}"
                            )
                            self.edges.append(GraphEdge(
                                source_id=pid,
                                target_id=vid,
                                edge_type=EdgeType.USED_VEHICLE,
                                provenance=prov_v,
                                timestamp=ts,
                                weight=0.85
                            ))

        # 6. SOCIAL MEDIA (social_media.csv)
        social_path = self.evidence_dir / "social_media.csv"
        if social_path.exists():
            with open(social_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    acc_id = row["account_id"]
                    cid = row["case_id"]
                    ph = row.get("linked_phone")
                    handle = row.get("username", "").lower()
                    
                    # Link to Phone if present
                    if ph and ph in self.nodes:
                        prov = ProvenanceRecord(
                            source_table="social_media.csv",
                            source_id=acc_id,
                            case_id=cid,
                            timestamp=row.get("created_date"),
                            evidence_type="Account Metadata Profile",
                            confidence=0.90,
                            notes=f"Profile linked to phone {ph}"
                        )
                        self.edges.append(GraphEdge(
                            source_id=acc_id,
                            target_id=ph,
                            edge_type=EdgeType.USED_PHONE,
                            provenance=prov,
                            weight=0.90
                        ))

                    # Associate to person in case if alias matches
                    for pid, n in self.nodes.items():
                        if n.case_ids == {cid} and n.node_type.value == "PERSON":
                            alias = (n.attributes.get("alias") or "").lower()
                            if alias and alias in handle:
                                prov_p = ProvenanceRecord(
                                    source_table="social_media.csv",
                                    source_id=acc_id,
                                    case_id=cid,
                                    timestamp=row.get("created_date"),
                                    evidence_type="Digital Account Recovery",
                                    confidence=0.85,
                                    notes=f"Handle @{handle} matches dossier alias {alias}"
                                )
                                self.edges.append(GraphEdge(
                                    source_id=pid,
                                    target_id=acc_id,
                                    edge_type=EdgeType.HAS_SOCIAL_ACCOUNT,
                                    provenance=prov_p,
                                    weight=0.85
                                ))

        # 7. CDR (cdr.csv) -> PHONE --CALLED--> PHONE
        cdr_path = self.evidence_dir / "cdr.csv"
        if cdr_path.exists():
            with open(cdr_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    c_id = row["cdr_id"]
                    caller = row["caller"]
                    receiver = row["receiver"]
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    dur = int(row.get("duration_sec", 0))
                    c_type = row.get("call_type")
                    twr = row.get("cell_tower")

                    # Context-aware check: is it a public hotline?
                    is_public = caller in KNOWN_PUBLIC_PHONES or receiver in KNOWN_PUBLIC_PHONES
                    base_conf = 0.15 if is_public else (0.85 if dur > 0 else 0.50)

                    prov = ProvenanceRecord(
                        source_table="cdr.csv",
                        source_id=c_id,
                        case_id=cid,
                        timestamp=ts,
                        evidence_type="Telecom Call Detail Record",
                        confidence=base_conf,
                        notes=f"{c_type}, duration {dur}s via tower {twr}" + (" [PUBLIC HELPLINE]" if is_public else "")
                    )
                    
                    self.edges.append(GraphEdge(
                        source_id=caller,
                        target_id=receiver,
                        edge_type=EdgeType.CALLED,
                        provenance=prov,
                        timestamp=ts,
                        weight=base_conf,
                        attributes={"duration_sec": dur, "call_type": c_type, "cell_tower": twr}
                    ))

        # 8. CHAT LOGS (chat_logs.csv) -> PHONE --MESSAGED--> PHONE
        chat_path = self.evidence_dir / "chat_logs.csv"
        if chat_path.exists():
            with open(chat_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    m_id = row["message_id"]
                    sender = row["sender"]
                    receiver = row["receiver"]
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    plat = row.get("platform")
                    msg = row.get("message_text")

                    prov = ProvenanceRecord(
                        source_table="chat_logs.csv",
                        source_id=m_id,
                        case_id=cid,
                        timestamp=ts,
                        evidence_type="Encrypted Chat Forensics Extraction",
                        confidence=0.90,
                        notes=f"App: {plat}; Message: \"{msg[:60]}...\""
                    )

                    self.edges.append(GraphEdge(
                        source_id=sender,
                        target_id=receiver,
                        edge_type=EdgeType.MESSAGED,
                        provenance=prov,
                        timestamp=ts,
                        weight=0.90,
                        attributes={"platform": plat, "message_preview": msg[:80]}
                    ))

        # 9. FINANCIAL TRANSACTIONS (financial_transactions.csv) -> BANK_ACCOUNT --TRANSFERRED_MONEY--> BANK_ACCOUNT
        fin_path = self.evidence_dir / "financial_transactions.csv"
        if fin_path.exists():
            with open(fin_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    tx_id = row["transaction_id"]
                    s_acc = row["sender_account"]
                    r_acc = row["receiver_account"]
                    amt = float(row.get("amount", 0))
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    tx_type = row.get("transaction_type")
                    ref = row.get("reference")

                    # Check public utility account
                    is_public = s_acc in KNOWN_PUBLIC_ACCOUNTS or r_acc in KNOWN_PUBLIC_ACCOUNTS
                    conf = 0.15 if is_public else self._compute_contextual_confidence("BANK_ACCOUNT", r_acc, direct=True)

                    prov = ProvenanceRecord(
                        source_table="financial_transactions.csv",
                        source_id=tx_id,
                        case_id=cid,
                        timestamp=ts,
                        evidence_type="Bank Transaction Record",
                        confidence=conf,
                        notes=f"Amount INR {amt:.2f} ({tx_type}) Ref: {ref}" + (" [PUBLIC UTILITY]" if is_public else "")
                    )

                    self.edges.append(GraphEdge(
                        source_id=s_acc,
                        target_id=r_acc,
                        edge_type=EdgeType.TRANSFERRED_MONEY,
                        provenance=prov,
                        timestamp=ts,
                        weight=conf,
                        attributes={"amount": amt, "transaction_type": tx_type, "reference": ref}
                    ))

        # 10. EVIDENCE ITEMS (evidence.csv) -> CASE --ASSOCIATED_WITH_EVIDENCE--> EVIDENCE
        evid_path = self.evidence_dir / "evidence.csv"
        if evid_path.exists():
            with open(evid_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    eid = row["evidence_id"]
                    cid = row["case_id"]
                    ts = row.get("timestamp")
                    ev_type = row.get("evidence_type")
                    method = row.get("extraction_method")

                    prov = ProvenanceRecord(
                        source_table="evidence.csv",
                        source_id=eid,
                        case_id=cid,
                        timestamp=ts,
                        evidence_type=ev_type,
                        confidence=0.95,
                        notes=f"Seized under method: {method}"
                    )

                    self.edges.append(GraphEdge(
                        source_id=cid,
                        target_id=eid,
                        edge_type=EdgeType.ASSOCIATED_WITH_EVIDENCE,
                        provenance=prov,
                        timestamp=ts,
                        weight=0.95
                    ))

        return self.edges
