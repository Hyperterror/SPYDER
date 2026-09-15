"""
Graph Builder for Global Case Knowledge Graph.
Assembles the complete evidence-backed MultiDiGraph and builds a projected entity graph
for network analytics and cross-case traversal.
"""

from typing import Dict, List, Set, Any, Optional, Tuple
from collections import Counter
import networkx as nx

from graph_analysis.schema import NodeType, EdgeType, GraphNode, GraphEdge
from graph_analysis.node_builder import NodeBuilder
from graph_analysis.edge_builder import EdgeBuilder

class GraphBuilder:
    def __init__(self):
        self.node_builder = NodeBuilder()
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self.multi_graph: Optional[nx.MultiDiGraph] = None
        self.projected_graph: Optional[nx.Graph] = None

    def build_global_graph(self) -> nx.MultiDiGraph:
        """
        Builds the global evidence-backed MultiDiGraph preserving every observation,
        timestamp, and provenance record.
        """
        self.nodes = self.node_builder.build_all_nodes()
        edge_builder = EdgeBuilder(self.nodes)
        self.edges = edge_builder.build_all_edges()

        g = nx.MultiDiGraph()

        # Add nodes with all attributes
        for n_id, node in self.nodes.items():
            g.add_node(n_id, **node.to_dict())

        # Add edges with provenance
        for edge in self.edges:
            # If source or target node not in graph, create a basic node
            if not g.has_node(edge.source_id):
                g.add_node(edge.source_id, node_id=edge.source_id, node_type="UNKNOWN", label=edge.source_id)
            if not g.has_node(edge.target_id):
                g.add_node(edge.target_id, node_id=edge.target_id, node_type="UNKNOWN", label=edge.target_id)

            g.add_edge(
                edge.source_id,
                edge.target_id,
                key=f"{edge.edge_type.value}_{edge.provenance.source_id}",
                **edge.to_dict()
            )

        self.multi_graph = g
        return self.multi_graph

    def build_projected_entity_graph(self) -> nx.Graph:
        """
        Builds an undirected, weighted projected graph of cases and entities.
        Aggregates multi-edges and preserves maximum weight, evidence count,
        and connecting evidence modalities.
        """
        if self.multi_graph is None:
            self.build_global_graph()

        p_graph = nx.Graph()

        # Copy all nodes
        for n, d in self.multi_graph.nodes(data=True):
            p_graph.add_node(n, **d)

        # Aggregate edges
        for u, v, k, data in self.multi_graph.edges(keys=True, data=True):
            if u == v:
                continue

            if p_graph.has_edge(u, v):
                edata = p_graph[u][v]
                edata["weight"] = max(edata["weight"], data.get("weight", 1.0))
                edata["evidence_count"] += 1
                edata["edge_types"].add(data.get("edge_type"))
                if data.get("timestamp"):
                    edata["timestamps"].append(data["timestamp"])
                edata["provenance_records"].append({
                    "table": data.get("provenance_table"),
                    "id": data.get("provenance_record_id"),
                    "case": data.get("provenance_case_id")
                })
            else:
                p_graph.add_edge(
                    u, v,
                    weight=data.get("weight", 1.0),
                    evidence_count=1,
                    edge_types={data.get("edge_type")},
                    timestamps=[data["timestamp"]] if data.get("timestamp") else [],
                    provenance_records=[{
                        "table": data.get("provenance_table"),
                        "id": data.get("provenance_record_id"),
                        "case": data.get("provenance_case_id")
                    }]
                )

        self.projected_graph = p_graph
        return self.projected_graph

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates global structural metrics of the Knowledge Graph."""
        if self.multi_graph is None:
            self.build_global_graph()

        node_types_count = Counter()
        for _, d in self.multi_graph.nodes(data=True):
            node_types_count[d.get("node_type", "UNKNOWN")] += 1

        edge_types_count = Counter()
        for _, _, d in self.multi_graph.edges(data=True):
            edge_types_count[d.get("edge_type", "UNKNOWN")] += 1

        # Undirected projection for connected components
        undirected_g = self.multi_graph.to_undirected()
        components = list(nx.connected_components(undirected_g))

        return {
            "total_nodes": self.multi_graph.number_of_nodes(),
            "total_edges": self.multi_graph.number_of_edges(),
            "nodes_by_type": dict(node_types_count),
            "edges_by_type": dict(edge_types_count),
            "num_connected_components": len(components),
            "largest_component_size": len(max(components, key=len)) if components else 0,
            "num_provisional_resolved_entities": len(self.node_builder.resolved_clusters)
        }
