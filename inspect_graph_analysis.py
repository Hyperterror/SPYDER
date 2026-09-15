"""
Inspection and Execution Script for Phase 3: Global Case Knowledge Graph + Network Analysis.
Builds the complete Knowledge Graph, runs network analytics, discovers cross-case trails,
exports all deliverables to output/graph_analysis/, runs internal evaluation, and displays
structured summary tables in the console.
"""

import sys
from pathlib import Path

# Add workspace to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from graph_analysis import (
    GraphBuilder, CentralityAnalyzer, CommunityAnalyzer,
    CrossCaseDetector, KnowledgeGraphEvaluator, GraphExporter
)

def run_phase_3_pipeline():
    print("\n" + "=" * 80)
    print(" " * 20 + "PHASE 3: GLOBAL CASE KNOWLEDGE GRAPH")
    print("=" * 80)

    # 1. Build Global Knowledge Graph
    print("\n[1/6] Building Global Evidence-Backed Knowledge Graph...")
    builder = GraphBuilder()
    multi_graph = builder.build_global_graph()
    projected_graph = builder.build_projected_entity_graph()
    summary_stats = builder.get_summary_stats()

    print(f" -> Total Graph Nodes: {summary_stats['total_nodes']:,}")
    print(f" -> Total Graph Edges: {summary_stats['total_edges']:,}")
    print(f" -> Connected Components: {summary_stats['num_connected_components']}")
    print(f" -> Provisional Resolved Entities: {summary_stats['num_provisional_resolved_entities']}")

    print("\nNodes by Type:")
    for ntype, count in sorted(summary_stats["nodes_by_type"].items()):
        print(f"    - {ntype:<16}: {count:>5}")

    print("\nEdges by Type:")
    for etype, count in sorted(summary_stats["edges_by_type"].items()):
        print(f"    - {etype:<26}: {count:>5}")

    # 2. Centrality Analytics
    print("\n[2/6] Computing Network Centrality & Bridge Metrics...")
    centrality_analyzer = CentralityAnalyzer(multi_graph, projected_graph)
    node_metrics = centrality_analyzer.calculate_node_metrics()

    top_degree_persons = centrality_analyzer.get_top_entities_by_metric("raw_degree", "PERSON", top_k=10)
    top_betweenness_persons = centrality_analyzer.get_top_entities_by_metric("betweenness_centrality", "PERSON", top_k=10)
    top_pagerank_persons = centrality_analyzer.get_top_entities_by_metric("pagerank", "PERSON", top_k=10)

    print("\nTop 10 PERSON Nodes by Degree:")
    print(f"    {'Node ID':<20} {'Label':<30} {'Degree':<8} {'Priority Status':<25}")
    print("    " + "-" * 85)
    for m in top_degree_persons:
        print(f"    {m['node_id']:<20} {m['label'][:28]:<30} {m['raw_degree']:<8} {m['priority_status']:<25}")

    print("\nTop 10 PERSON Nodes by Betweenness Centrality:")
    print(f"    {'Node ID':<20} {'Label':<30} {'Betweenness':<12} {'Analytical Tags':<25}")
    print("    " + "-" * 90)
    for m in top_betweenness_persons:
        print(f"    {m['node_id']:<20} {m['label'][:28]:<30} {m['betweenness_centrality']:<12.6f} {m['analytical_tags']:<25}")

    print("\nTop 10 PERSON Nodes by PageRank:")
    print(f"    {'Node ID':<20} {'Label':<30} {'PageRank':<12} {'Case Count':<10}")
    print("    " + "-" * 75)
    for m in top_pagerank_persons:
        print(f"    {m['node_id']:<20} {m['label'][:28]:<30} {m['pagerank']:<12.6f} {m['case_count']:<10}")

    # 3. Community Detection
    print("\n[3/6] Detecting Investigative Clusters (Observable Communities)...")
    community_analyzer = CommunityAnalyzer(projected_graph, multi_graph)
    communities = community_analyzer.detect_communities()
    print(f" -> Total Detected Communities: {len(communities)}")
    for comm in communities[:5]:
        print(f"    [{comm['community_id']}] {comm['cluster_label']}: {comm['total_nodes']} nodes "
              f"({comm['num_persons']} persons, {comm['num_cases']} cases) | Top: {comm['top_connected_nodes']}")

    # 4. Cross-Case Connection Discovery
    print("\n[4/6] Discovering Cross-Case Multi-Hop Connections...")
    cross_case_detector = CrossCaseDetector(multi_graph, projected_graph)
    connections = cross_case_detector.find_cross_case_connections()
    print(f" -> Total Discovered Cross-Case Paths: {len(connections)}")

    high_priority_leads = [c for c in connections if c.tier == "HIGH-PRIORITY LEAD"]
    review_leads = [c for c in connections if c.tier == "REVIEW"]
    print(f"    - HIGH-PRIORITY LEADS : {len(high_priority_leads)}")
    print(f"    - REVIEW LEADS        : {len(review_leads)}")
    print(f"    - LOW PRIORITY        : {len(connections) - len(high_priority_leads) - len(review_leads)}")

    print("\nExample Cross-Case Connections & Evidence Explanations:")
    for idx, c in enumerate(connections[:3], 1):
        print(f"\n--- Lead #{idx} [{c.tier}] (Score: {c.score:.3f}) ---")
        print(f"Path: {c.path}")
        print(f"Connecting Entities: {'; '.join(c.connecting_entities)}")
        print(f"Explanation:\n{c.explanation}")

    # 5. Export Deliverables to output/graph_analysis/
    print("\n[5/6] Exporting Graph Artifacts to output/graph_analysis/...")
    exporter = GraphExporter()
    exporter.export_nodes_csv(builder.nodes)
    exporter.export_edges_csv(builder.edges)
    exporter.export_case_graph_json(multi_graph)
    exporter.export_cross_case_connections_csv(connections)
    exporter.export_node_metrics_csv(node_metrics)
    exporter.export_communities_csv(communities)
    exporter.export_graph_summary_json(summary_stats)
    print(" -> Successfully exported nodes.csv, edges.csv, case_graph.json,")
    print("    cross_case_connections.csv, node_metrics.csv, communities.csv, graph_summary.json")

    # 6. Internal Evaluation
    print("\n[6/6] Running Internal Ground-Truth Evaluation...")
    evaluator = KnowledgeGraphEvaluator()
    edges_dicts = [e.to_dict() for e in builder.edges]
    eval_report = evaluator.evaluate_all(connections, node_metrics, communities, edges_dicts)
    
    cd = eval_report["cross_case_detection"]
    bd = eval_report["bridge_entity_detection"]
    cs = eval_report["community_syndicate_overlap"]
    pc = eval_report["provenance_completeness"]

    print("\n" + "=" * 80)
    print(" " * 25 + "EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Cross-Case Connection Discovery Precision : {cd['precision']:.4f}")
    print(f"Cross-Case Connection Discovery Recall    : {cd['recall']:.4f}")
    print(f"Cross-Case Connection Discovery F1 Score  : {cd['f1_score']:.4f}")
    print(f"High-Priority Lead Precision              : {cd['high_priority_precision']:.4f}")
    print(f"Cross-Case Bridge Entity Recall           : {bd['bridge_recall']:.4f}")
    print(f"Community / Syndicate Overlap (ARI)       : {cs['adjusted_rand_index']:.4f}")
    print(f"Community / Syndicate Overlap (NMI)       : {cs['normalized_mutual_info']:.4f}")
    print(f"Evidence Provenance Completeness Rate     : {pc['provenance_rate'] * 100:.2f}%")
    print(" -> Detailed report written to output/graph_analysis/evaluation_report.md")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_phase_3_pipeline()
