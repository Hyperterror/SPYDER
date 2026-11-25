"""
Node Builder for Global Case Knowledge Graph.
Extracts 11 observable node types across all evidence tables and builds provisional
resolved entity clusters with transitivity safeguards and cluster quality metrics.

ORGANIZATION nodes are derived (see ``synthetic_data_generator/derive_organizations.py``)
from observable occupation, investigating-agency and chain-of-custody records. An
affiliation is an observed association, not a claim about an entity's role.
"""

import csv
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional
import networkx as nx

from graph_analysis.config import (
    EVIDENCE_DIR, ER_PREDICTIONS_PATH, ER_HIGH_CONFIDENCE_THRESHOLD,
    ER_CONFLICT_THRESHOLD, MAX_TRANSITIVE_CHAIN_LENGTH, MIN_CLUSTER_COHESION
)
from graph_analysis.schema import NodeType, GraphNode, ResolvedClusterMetadata

# Administrative custody organisations (evidence stores, forensic laboratories) are
# recorded in ``org_affiliations.csv`` for provenance but are deliberately kept out
# of the network graph: they touch every evidence item and would otherwise dominate
# degree/PageRank purely by clerical fan-out, drowning out investigative leads.
ADMINISTRATIVE_ORG_TYPES = {"FORENSIC_LABORATORY", "EVIDENCE_STORE"}

class NodeBuilder:
    def __init__(self, evidence_dir: Path = EVIDENCE_DIR, er_predictions_path: Path = ER_PREDICTIONS_PATH):
        self.evidence_dir = Path(evidence_dir)
        self.er_predictions_path = Path(er_predictions_path)
        self.nodes: Dict[str, GraphNode] = {}
        self.resolved_clusters: Dict[str, ResolvedClusterMetadata] = {}
        self.person_to_resolved: Dict[str, str] = {}
        self.pairwise_predictions: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def load_er_predictions(self):
        """Loads Phase 2 pairwise predictions and indexes them."""
        if not self.er_predictions_path.exists():
            return

        with open(self.er_predictions_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_a = row["person_id_a"]
                p_b = row["person_id_b"]
                prob = float(row["match_probability"])
                key = tuple(sorted([p_a, p_b]))
                self.pairwise_predictions[key] = {
                    "person_id_a": p_a,
                    "person_id_b": p_b,
                    "match_probability": prob,
                    "confidence_tier": row["confidence_tier"],
                    "explanation_summary": row["explanation_summary"],
                    "supporting_reasons": row["supporting_reasons"],
                    "conflicting_reasons": row["conflicting_reasons"],
                    "case_id_a": row["case_id_a"],
                    "case_id_b": row["case_id_b"]
                }

    def build_provisional_resolved_entities(self) -> Dict[str, ResolvedClusterMetadata]:
        """
        Builds provisional resolved entity clusters with strict transitivity safeguards.
        1. Identifies high-confidence edges (p >= 0.90).
        2. Detects components.
        3. Validates cluster consistency: checks if any pair within component has conflicting
           or low-confidence prediction (p < 0.50). If conflict exists, splits the component.
        4. Calculates cohesion, minimum pair probability, and cluster diameter.
        5. Flags long chains or low-cohesion clusters for investigator review.
        """
        self.load_er_predictions()
        
        # Build graph of high-confidence links
        er_graph = nx.Graph()
        for (p_a, p_b), data in self.pairwise_predictions.items():
            if data["match_probability"] >= ER_HIGH_CONFIDENCE_THRESHOLD:
                er_graph.add_edge(p_a, p_b, weight=data["match_probability"], data=data)

        cluster_idx = 1
        for comp in list(nx.connected_components(er_graph)):
            members = sorted(list(comp))
            if len(members) < 2:
                continue

            subgraph = er_graph.subgraph(members)
            
            # Safeguard: Check for internal conflicts or low-confidence cross-pairs
            # e.g., if A-B=0.96 and B-C=0.95, but A-C was evaluated and had p < 0.50
            has_conflict = False
            conflict_details = []
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    m1, m2 = members[i], members[j]
                    pair_key = tuple(sorted([m1, m2]))
                    if pair_key in self.pairwise_predictions:
                        p_data = self.pairwise_predictions[pair_key]
                        if p_data["match_probability"] < ER_CONFLICT_THRESHOLD:
                            has_conflict = True
                            conflict_details.append(
                                f"Low-confidence affinity between {m1} and {m2} (p={p_data['match_probability']:.3f})"
                            )

            # If conflict found, we do not perform silent monolithic merge;
            # we isolate cliques or strongest edges
            if has_conflict:
                # Fallback to direct cliques or disjoint edges with highest weight
                cliques = list(nx.find_cliques(subgraph))
                # Process cliques separately
                component_groups = [sorted(c) for c in cliques if len(c) >= 2]
            else:
                component_groups = [members]

            for grp in component_groups:
                # Check if group already covered
                if any(m in self.person_to_resolved for m in grp):
                    continue

                grp_subgraph = er_graph.subgraph(grp)
                links = []
                probs = []
                for u, v, d in grp_subgraph.edges(data=True):
                    links.append(d["data"])
                    probs.append(d["weight"])

                # Metrics
                cohesion = sum(probs) / len(probs) if probs else 1.0
                min_prob = min(probs) if probs else 1.0
                try:
                    diameter = nx.diameter(grp_subgraph)
                except nx.NetworkXError:
                    diameter = 1

                # Check transitivity: is graph a complete clique?
                possible_edges = len(grp) * (len(grp) - 1) // 2
                is_transitive = len(links) < possible_edges or diameter > 1

                # Review flagging
                review_reasons = []
                flagged = False
                if diameter > 2 or len(grp) > MAX_TRANSITIVE_CHAIN_LENGTH:
                    flagged = True
                    review_reasons.append(f"Transitive chain length {diameter} exceeds review threshold")
                if cohesion < MIN_CLUSTER_COHESION:
                    flagged = True
                    review_reasons.append(f"Cluster cohesion {cohesion:.3f} below threshold {MIN_CLUSTER_COHESION}")
                if has_conflict:
                    flagged = True
                    review_reasons.extend(conflict_details)

                # Find member cases
                member_cases = set()
                for link in links:
                    member_cases.add(link["case_id_a"])
                    member_cases.add(link["case_id_b"])

                cluster_id = f"PROV_RES_ENT_{cluster_idx:03d}"
                cluster_meta = ResolvedClusterMetadata(
                    cluster_id=cluster_id,
                    member_person_ids=grp,
                    member_cases=sorted(list(member_cases)),
                    pairwise_links=links,
                    cohesion_score=cohesion,
                    min_pair_probability=min_prob,
                    is_transitive=is_transitive,
                    cluster_diameter=diameter,
                    flagged_for_review=flagged,
                    review_reasons=review_reasons
                )

                self.resolved_clusters[cluster_id] = cluster_meta
                for m in grp:
                    self.person_to_resolved[m] = cluster_id

                # Create graph node for provisional resolved entity
                self.nodes[cluster_id] = GraphNode(
                    node_id=cluster_id,
                    node_type=NodeType.PERSON,
                    label=f"Provisional Resolved Entity ({cluster_id})",
                    case_ids=member_cases,
                    resolved_entity_id=cluster_id,
                    attributes={
                        "is_provisional_resolved": True,
                        "cluster_size": len(grp),
                        "member_person_ids": grp,
                        "cohesion_score": round(cohesion, 4),
                        "min_pair_probability": round(min_prob, 4),
                        "is_transitive": is_transitive,
                        "cluster_diameter": diameter,
                        "flagged_for_review": flagged,
                        "review_reasons": review_reasons,
                        "status": "High-Confidence Association (Investigative Lead)"
                    }
                )
                cluster_idx += 1

        return self.resolved_clusters

    def build_all_nodes(self) -> Dict[str, GraphNode]:
        """Extracts and standardizes all 10 observable node types."""
        # 1. Provisional Resolved Entities (built first so persons can link)
        self.build_provisional_resolved_entities()

        # 2. CASES
        cases_path = self.evidence_dir / "cases.csv"
        if cases_path.exists():
            with open(cases_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row["case_id"]
                    self.nodes[cid] = GraphNode(
                        node_id=cid,
                        node_type=NodeType.CASE,
                        label=f"{cid}: {row.get('case_type', 'Case')}",
                        case_ids={cid},
                        attributes={
                            "case_type": row.get("case_type"),
                            "reported_date": row.get("reported_date"),
                            "incident_date": row.get("incident_date"),
                            "origin_location": row.get("origin_location"),
                            "destination_location": row.get("destination_location"),
                            "agency": row.get("agency"),
                            "priority": row.get("priority"),
                            "status": row.get("status")
                        }
                    )

        # 3. PERSONS (Observational)
        persons_path = self.evidence_dir / "persons.csv"
        if persons_path.exists():
            with open(persons_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pid = row["person_id"]
                    cid = row["case_id"]
                    res_id = self.person_to_resolved.get(pid)
                    self.nodes[pid] = GraphNode(
                        node_id=pid,
                        node_type=NodeType.PERSON,
                        label=f"{row['name']} ({pid})",
                        case_ids={cid},
                        resolved_entity_id=res_id,
                        attributes={
                            "name": row.get("name"),
                            "alias": row.get("alias"),
                            "age_group": row.get("age_group"),
                            "procedural_role": row.get("role"),
                            "occupation": row.get("occupation"),
                            "address": row.get("address"),
                            "phone_id": row.get("phone_id"),
                            "device_id": row.get("device_id"),
                            "is_provisional_resolved": False
                        }
                    )

        # 4. VICTIMS
        victims_path = self.evidence_dir / "victims.csv"
        if victims_path.exists():
            with open(victims_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    vid = row["victim_id"]
                    cid = row["case_id"]
                    self.nodes[vid] = GraphNode(
                        node_id=vid,
                        node_type=NodeType.VICTIM,
                        label=f"Victim ({vid})",
                        case_ids={cid},
                        attributes={
                            "age_group": row.get("age_group"),
                            "reported_location": row.get("reported_location"),
                            "last_known_location": row.get("last_known_location"),
                            "recruitment_channel": row.get("recruitment_channel"),
                            "status": row.get("status")
                        }
                    )

        # 5. PHONES (From CDR, Chat, Social Media, and Persons)
        # Collect distinct phone numbers
        phones_seen: Dict[str, Set[str]] = {}

        # Social Media phones
        social_path = self.evidence_dir / "social_media.csv"
        if social_path.exists():
            with open(social_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    p = row.get("linked_phone")
                    cid = row.get("case_id")
                    if p:
                        phones_seen.setdefault(p, set()).add(cid)

        # CDR phones
        cdr_path = self.evidence_dir / "cdr.csv"
        if cdr_path.exists():
            with open(cdr_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row.get("case_id")
                    for p in [row.get("caller"), row.get("receiver")]:
                        if p:
                            phones_seen.setdefault(p, set()).add(cid)

        # Chat phones
        chat_path = self.evidence_dir / "chat_logs.csv"
        if chat_path.exists():
            with open(chat_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row.get("case_id")
                    for p in [row.get("sender"), row.get("receiver")]:
                        if p:
                            phones_seen.setdefault(p, set()).add(cid)

        # Register PHONE nodes
        for ph, cids in phones_seen.items():
            self.nodes[ph] = GraphNode(
                node_id=ph,
                node_type=NodeType.PHONE,
                label=f"Phone {ph}",
                case_ids=cids,
                attributes={"phone_number": ph}
            )

        # 6. DEVICES (Hardware IMEIs and Device IDs from device_logs.csv and persons.csv)
        dev_path = self.evidence_dir / "device_logs.csv"
        if dev_path.exists():
            with open(dev_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    did = row["device_id"]
                    imei = row.get("imei")
                    cid = row["case_id"]
                    if did not in self.nodes:
                        self.nodes[did] = GraphNode(
                            node_id=did,
                            node_type=NodeType.DEVICE,
                            label=f"Device {did} (IMEI {imei})",
                            case_ids={cid},
                            attributes={"device_id": did, "imei": imei}
                        )
                    else:
                        self.nodes[did].case_ids.add(cid)
                    
                    # Also register IMEI as a dedicated device identifier node
                    if imei:
                        imei_id = f"IMEI_{imei}"
                        if imei_id not in self.nodes:
                            self.nodes[imei_id] = GraphNode(
                                node_id=imei_id,
                                node_type=NodeType.DEVICE,
                                label=f"IMEI {imei}",
                                case_ids={cid},
                                attributes={"imei": imei, "is_hardware_imei": True}
                            )
                        else:
                            self.nodes[imei_id].case_ids.add(cid)

        # 7. VEHICLES (From vehicle_records.csv and travel_movements.csv)
        veh_path = self.evidence_dir / "vehicle_records.csv"
        if veh_path.exists():
            with open(veh_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    vid = row["vehicle_id"]
                    v_reg = row["registration_no"]
                    cid = row["case_id"]
                    self.nodes[vid] = GraphNode(
                        node_id=vid,
                        node_type=NodeType.VEHICLE,
                        label=f"Vehicle {v_reg} ({vid})",
                        case_ids={cid},
                        attributes={
                            "vehicle_id": vid,
                            "registration_no": v_reg,
                            "vehicle_type": row.get("vehicle_type"),
                            "owner_id": row.get("owner_id"),
                            "driver_id": row.get("driver_id")
                        }
                    )

        # 8. BANK_ACCOUNTS (From financial_transactions.csv)
        fin_path = self.evidence_dir / "financial_transactions.csv"
        if fin_path.exists():
            with open(fin_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row["case_id"]
                    for acc in [row["sender_account"], row["receiver_account"]]:
                        if acc:
                            if acc not in self.nodes:
                                self.nodes[acc] = GraphNode(
                                    node_id=acc,
                                    node_type=NodeType.BANK_ACCOUNT,
                                    label=f"Account {acc}",
                                    case_ids={cid},
                                    attributes={"account_id": acc}
                                )
                            else:
                                self.nodes[acc].case_ids.add(cid)

        # 9. SOCIAL_ACCOUNTS (From social_media.csv)
        if social_path.exists():
            with open(social_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    acc_id = row["account_id"]
                    cid = row["case_id"]
                    self.nodes[acc_id] = GraphNode(
                        node_id=acc_id,
                        node_type=NodeType.SOCIAL_ACCOUNT,
                        label=f"{row['platform']}: {row['username']}",
                        case_ids={cid},
                        attributes={
                            "username": row.get("username"),
                            "platform": row.get("platform"),
                            "linked_phone": row.get("linked_phone"),
                            "linked_email": row.get("linked_email"),
                            "created_date": row.get("created_date")
                        }
                    )

        # 10. LOCATIONS (From cases, travel, cell towers, and device logs)
        locs_seen: Dict[str, Set[str]] = {}

        # Travel movements
        travel_path = self.evidence_dir / "travel_movements.csv"
        if travel_path.exists():
            with open(travel_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cid = row["case_id"]
                    for loc in [row.get("source"), row.get("destination")]:
                        if loc:
                            locs_seen.setdefault(loc, set()).add(cid)

        # Cell towers from CDR
        if cdr_path.exists():
            with open(cdr_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    twr = row.get("cell_tower")
                    cid = row.get("case_id")
                    if twr:
                        locs_seen.setdefault(twr, set()).add(cid)

        for loc_name, cids in locs_seen.items():
            loc_id = f"LOC_{loc_name.replace(' ', '_').replace('/', '_')}"
            self.nodes[loc_id] = GraphNode(
                node_id=loc_id,
                node_type=NodeType.LOCATION,
                label=f"Location {loc_name}",
                case_ids=cids,
                attributes={"location_name": loc_name}
            )

        # 11. EVIDENCE (From evidence.csv)
        evid_path = self.evidence_dir / "evidence.csv"
        if evid_path.exists():
            with open(evid_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    eid = row["evidence_id"]
                    cid = row["case_id"]
                    self.nodes[eid] = GraphNode(
                        node_id=eid,
                        node_type=NodeType.EVIDENCE,
                        label=f"Evidence {eid} ({row.get('evidence_type', 'Item')})",
                        case_ids={cid},
                        attributes={
                            "evidence_type": row.get("evidence_type"),
                            "timestamp": row.get("timestamp"),
                            "source_file": row.get("source_file"),
                            "extraction_method": row.get("extraction_method"),
                            "reliability": row.get("reliability"),
                            "chain_of_custody": row.get("chain_of_custody")
                        }
                    )

        # 12. ORGANIZATIONS (Derived from occupation, investigating agency and custody records)
        orgs_path = self.evidence_dir / "organizations.csv"
        if orgs_path.exists():
            with open(orgs_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    oid = row["org_id"]
                    cid = row.get("case_id")
                    if (row.get("org_type") or "") in ADMINISTRATIVE_ORG_TYPES:
                        continue
                    city = (row.get("registered_office_city") or "").strip()
                    self.nodes[oid] = GraphNode(
                        node_id=oid,
                        node_type=NodeType.ORGANIZATION,
                        label=row.get("name", oid),
                        case_ids={cid} if cid else set(),
                        attributes={
                            "org_name": row.get("name"),
                            "org_type": row.get("org_type"),
                            "sector": row.get("sector"),
                            "registration_no": row.get("registration_no"),
                            "office_city": city or None,
                        }
                    )
                    # Ensure the operating city exists as a LOCATION node so the
                    # ORGANIZATION --OPERATES_IN--> LOCATION edge has a real target.
                    if city:
                        loc_id = f"LOC_{city.replace(' ', '_').replace('/', '_')}"
                        if loc_id in self.nodes:
                            if cid:
                                self.nodes[loc_id].case_ids.add(cid)
                        else:
                            self.nodes[loc_id] = GraphNode(
                                node_id=loc_id,
                                node_type=NodeType.LOCATION,
                                label=f"Location {city}",
                                case_ids={cid} if cid else set(),
                                attributes={"location_name": city}
                            )

        return self.nodes
