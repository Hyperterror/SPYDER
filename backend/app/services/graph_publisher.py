"""
Atomic Graph Publication & Versioned Snapshot Service (Milestone 2).

Guarantees:
1. Never mutates synthetic_data_generator/output/evidence_dataset/*.csv.
2. Builds candidate graph in an isolated staging snapshot directory from:
   - Read-only baseline dataset (when enabled/present)
   - Authoritative PostgreSQL ParsedRecord rows belonging ONLY to ACTIVE EvidenceItems
     (excluding SUPERSEDED and WITHDRAWN evidence).
3. Validates graph structure and provenance before atomic activation.
4. Atomically swaps active pointers (GraphSnapshot DB row + active_snapshot.json + output files).
5. Preserves previous valid snapshot on failure for instant rollback.
6. Optionally syncs active graph to Neo4j without failing the evidence core if Neo4j is down.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceItem, ParsedRecord
from app.models.graph import GraphSnapshot
from app.models.intelligence import IdentityHypothesis
from graph_analysis.config import EVIDENCE_DIR, OUTPUT_DIR as GRAPH_OUTPUT_DIR
from graph_analysis.export import GraphExporter
from graph_analysis.graph_builder import GraphBuilder
from graph_analysis.schema import EdgeType, GraphEdge, GraphNode, NodeType, ProvenanceRecord


_PUBLISH_LOCK = threading.Lock()


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _overlay_db_records_onto_graph(
    graph_builder: GraphBuilder,
    candidate_graph: nx.MultiDiGraph,
    db: Session,
) -> int:
    """
    Overlay all VALID ParsedRecord rows from ACTIVE EvidenceItems in PostgreSQL
    onto the candidate graph with complete source provenance.
    Returns count of overlaid records.
    """
    rows = (
        db.query(ParsedRecord, EvidenceItem)
        .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
        .filter(
            ParsedRecord.parse_status == "VALID",
            EvidenceItem.lifecycle_status == "ACTIVE",
        )
        .all()
    )

    overlaid = 0
    for rec, ev in rows:
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        case_str = str(rec.case_id)
        ev_str = str(rec.evidence_id)
        src_table = ev.sanitized_filename or ev.original_filename or "db_parsed_records"
        rec_ref = f"DB:{ev_str}:{rec.source_row_number}"

        def _ensure_node(node_id: str, node_type: NodeType, label: str, attrs: Optional[dict] = None):
            if node_id not in graph_builder.nodes:
                gn = GraphNode(
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    case_ids={case_str},
                    attributes=attrs or {},
                )
                graph_builder.nodes[node_id] = gn
                candidate_graph.add_node(node_id, **gn.to_dict())
            else:
                graph_builder.nodes[node_id].case_ids.add(case_str)
                if candidate_graph.has_node(node_id):
                    existing_cases = set(candidate_graph.nodes[node_id].get("case_ids", []))
                    existing_cases.add(case_str)
                    candidate_graph.nodes[node_id]["case_ids"] = sorted(list(existing_cases))

        def _add_edge(src: str, tgt: str, etype: EdgeType, ts: Optional[str] = None, attrs: Optional[dict] = None):
            prov = ProvenanceRecord(
                source_table=src_table,
                source_id=rec_ref,
                case_id=case_str,
                timestamp=ts,
                evidence_type=rec.record_type,
                confidence=1.0,
                notes=f"sha256={ev.sha256_hash}; row={rec.source_row_number}; ver={rec.evidence_version}",
            )
            ge = GraphEdge(
                source_id=src,
                target_id=tgt,
                edge_type=etype,
                provenance=prov,
                timestamp=ts,
                weight=1.0,
                attributes=attrs or {},
            )
            graph_builder.edges.append(ge)
            candidate_graph.add_edge(
                src,
                tgt,
                key=f"{etype.value}_{rec_ref}",
                **ge.to_dict(),
            )

        if rec.record_type == "CDR":
            caller = nr.get("calling_number")
            callee = nr.get("called_number")
            ts = nr.get("start_time_utc")
            if caller and callee:
                _ensure_node(caller, NodeType.PHONE, f"Phone {caller}", {"phone_number": caller})
                _ensure_node(callee, NodeType.PHONE, f"Phone {callee}", {"phone_number": callee})
                _add_edge(caller, callee, EdgeType.CALLED, ts, {"duration_seconds": nr.get("duration_seconds")})
                if nr.get("tower_id"):
                    twr = f"LOC_{nr['tower_id']}"
                    _ensure_node(twr, NodeType.LOCATION, f"Tower {nr['tower_id']}", {"tower_id": nr["tower_id"]})
                    _add_edge(caller, twr, EdgeType.OPERATES_IN, ts)
                overlaid += 1

        elif rec.record_type == "TRANSACTION":
            sender = nr.get("sender_identifier")
            receiver = nr.get("receiver_identifier")
            ts = nr.get("timestamp_utc")
            if sender and receiver:
                _ensure_node(sender, NodeType.BANK_ACCOUNT, f"Account {sender}", {"account_id": sender})
                _ensure_node(receiver, NodeType.BANK_ACCOUNT, f"Account {receiver}", {"account_id": receiver})
                _add_edge(sender, receiver, EdgeType.TRANSFERRED_MONEY, ts, {
                    "amount": nr.get("amount"),
                    "currency": nr.get("currency", "INR"),
                    "transaction_type": nr.get("transaction_type"),
                })
                overlaid += 1

        elif rec.record_type == "TRAVEL":
            pid = nr.get("person_id")
            dest = nr.get("destination")
            ts = nr.get("departure_time_utc")
            if pid and dest:
                loc_id = f"LOC_{dest.replace(' ', '_')}"
                _ensure_node(pid, NodeType.PERSON, pid, {"person_id": pid})
                _ensure_node(loc_id, NodeType.LOCATION, f"Location {dest}", {"location_name": dest})
                _add_edge(pid, loc_id, EdgeType.TRAVELLED_TO, ts, {"origin": nr.get("origin"), "mode": nr.get("transport_mode")})
                overlaid += 1

        elif rec.record_type == "VEHICLE":
            veh = nr.get("vehicle_number")
            owner = nr.get("owner_person_id")
            ts = nr.get("timestamp_utc")
            if veh:
                _ensure_node(veh, NodeType.VEHICLE, f"Vehicle {veh}", {"registration_no": veh})
                if owner:
                    _ensure_node(owner, NodeType.PERSON, owner, {"person_id": owner})
                    _add_edge(owner, veh, EdgeType.USED_VEHICLE, ts)
                overlaid += 1

        elif rec.record_type == "DEVICE":
            dev = nr.get("device_id")
            pid = nr.get("person_id")
            ts = nr.get("timestamp_utc")
            if dev:
                _ensure_node(dev, NodeType.DEVICE, f"Device {dev}", {"device_id": dev, "ip_address": nr.get("ip_address")})
                if pid:
                    _ensure_node(pid, NodeType.PERSON, pid, {"person_id": pid})
                    _add_edge(pid, dev, EdgeType.USED_DEVICE, ts)
                overlaid += 1

        elif rec.record_type == "CHAT":
            sender = nr.get("sender_id")
            recipient = nr.get("recipient_id")
            ts = nr.get("timestamp_utc")
            if sender and recipient:
                _ensure_node(sender, NodeType.SOCIAL_ACCOUNT, sender)
                _ensure_node(recipient, NodeType.SOCIAL_ACCOUNT, recipient)
                _add_edge(sender, recipient, EdgeType.MESSAGED, ts, {"platform": nr.get("platform")})
                overlaid += 1

        elif rec.record_type == "PERSONS":
            pid = nr.get("person_id")
            name = nr.get("raw_name")
            if pid:
                _ensure_node(pid, NodeType.PERSON, f"{name or pid} ({pid})", {"name": name, "person_id": pid})
                _ensure_node(case_str, NodeType.CASE, f"Case {case_str}")
                _add_edge(pid, case_str, EdgeType.APPEARS_IN)
                overlaid += 1

        elif rec.record_type == "DOCUMENT":
            doc_id = f"DOC_{ev_str}"
            _ensure_node(doc_id, NodeType.EVIDENCE, ev.sanitized_filename or doc_id, {"sha256_hash": ev.sha256_hash})
            _ensure_node(case_str, NodeType.CASE, f"Case {case_str}")
            _add_edge(doc_id, case_str, EdgeType.ASSOCIATED_WITH_EVIDENCE)
            overlaid += 1

    # Overlay non-rejected IdentityHypothesis links explicitly as provisional/reviewed
    # relationships without destructively merging original observational person nodes.
    hypotheses = db.query(IdentityHypothesis).filter(
        IdentityHypothesis.status.in_(["PENDING_REVIEW", "ACCEPTED", "DISPUTED"])
    ).all()
    for hyp in hypotheses:
        if hyp.person_a_ref in graph_builder.nodes and hyp.person_b_ref in graph_builder.nodes:
            prov = ProvenanceRecord(
                source_table="identity_hypotheses",
                source_id=str(hyp.id),
                case_id=hyp.case_a_ref,
                evidence_type="IDENTITY_HYPOTHESIS",
                confidence=hyp.match_probability,
                notes=f"review_status={hyp.status}; model_version={hyp.model_version}; case_b={hyp.case_b_ref}",
            )
            ge = GraphEdge(
                source_id=hyp.person_a_ref,
                target_id=hyp.person_b_ref,
                edge_type=EdgeType.OBSERVES_ENTITY,
                provenance=prov,
                weight=hyp.match_probability,
                attributes={"review_status": hyp.status, "is_provisional_identity": hyp.status != "ACCEPTED"},
            )
            graph_builder.edges.append(ge)
            candidate_graph.add_edge(
                hyp.person_a_ref,
                hyp.person_b_ref,
                key=f"IDENTITY_HYPOTHESIS_{hyp.hypothesis_key}",
                **ge.to_dict(),
            )
            overlaid += 1

    return overlaid


def _sync_active_db_records_to_neo4j(db: Session, version_tag: str) -> bool:
    """Best-effort sync of active DB graph records to Neo4j. Never fails pipeline."""
    try:
        from app.core.neo4j import get_neo4j
        from app.services.graph_upsert import (
            create_called_edge,
            create_connected_to_tower_edge,
            create_transferred_to_edge,
            create_used_device_edge,
            upsert_account_node,
            upsert_device_node,
            upsert_document_node,
            upsert_phone_node,
            upsert_tower_node,
        )

        neo4j = get_neo4j()
        neo4j.verify_connectivity()

        # Remove edges belonging to superseded/withdrawn evidence
        inactive_ids = [
            str(r[0])
            for r in db.query(EvidenceItem.id)
            .filter(EvidenceItem.lifecycle_status != "ACTIVE")
            .all()
        ]
        if inactive_ids:
            neo4j.run_query(
                "MATCH ()-[r]->() WHERE r.evidence_id IN $eids DELETE r",
                {"eids": inactive_ids},
            )

        rows = (
            db.query(ParsedRecord, EvidenceItem)
            .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
            .filter(
                ParsedRecord.parse_status == "VALID",
                EvidenceItem.lifecycle_status == "ACTIVE",
            )
            .limit(5000)
            .all()
        )
        for rec, ev in rows:
            case_id = str(ev.case_id)
            nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
            upsert_document_node(
                case_id=case_id,
                evidence_id=str(ev.id),
                evidence_code=ev.evidence_code,
                filename=ev.sanitized_filename,
                sha256_hash=ev.sha256_hash,
                integrity_status=ev.integrity_status,
            )
            prov = {
                "evidence_id": str(ev.id),
                "case_id": case_id,
                "source_file_name": ev.sanitized_filename,
                "source_row_number": rec.source_row_number,
                "source_hash": ev.sha256_hash,
                "verification_status": ev.integrity_status,
                "relationship_status": "DIRECT_RECORD",
                "confidence_label": "DIRECT_SOURCE_RECORD",
                "graph_version": version_tag,
            }
            if rec.record_type == "CDR" and nr.get("calling_number") and nr.get("called_number"):
                ts = nr.get("start_time_utc", "")
                upsert_phone_node(case_id, nr["calling_number"], [nr["calling_number"]], ts, ts)
                upsert_phone_node(case_id, nr["called_number"], [nr["called_number"]], ts, ts)
                create_called_edge(
                    case_id,
                    nr["calling_number"],
                    nr["called_number"],
                    {**prov, "event_timestamp_utc": ts, "raw_timestamp": nr.get("raw_start_time", "")},
                    nr.get("duration_seconds"),
                )
                if nr.get("imei"):
                    upsert_device_node(case_id, nr["imei"])
                    create_used_device_edge(case_id, nr["calling_number"], nr["imei"], {**prov, "event_timestamp_utc": ts})
                if nr.get("tower_id"):
                    upsert_tower_node(case_id, nr["tower_id"])
                    create_connected_to_tower_edge(case_id, nr["calling_number"], nr["tower_id"], {**prov, "event_timestamp_utc": ts})
            elif rec.record_type == "TRANSACTION" and nr.get("sender_identifier") and nr.get("receiver_identifier"):
                ts = nr.get("timestamp_utc", "")
                upsert_account_node(case_id, nr["sender_identifier"], nr.get("transaction_type", "UPI"), ts, ts)
                upsert_account_node(case_id, nr["receiver_identifier"], nr.get("transaction_type", "UPI"), ts, ts)
                create_transferred_to_edge(
                    case_id,
                    nr["sender_identifier"],
                    nr["receiver_identifier"],
                    {**prov, "event_timestamp_utc": ts, "raw_timestamp": nr.get("raw_timestamp", "")},
                    nr.get("amount", 0.0),
                    nr.get("currency", "INR"),
                    nr.get("transaction_id"),
                    nr.get("transaction_type"),
                )
        return True
    except Exception:
        return False


def publish_graph_snapshot(
    db: Session,
    created_by: Optional[str] = None,
    output_dir: Path = GRAPH_OUTPUT_DIR,
    include_baseline_dataset: bool = True,
    simulate_validation_failure: bool = False,
) -> GraphSnapshot:
    """
    Build, validate, stage, and atomically publish a versioned knowledge graph snapshot.
    On any failure, the previous ACTIVE snapshot and files remain untouched.
    """
    with _PUBLISH_LOCK:
        max_ver = db.query(func.max(GraphSnapshot.version_number)).scalar() or 0
        next_ver = int(max_ver) + 1
        version_tag = f"v{next_ver:05d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        staging_dir = Path(output_dir) / "snapshots" / version_tag

        snapshot = GraphSnapshot(
            id=uuid.uuid4(),
            version_number=next_ver,
            version_tag=version_tag,
            status="BUILDING",
            artifact_dir=str(staging_dir),
            created_by=uuid.UUID(str(created_by)) if created_by else None,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        try:
            graph_builder = GraphBuilder()
            if include_baseline_dataset and EVIDENCE_DIR.exists():
                candidate_graph = graph_builder.build_global_graph()
            else:
                candidate_graph = nx.MultiDiGraph()
                graph_builder.multi_graph = candidate_graph

            db_overlaid = _overlay_db_records_onto_graph(graph_builder, candidate_graph, db)

            node_count = candidate_graph.number_of_nodes()
            edge_count = candidate_graph.number_of_edges()

            if simulate_validation_failure:
                raise RuntimeError("Simulated graph structural validation failure.")

            if node_count == 0 or edge_count == 0:
                raise RuntimeError(
                    f"Candidate graph failed structural validation (nodes={node_count}, edges={edge_count})."
                )

            # Provenance check: every edge must carry provenance_table and provenance_case_id
            for _, _, edata in candidate_graph.edges(data=True):
                if not edata.get("provenance_table") or not edata.get("provenance_case_id"):
                    raise RuntimeError("Graph provenance validation failed: edge missing source provenance.")

            staging_dir.mkdir(parents=True, exist_ok=True)
            exporter = GraphExporter(output_dir=staging_dir)
            exporter.export_nodes_csv(graph_builder.nodes)
            exporter.export_edges_csv(graph_builder.edges)
            exporter.export_case_graph_json(candidate_graph)
            summary = graph_builder.get_summary_stats()
            summary["db_overlaid_records"] = db_overlaid
            summary["version_tag"] = version_tag
            exporter.export_graph_summary_json(summary)

            manifest = {
                "version_number": next_ver,
                "version_tag": version_tag,
                "node_count": node_count,
                "edge_count": edge_count,
                "db_overlaid_records": db_overlaid,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_text(staging_dir / "manifest.json", json.dumps(manifest, indent=2))

            snapshot.status = "VALIDATED"
            snapshot.node_count = node_count
            snapshot.edge_count = edge_count
            snapshot.manifest = manifest
            db.commit()

            # Atomic activation in filesystem (temp + os.replace)
            for fname in ("nodes.csv", "edges.csv", "case_graph.json", "graph_summary.json"):
                src_f = staging_dir / fname
                if src_f.exists():
                    _atomic_copy(src_f, Path(output_dir) / fname)

            _atomic_write_text(Path(output_dir) / "active_snapshot.json", json.dumps(manifest, indent=2))

            # Atomic DB status swap
            now = datetime.now(timezone.utc)
            db.query(GraphSnapshot).filter(GraphSnapshot.status == "ACTIVE").update(
                {"status": "ROLLED_BACK"},
                synchronize_session=False,
            )
            snapshot.status = "ACTIVE"
            snapshot.activated_at = now
            db.commit()
            db.refresh(snapshot)

            _sync_active_db_records_to_neo4j(db, version_tag)
            return snapshot

        except Exception as exc:
            snapshot.status = "FAILED"
            snapshot.error_message = str(exc)[:500]
            db.commit()
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
