"""
Candidate Generation and Negative Sampling for Phase 4.
Generates observed positive PERSON ↔ PERSON links and constructs 7 categories of negatives
(Types A through G) to rigorously train and validate link prediction models.
"""

import random
from typing import Dict, List, Set, Any, Tuple, Optional
import networkx as nx

from phase4.config import (
    KNOWN_PUBLIC_IPS, KNOWN_SHARED_BUSES, GENERIC_LOCATIONS,
    RANDOM_SEED, NEGATIVE_RATIO
)

class CandidateGenerator:
    def __init__(self, multi_graph: nx.MultiDiGraph, random_seed: int = RANDOM_SEED):
        self.multi_graph = multi_graph
        self.rng = random.Random(random_seed)
        self.undirected_g = multi_graph.to_undirected()

        self.person_nodes = [
            n for n, d in self.multi_graph.nodes(data=True)
            if d.get("node_type") == "PERSON"
        ]

        # Map person to case memberships
        self.person_cases: Dict[str, Set[str]] = {
            p: self.multi_graph.nodes[p].get("case_ids", set())
            for p in self.person_nodes
        }

        # Track existing observed positive ties and their supporting graph edges
        self.observed_positive_pairs: Set[Tuple[str, str]] = set()
        self.positive_supporting_edges: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
        self.positive_max_timestamp: Dict[Tuple[str, str], str] = {}
        self._extract_observed_positives()

    def _canonical_edge(self, u: str, v: str) -> Tuple[str, str]:
        return (u, v) if u <= v else (v, u)

    def _record_edge_timestamp(self, pair: Tuple[str, str], ts: Any) -> None:
        if ts:
            ts_str = str(ts).strip()
            if ts_str and ts_str > self.positive_max_timestamp.get(pair, ""):
                self.positive_max_timestamp[pair] = ts_str

    def _extract_observed_positives(self):
        """
        Extracts evidence-backed person-to-person connections and records exact supporting edges
        so split evaluation can mask out held-out target edges cleanly:
        - Direct call/chat between their phones (records the CALLED/MESSAGED edge)
        - Financial transfer or shared personal entity / provisional node (records incident edges)
        """
        # Map phone/device/account to persons
        entity_to_persons: Dict[str, Set[str]] = {}
        for p in self.person_nodes:
            for _, target, d in self.multi_graph.out_edges(p, data=True):
                ttype = self.multi_graph.nodes[target].get("node_type")
                if ttype in ["PHONE", "DEVICE", "BANK_ACCOUNT", "PERSON"]:
                    entity_to_persons.setdefault(target, set()).add(p)

        # Direct links via shared personal entities or resolved clusters
        for ent, persons in entity_to_persons.items():
            if len(persons) >= 2:
                # Exclude high fan-out infrastructure
                if ent in KNOWN_PUBLIC_IPS or ent in KNOWN_SHARED_BUSES or ent in GENERIC_LOCATIONS:
                    continue
                deg = self.undirected_g.degree(ent)
                if deg > 6:  # Skip high fan-out
                    continue

                p_list = sorted(list(persons))
                for i in range(len(p_list)):
                    for j in range(i + 1, len(p_list)):
                        pair = (p_list[i], p_list[j])
                        self.observed_positive_pairs.add(pair)
                        edges_set = self.positive_supporting_edges.setdefault(pair, set())
                        edges_set.add(self._canonical_edge(p_list[i], ent))
                        edges_set.add(self._canonical_edge(p_list[j], ent))
                        for node_end in (p_list[i], p_list[j]):
                            if self.multi_graph.has_edge(node_end, ent):
                                for _, d in self.multi_graph[node_end][ent].items():
                                    self._record_edge_timestamp(pair, d.get("timestamp"))

        # Also add direct phone communication (calls/chats)
        phone_to_persons: Dict[str, Set[str]] = {}
        for p in self.person_nodes:
            for _, t, d in self.multi_graph.out_edges(p, data=True):
                if d.get("edge_type") in ["USED_PHONE", "USED_DEVICE"]:
                    phone_to_persons.setdefault(t, set()).add(p)

        for u, v, d in self.multi_graph.edges(data=True):
            if d.get("edge_type") in ["CALLED", "MESSAGED"]:
                p_u = phone_to_persons.get(u, set())
                p_v = phone_to_persons.get(v, set())
                for pu in p_u:
                    for pv in p_v:
                        if pu != pv:
                            pair = tuple(sorted([pu, pv]))
                            self.observed_positive_pairs.add(pair)
                            self.positive_supporting_edges.setdefault(pair, set()).add(self._canonical_edge(u, v))
                            self._record_edge_timestamp(pair, d.get("timestamp"))

    def generate_all_candidates(self) -> List[Dict[str, Any]]:
        """
        Generates the complete dataset of positive and negative candidate links.
        Categories:
        - POSITIVE: Observed evidence-backed ties
        - NEG_A_RANDOM: Random unlinked person pairs
        - NEG_B_SAME_CASE_HARD: Same case dossier, no interaction
        - NEG_C_CROSS_CASE_HARD: Cross-case pairs with similar procedural roles, no interaction
        - NEG_D_SHARED_LOCATION: Connected ONLY via ambient city (e.g. LOC_Delhi_NCR)
        - NEG_E_SHARED_COMMERCIAL_VEHICLE: Connected ONLY via commercial transit bus (VEH_026)
        - NEG_F_SHARED_PUBLIC_IP: Connected ONLY via public Wi-Fi (103.21.244.18)
        - NEG_G_HIGH_DEGREE_HUB: High-degree nodes with zero mutual structural tie
        """
        candidates: List[Dict[str, Any]] = []

        # 1. POSITIVES
        pos_list = sorted(list(self.observed_positive_pairs))
        for p1, p2 in pos_list:
            c1 = self.person_cases.get(p1, set())
            c2 = self.person_cases.get(p2, set())
            sup_edges = sorted([list(e) for e in self.positive_supporting_edges.get((p1, p2), set())])
            candidates.append({
                "source": p1,
                "target": p2,
                "label": 1,
                "category": "POSITIVE",
                "source_cases": "; ".join(sorted(list(c1))),
                "target_cases": "; ".join(sorted(list(c2))),
                "is_cross_case": len(c1 & c2) == 0,
                "supporting_edge_keys": sup_edges,
                "max_timestamp": self.positive_max_timestamp.get((p1, p2), ""),
            })

        num_positives = len(candidates)
        num_neg_needed = num_positives * NEGATIVE_RATIO

        seen_pairs: Set[Tuple[str, str]] = set(pos_list)

        # 2. HARD NEGATIVE TYPE D: Shared Generic Location
        for loc in GENERIC_LOCATIONS:
            if self.multi_graph.has_node(loc):
                loc_persons = [
                    nbr for nbr in self.undirected_g.neighbors(loc)
                    if self.multi_graph.nodes[nbr].get("node_type") == "PERSON"
                ]
                for i in range(len(loc_persons)):
                    for j in range(i + 1, len(loc_persons)):
                        p1, p2 = loc_persons[i], loc_persons[j]
                        pair = tuple(sorted([p1, p2]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            candidates.append({
                                "source": p1, "target": p2, "label": 0,
                                "category": "NEG_D_SHARED_LOCATION",
                                "source_cases": "; ".join(sorted(list(self.person_cases.get(p1, set())))),
                                "target_cases": "; ".join(sorted(list(self.person_cases.get(p2, set())))),
                                "is_cross_case": len(self.person_cases.get(p1, set()) & self.person_cases.get(p2, set())) == 0,
                                "shared_context": loc
                            })

        # 3. HARD NEGATIVE TYPE E: Shared Commercial Vehicle (VEH_026)
        for bus in KNOWN_SHARED_BUSES:
            if self.multi_graph.has_node(bus):
                bus_persons = [
                    nbr for nbr in self.undirected_g.neighbors(bus)
                    if self.multi_graph.nodes[nbr].get("node_type") == "PERSON"
                ]
                for i in range(len(bus_persons)):
                    for j in range(i + 1, len(bus_persons)):
                        p1, p2 = bus_persons[i], bus_persons[j]
                        pair = tuple(sorted([p1, p2]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            candidates.append({
                                "source": p1, "target": p2, "label": 0,
                                "category": "NEG_E_SHARED_COMMERCIAL_VEHICLE",
                                "source_cases": "; ".join(sorted(list(self.person_cases.get(p1, set())))),
                                "target_cases": "; ".join(sorted(list(self.person_cases.get(p2, set())))),
                                "is_cross_case": len(self.person_cases.get(p1, set()) & self.person_cases.get(p2, set())) == 0,
                                "shared_context": bus
                            })

        # 4. HARD NEGATIVE TYPE F: Shared Public Wi-Fi / IP
        for ip in KNOWN_PUBLIC_IPS:
            # Trace devices and entities using this IP to their associated persons
            ip_persons = set()
            for u, v, d in self.multi_graph.edges(data=True):
                if d.get("ip_address") == ip or ip in str(d.get("notes", "")):
                    for n in [u, v]:
                        if self.multi_graph.nodes[n].get("node_type") == "PERSON":
                            ip_persons.add(n)
                        for nbr in self.undirected_g.neighbors(n):
                            if self.multi_graph.nodes[nbr].get("node_type") == "PERSON":
                                ip_persons.add(nbr)
                            for nbr2 in self.undirected_g.neighbors(nbr):
                                if self.multi_graph.nodes[nbr2].get("node_type") == "PERSON":
                                    ip_persons.add(nbr2)
            ip_list = sorted(list(ip_persons))
            for i in range(len(ip_list)):
                for j in range(i + 1, len(ip_list)):
                    p1, p2 = ip_list[i], ip_list[j]
                    pair = tuple(sorted([p1, p2]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        candidates.append({
                            "source": p1, "target": p2, "label": 0,
                            "category": "NEG_F_SHARED_PUBLIC_IP",
                            "source_cases": "; ".join(sorted(list(self.person_cases.get(p1, set())))),
                            "target_cases": "; ".join(sorted(list(self.person_cases.get(p2, set())))),
                            "is_cross_case": len(self.person_cases.get(p1, set()) & self.person_cases.get(p2, set())) == 0,
                            "shared_context": ip
                        })

        # 5. HARD NEGATIVE TYPE G: High-Degree Hubs
        person_degrees = {p: self.undirected_g.degree(p) for p in self.person_nodes}
        top_hubs = sorted(person_degrees.keys(), key=lambda x: person_degrees[x], reverse=True)[:15]
        for i in range(len(top_hubs)):
            for j in range(i + 1, len(top_hubs)):
                p1, p2 = top_hubs[i], top_hubs[j]
                pair = tuple(sorted([p1, p2]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append({
                        "source": p1, "target": p2, "label": 0,
                        "category": "NEG_G_HIGH_DEGREE_HUB",
                        "source_cases": "; ".join(sorted(list(self.person_cases.get(p1, set())))),
                        "target_cases": "; ".join(sorted(list(self.person_cases.get(p2, set())))),
                        "is_cross_case": len(self.person_cases.get(p1, set()) & self.person_cases.get(p2, set())) == 0
                    })

        # 6. HARD NEGATIVE TYPE B: Same-Case Hard Negatives
        case_to_persons: Dict[str, List[str]] = {}
        for p, cases in self.person_cases.items():
            for c in cases:
                case_to_persons.setdefault(c, []).append(p)

        b_count = 0
        target_b = 50
        for c, p_in_case in case_to_persons.items():
            for i in range(len(p_in_case)):
                for j in range(i + 1, len(p_in_case)):
                    if b_count >= target_b:
                        break
                    p1, p2 = p_in_case[i], p_in_case[j]
                    pair = tuple(sorted([p1, p2]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        candidates.append({
                            "source": p1, "target": p2, "label": 0,
                            "category": "NEG_B_SAME_CASE_HARD",
                            "source_cases": c,
                            "target_cases": c,
                            "is_cross_case": False
                        })
                        b_count += 1

        # 7. TYPE A (Random) & TYPE C (Cross-Case Hard) Negatives
        all_p = self.person_nodes
        a_count = 0
        c_count = 0
        target_quota = 50
        attempts = 0
        while (a_count < target_quota or c_count < target_quota) and attempts < 15000:
            attempts += 1
            p1, p2 = self.rng.sample(all_p, 2)
            pair = tuple(sorted([p1, p2]))
            if pair not in seen_pairs:
                c1 = self.person_cases.get(p1, set())
                c2 = self.person_cases.get(p2, set())
                is_cross = len(c1 & c2) == 0
                if is_cross and c_count < target_quota:
                    seen_pairs.add(pair)
                    candidates.append({
                        "source": p1, "target": p2, "label": 0,
                        "category": "NEG_C_CROSS_CASE_HARD",
                        "source_cases": "; ".join(sorted(list(c1))),
                        "target_cases": "; ".join(sorted(list(c2))),
                        "is_cross_case": True
                    })
                    c_count += 1
                elif not is_cross and a_count < target_quota:
                    seen_pairs.add(pair)
                    candidates.append({
                        "source": p1, "target": p2, "label": 0,
                        "category": "NEG_A_RANDOM",
                        "source_cases": "; ".join(sorted(list(c1))),
                        "target_cases": "; ".join(sorted(list(c2))),
                        "is_cross_case": False
                    })
                    a_count += 1

        # Fill remaining NEG_A_RANDOM quota if same-case random draws are exhausted
        while a_count < target_quota and attempts < 25000:
            attempts += 1
            p1, p2 = self.rng.sample(all_p, 2)
            pair = tuple(sorted([p1, p2]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                c1 = self.person_cases.get(p1, set())
                c2 = self.person_cases.get(p2, set())
                candidates.append({
                    "source": p1, "target": p2, "label": 0,
                    "category": "NEG_A_RANDOM",
                    "source_cases": "; ".join(sorted(list(c1))),
                    "target_cases": "; ".join(sorted(list(c2))),
                    "is_cross_case": len(c1 & c2) == 0
                })
                a_count += 1

        return candidates

    @staticmethod
    def collect_supporting_edges(pairs: List[Dict[str, Any]]) -> Set[Tuple[str, str]]:
        """Collect canonical undirected edge tuples supporting the given positive pairs."""
        excluded: Set[Tuple[str, str]] = set()
        for p in pairs:
            if p.get("label") == 1:
                for edge_pair in p.get("supporting_edge_keys", []) or []:
                    if len(edge_pair) == 2:
                        u, v = edge_pair
                        excluded.add((u, v) if u <= v else (v, u))
        return excluded
