"""
Community Analysis Module.
Detects observable structural network clusters using modularity-based community detection
and generates investigative cluster profiles with strictly neutral, objective terminology.
"""

from typing import Dict, List, Set, Any, Optional
from collections import Counter
import networkx as nx

class CommunityAnalyzer:
    def __init__(self, projected_graph: nx.Graph, multi_graph: Optional[nx.MultiDiGraph] = None):
        self.projected_graph = projected_graph
        self.multi_graph = multi_graph

    def _build_person_interaction_graph(self) -> nx.Graph:
        """
        Constructs a projected person-level interaction network where edges represent
        direct operational connections: communication (calls/chats), financial transfers,
        shared hardware devices, or provisional entity resolution clustering.
        Intermediate infrastructure is weighted inversely to its fan-out (penalizing public/shared transit).
        """
        person_graph = nx.Graph()
        
        # Add all PERSON nodes (observational persons and provisional resolved entities)
        for n, d in self.projected_graph.nodes(data=True):
            if d.get("node_type") == "PERSON":
                person_graph.add_node(n, **d)

        # Connect persons via shared intermediate entities
        # Also connect persons directly linked to the same provisional resolved entity
        for n, d in self.projected_graph.nodes(data=True):
            ntype = d.get("node_type")
            if ntype in ["PHONE", "DEVICE", "VEHICLE", "BANK_ACCOUNT", "SOCIAL_ACCOUNT", "PERSON"]:
                # Find all PERSON neighbors
                person_nbrs = [
                    nbr for nbr in self.projected_graph.neighbors(n)
                    if self.projected_graph.nodes[nbr].get("node_type") == "PERSON"
                ]
                
                if len(person_nbrs) < 2:
                    continue

                # Context-aware weighting: if intermediate is shared by many persons, downweight heavily
                deg = len(person_nbrs)
                if deg > 6:
                    weight_factor = 0.05  # Mass transit bus / shared public infrastructure
                elif deg > 3:
                    weight_factor = 0.20  # Commercial vehicle / shared terminal
                else:
                    weight_factor = 1.0   # Private/dedicated co-usage

                if ntype == "DEVICE" or "IMEI_" in n:
                    weight_factor *= 1.5
                if d.get("is_provisional_resolved"):
                    weight_factor *= 2.0

                for i in range(len(person_nbrs)):
                    for j in range(i + 1, len(person_nbrs)):
                        p1, p2 = person_nbrs[i], person_nbrs[j]
                        edge_w = weight_factor
                        if person_graph.has_edge(p1, p2):
                            person_graph[p1][p2]["weight"] += edge_w
                            person_graph[p1][p2]["evidence_types"].add(ntype)
                        else:
                            person_graph.add_edge(p1, p2, weight=edge_w, evidence_types={ntype})

        return person_graph

    def detect_communities(self) -> List[Dict[str, Any]]:
        """
        Applies modularity community detection (Louvain or Greedy Modularity)
        on the person interaction network and profiles each detected investigative cluster.
        """
        person_graph = self._build_person_interaction_graph()
        connected_nodes = [n for n, deg in person_graph.degree() if deg > 0]
        subgraph = person_graph.subgraph(connected_nodes)

        if subgraph.number_of_nodes() == 0:
            return []

        try:
            communities_generator = nx.community.louvain_communities(subgraph, weight="weight", seed=42)
            raw_communities = list(communities_generator)
        except Exception:
            raw_communities = list(nx.community.greedy_modularity_communities(subgraph, weight="weight"))

        # Sort communities by size descending
        raw_communities.sort(key=len, reverse=True)

        community_summaries = []
        comm_idx = 1

        for comm_nodes in raw_communities:
            node_list = list(comm_nodes)
            comm_subgraph = self.projected_graph.subgraph(node_list)

            # Analyze composition
            persons = [n for n in node_list if comm_subgraph.nodes[n].get("node_type") == "PERSON"]
            cases_represented = set()
            evidence_types = set()

            for n in node_list:
                ndata = comm_subgraph.nodes[n]
                c_ids = ndata.get("case_ids", [])
                if isinstance(c_ids, (list, set)):
                    cases_represented.update(c_ids)

            # Extract evidence types from internal edges
            for u, v, d in comm_subgraph.edges(data=True):
                e_types = d.get("edge_types", set())
                evidence_types.update(e_types)

            # Centrality within cluster
            deg_map = dict(comm_subgraph.degree())
            sorted_by_deg = sorted(node_list, key=lambda x: deg_map.get(x, 0), reverse=True)
            top_nodes = sorted_by_deg[:5]

            # Cross-case bridges within cluster
            cross_case_nodes = []
            for n in node_list:
                c_ids = comm_subgraph.nodes[n].get("case_ids", [])
                if len(c_ids) >= 2:
                    cross_case_nodes.append(n)

            avg_deg = sum(deg_map.values()) / max(1, len(node_list))
            
            cluster_id = f"COMM_{comm_idx:03d}"
            community_summaries.append({
                "community_id": cluster_id,
                "cluster_label": f"Investigative Cluster {cluster_id}",
                "total_nodes": len(node_list),
                "num_persons": len(persons),
                "num_cases": len(cases_represented),
                "cases_represented": "; ".join(sorted(list(cases_represented))),
                "cross_case_bridges_count": len(cross_case_nodes),
                "cross_case_bridge_nodes": "; ".join(cross_case_nodes[:5]),
                "top_connected_nodes": "; ".join(top_nodes),
                "mean_internal_degree": round(avg_deg, 2),
                "evidence_modalities": "; ".join(sorted([str(e) for e in evidence_types if e])),
                "member_nodes": node_list,
                "analytical_classification": "cross-case connected group" if len(cases_represented) > 1 else "local case cluster"
            })
            comm_idx += 1

        return community_summaries
