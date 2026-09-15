"""
Comprehensive Unit and Integration Test Suite for Phase 3:
Global Case Knowledge Graph and Network Analytics.
Validates node/edge construction, zero ground-truth leakage, provenance completeness,
transitive ER safeguards, context-aware identifier reliability, centrality, communities,
cross-case discovery, and neutral explanation generation.
"""

import unittest
from pathlib import Path
import networkx as nx

from graph_analysis.config import (
    EVIDENCE_DIR, ER_PREDICTIONS_PATH, KNOWN_PUBLIC_IPS, KNOWN_PUBLIC_ACCOUNTS,
    KNOWN_PUBLIC_PHONES
)
from graph_analysis.schema import NodeType, EdgeType, GraphNode, GraphEdge
from graph_analysis.node_builder import NodeBuilder
from graph_analysis.edge_builder import EdgeBuilder
from graph_analysis.graph_builder import GraphBuilder
from graph_analysis.temporal import TemporalEngine
from graph_analysis.centrality import CentralityAnalyzer
from graph_analysis.communities import CommunityAnalyzer
from graph_analysis.cross_case import CrossCaseDetector
from graph_analysis.explanations import generate_cross_case_explanation

class TestGraphAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = GraphBuilder()
        cls.multi_graph = cls.builder.build_global_graph()
        cls.projected_graph = cls.builder.build_projected_entity_graph()

    def test_01_all_10_node_types_created(self):
        """Validates that all 10 required observable node types exist in the knowledge graph."""
        node_types = {d.get("node_type") for _, d in self.multi_graph.nodes(data=True)}
        expected_types = {
            "PERSON", "VICTIM", "CASE", "PHONE", "DEVICE",
            "VEHICLE", "BANK_ACCOUNT", "SOCIAL_ACCOUNT", "LOCATION", "EVIDENCE"
        }
        for expected in expected_types:
            self.assertIn(expected, node_types, f"Node type {expected} missing from graph")

    def test_02_zero_ground_truth_contamination(self):
        """
        CRITICAL AUDIT: Asserts that latent ground truth (GLOBAL_ENTITY_ID, true_role, syndicate)
        is NEVER leaked into graph node attributes, edges, or labels.
        """
        forbidden_substrings = ["GLOBAL_ENT", "GLOBAL_ENTITY", "mastermind", "syndicate head", "NETWORK_ALPHA", "NETWORK_BETA"]
        
        # Check node attributes
        for n_id, d in self.multi_graph.nodes(data=True):
            for sub in forbidden_substrings:
                self.assertNotIn(sub, n_id, f"Ground truth token {sub} leaked into node ID: {n_id}")
                label = str(d.get("label", ""))
                self.assertNotIn(sub, label, f"Ground truth token {sub} leaked into node label: {label}")
                # Ensure true_role is not present
                self.assertNotIn("true_role", d, f"Latent true_role found in node {n_id}")
                self.assertNotIn("network_cluster", d, f"Latent network_cluster found in node {n_id}")

        # Check edge attributes
        for u, v, k, d in self.multi_graph.edges(keys=True, data=True):
            notes = str(d.get("notes", ""))
            for sub in forbidden_substrings:
                self.assertNotIn(sub, notes, f"Ground truth token {sub} leaked into edge notes between {u} and {v}")

    def test_03_provenance_preservation(self):
        """Verifies that every edge carries strict provenance (table, record ID, and case ID)."""
        edges_checked = 0
        for u, v, k, d in self.multi_graph.edges(keys=True, data=True):
            self.assertIn("provenance_table", d, f"Missing provenance_table on edge {u}->{v}")
            self.assertIsNotNone(d["provenance_table"], f"Null provenance_table on edge {u}->{v}")
            self.assertIn("provenance_record_id", d, f"Missing provenance_record_id on edge {u}->{v}")
            self.assertIn("provenance_case_id", d, f"Missing provenance_case_id on edge {u}->{v}")
            self.assertGreaterEqual(d.get("weight", 0), 0.0)
            self.assertLessEqual(d.get("weight", 0), 1.0)
            edges_checked += 1

        self.assertGreater(edges_checked, 1000, "Insufficient edges in graph")

    def test_04_provisional_er_clustering_safeguards(self):
        """
        SAFEGUARD 1: Validates that provisional ER clusters preserve pairwise probabilities,
        compute cohesion and diameter, and track transitivity.
        """
        nb = NodeBuilder()
        clusters = nb.build_provisional_resolved_entities()
        self.assertGreater(len(clusters), 0, "No provisional ER clusters formed")

        for c_id, meta in clusters.items():
            # Preserves pairwise predictions
            self.assertGreater(len(meta.pairwise_links), 0, f"No pairwise links recorded for {c_id}")
            self.assertGreaterEqual(meta.cohesion_score, 0.80, f"Low cohesion in {c_id}")
            self.assertGreaterEqual(meta.min_pair_probability, 0.85, f"Low min pair prob in {c_id}")
            self.assertIsInstance(meta.is_transitive, bool)
            self.assertGreaterEqual(meta.cluster_diameter, 1)

            # Node representation
            node = nb.nodes.get(c_id)
            self.assertIsNotNone(node, f"Node for cluster {c_id} was not created")
            self.assertTrue(node.attributes["is_provisional_resolved"])
            # Label must be neutral
            self.assertNotIn("criminal", node.label.lower())
            self.assertNotIn("syndicate", node.label.lower())

    def test_05_er_transitive_conflict_prevention(self):
        """
        SAFEGUARD 1: Asserts that if pair A-C has low probability / conflict,
        A and C are NOT silently merged into a single unquestioned cluster.
        """
        nb = NodeBuilder()
        # Mock pairwise predictions with an intransitive conflict: A-B=0.96, B-C=0.95, A-C=0.42
        nb.pairwise_predictions = {
            ("P_TEST_A", "P_TEST_B"): {
                "person_id_a": "P_TEST_A", "person_id_b": "P_TEST_B",
                "match_probability": 0.96, "confidence_tier": "HIGH CONFIDENCE",
                "explanation_summary": "Test match", "supporting_reasons": "IMEI",
                "conflicting_reasons": "", "case_id_a": "CASE_001", "case_id_b": "CASE_002"
            },
            ("P_TEST_B", "P_TEST_C"): {
                "person_id_a": "P_TEST_B", "person_id_b": "P_TEST_C",
                "match_probability": 0.95, "confidence_tier": "HIGH CONFIDENCE",
                "explanation_summary": "Test match", "supporting_reasons": "IMEI",
                "conflicting_reasons": "", "case_id_a": "CASE_002", "case_id_b": "CASE_003"
            },
            ("P_TEST_A", "P_TEST_C"): {
                "person_id_a": "P_TEST_A", "person_id_b": "P_TEST_C",
                "match_probability": 0.42, "confidence_tier": "LOW CONFIDENCE",
                "explanation_summary": "Conflict", "supporting_reasons": "",
                "conflicting_reasons": "Divergent biometric and temporal location",
                "case_id_a": "CASE_001", "case_id_b": "CASE_003"
            }
        }
        clusters = nb.build_provisional_resolved_entities()
        
        # Verify that P_TEST_A and P_TEST_C are not in the same monolithic unflagged cluster
        for c_id, meta in clusters.items():
            if "P_TEST_A" in meta.member_person_ids:
                self.assertNotIn(
                    "P_TEST_C", meta.member_person_ids,
                    "Conflicting entities P_TEST_A and P_TEST_C were silently merged!"
                )

    def test_06_context_aware_public_infrastructure_penalty(self):
        """
        SAFEGUARD 2: Confirmed public transit Wi-Fi IPs, utility accounts, and public helplines
        must receive heavily discounted reliability scores.
        """
        nodes = self.builder.nodes
        eb = EdgeBuilder(nodes)
        
        # Check public IP confidence
        conf_public_ip = eb._compute_contextual_confidence("IP_ADDRESS", "103.21.244.18")
        self.assertLessEqual(conf_public_ip, 0.20, "Public Wi-Fi IP was not appropriately penalized")

        # Check public utility account confidence
        conf_public_acc = eb._compute_contextual_confidence("BANK_ACCOUNT", "ACC_SBI_IRCTC_099")
        self.assertLessEqual(conf_public_acc, 0.20, "Public utility account was not appropriately penalized")

        # Check public helpline phone
        conf_public_phone = eb._compute_contextual_confidence("PHONE_NUMBER", "+911123010000")
        self.assertLessEqual(conf_public_phone, 0.20, "Public helpline phone was not appropriately penalized")

    def test_07_context_aware_identifier_fanout_penalty(self):
        """
        SAFEGUARD 2: Identifiers used across many unrelated records/persons (high fan-out)
        must receive down-weighted confidence compared to isolated direct identifiers.
        """
        nodes = self.builder.nodes
        eb = EdgeBuilder(nodes)
        eb.identifier_usage_counts["REG_TEST_FLEET"] = 12
        eb.identifier_usage_counts["REG_TEST_SOLITARY"] = 1

        conf_fleet = eb._compute_contextual_confidence("VEHICLE_REG", "REG_TEST_FLEET")
        conf_solitary = eb._compute_contextual_confidence("VEHICLE_REG", "REG_TEST_SOLITARY")

        self.assertLess(conf_fleet, conf_solitary, "Shared fleet vehicle was not penalized for high fan-out")

    def test_08_temporal_engine_filtering(self):
        """PHASE 3B: Tests temporal interval slicing and incident-centered queries."""
        te = TemporalEngine(self.multi_graph)
        
        # Test temporal slice
        slice_g = te.filter_subgraph_by_time("2025-02-01 00:00:00", "2025-02-15 23:59:59")
        self.assertIsInstance(slice_g, nx.MultiDiGraph)
        self.assertGreater(slice_g.number_of_edges(), 0)

        # Test incident connection query
        incident_conns = te.get_connections_around_incident("2025-02-10 12:00:00", pre_days=3, post_days=3)
        self.assertIsInstance(incident_conns, list)
        for conn in incident_conns:
            self.assertIn("timestamp", conn)
            self.assertIn("case_id", conn)

    def test_09_centrality_metrics_and_neutral_terminology(self):
        """PHASE 3C: Verifies centrality metrics and ensures strictly neutral terminology."""
        analyzer = CentralityAnalyzer(self.multi_graph, self.projected_graph)
        metrics = analyzer.calculate_node_metrics()
        self.assertGreater(len(metrics), 0)

        for m in metrics:
            self.assertIn("degree_centrality", m)
            self.assertIn("betweenness_centrality", m)
            self.assertIn("pagerank", m)
            self.assertIn("analytical_tags", m)
            
            # Neutrality check
            tags = m["analytical_tags"].lower()
            self.assertNotIn("mastermind", tags)
            self.assertNotIn("criminal", tags)
            self.assertNotIn("guilty", tags)
            self.assertNotIn("syndicate", tags)

    def test_10_community_detection(self):
        """PHASE 3F: Verifies observable community clustering and profiling."""
        analyzer = CommunityAnalyzer(self.projected_graph, self.multi_graph)
        communities = analyzer.detect_communities()
        self.assertGreater(len(communities), 0, "No communities detected")

        for comm in communities:
            self.assertIn("community_id", comm)
            self.assertIn("num_persons", comm)
            self.assertIn("num_cases", comm)
            self.assertIn("cases_represented", comm)
            self.assertIn("analytical_classification", comm)
            # Neutral terminology
            self.assertNotIn("syndicate", comm["cluster_label"].lower())

    def test_11_cross_case_discovery_and_scoring(self):
        """PHASE 3D & 3E: Verifies multi-hop path finding, scoring, and priority tiers."""
        detector = CrossCaseDetector(self.multi_graph, self.projected_graph)
        connections = detector.find_cross_case_connections()
        self.assertGreater(len(connections), 0, "No cross-case paths found")

        for conn in connections:
            self.assertNotEqual(conn.source_case, conn.target_case)
            self.assertGreaterEqual(conn.score, 0.0)
            self.assertLessEqual(conn.score, 1.0)
            self.assertIn(conn.tier, ["HIGH-PRIORITY LEAD", "REVIEW", "LOW PRIORITY"])
            self.assertGreater(len(conn.reasons), 0)
            self.assertGreater(len(conn.explanation), 20)
            # Neutrality check
            self.assertNotIn("syndicate", conn.explanation.lower())

    def test_12_isolated_nodes_handling(self):
        """Tests that isolated nodes with no edges are gracefully handled without crashing."""
        test_graph = nx.MultiDiGraph()
        test_graph.add_node("ISOLATED_NODE_01", node_type="PERSON", label="Isolated Person")
        analyzer = CentralityAnalyzer(test_graph, test_graph.to_undirected())
        metrics = analyzer.calculate_node_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["raw_degree"], 0)

    def test_13_duplicate_edges_handling(self):
        """Tests that duplicate observational records are aggregated with frequency tracking."""
        projected = self.projected_graph
        # Verify projected graph contains aggregated evidence counts
        for u, v, d in projected.edges(data=True):
            self.assertGreaterEqual(d.get("evidence_count", 0), 1)
            self.assertIsInstance(d.get("edge_types"), set)

    def test_14_explanation_generation_fidelity(self):
        """Verifies that generated narrative explanations cite observable source tables."""
        explanation = generate_cross_case_explanation(
            source_case="CASE_001",
            target_case="CASE_003",
            path_nodes=["CASE_001", "CASE_001_PER_01", "DEV_001", "CASE_003_PER_01", "CASE_003"],
            relationship_types=["APPEARS_IN", "USED_DEVICE"],
            supporting_evidence=[
                {"table": "device_logs.csv", "id": "DEV_001_861990", "confidence": 0.95},
                {"table": "persons.csv", "id": "CASE_001_PER_01", "confidence": 1.0}
            ],
            connecting_entities=["CASE_001_PER_01", "DEV_001", "CASE_003_PER_01"],
            tier="HIGH-PRIORITY LEAD",
            reasons=["Direct hardware identifier (IMEI) match", "Multi-modal corroboration"]
        )
        self.assertIn("CASE_001", explanation)
        self.assertIn("CASE_003", explanation)
        self.assertIn("device_logs.csv", explanation)
        self.assertIn("HIGH-PRIORITY LEAD", explanation)
        self.assertNotIn("syndicate", explanation.lower())

if __name__ == "__main__":
    unittest.main()
