"""
Graph API — queries Neo4j when available, with graceful fallback to authoritative
active ParsedRecord rows in PostgreSQL/SQLite.
"""
from __future__ import annotations

import hashlib
from collections import deque
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authz import require_case_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.evidence import EvidenceItem, ParsedRecord
from app.models.graph import GraphSnapshot

router = APIRouter(prefix="/api/v1/cases", tags=["graph"])

LIMITATIONS = [
    "This record indicates a communication or financial event between identifiers.",
    "It does not establish who physically used the phone or account.",
    "It does not establish the content, purpose, or legality of the interaction.",
    "A graph path represents recorded relationships — not proof of criminal conduct.",
]


def _stable_id(*parts: str) -> str:
    """Generate a stable deterministic ID from entity fields."""
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:16]


def _in_time_window(ts: Optional[str], start_time: Optional[str], end_time: Optional[str]) -> bool:
    if not start_time and not end_time:
        return True
    if not ts:
        return False
    if start_time and ts < start_time:
        return False
    if end_time and ts > end_time:
        return False
    return True


def _neo4j_available() -> bool:
    try:
        from app.core.neo4j import get_neo4j
        neo4j = get_neo4j()
        neo4j.verify_connectivity()
        return True
    except Exception:
        return False


def _query_graph_from_neo4j(
    case_id: str,
    entity_filter: Optional[str] = None,
    rel_types: Optional[list[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit_nodes: int = 200,
) -> Optional[tuple[list[dict], list[dict]]]:
    """Query Neo4j strictly scoped by case_id. Returns None on failure so DB fallback triggers."""
    try:
        from app.core.neo4j import get_neo4j
        neo4j = get_neo4j()
        rows = neo4j.run_query(
            """
            MATCH (a {case_id: $case_id})-[r {case_id: $case_id}]->(b {case_id: $case_id})
            WHERE ($rel_types IS NULL OR type(r) IN $rel_types)
              AND ($start_time IS NULL OR coalesce(r.event_timestamp_utc, '') >= $start_time)
              AND ($end_time IS NULL OR coalesce(r.event_timestamp_utc, '') <= $end_time)
            RETURN a AS src, labels(a) AS src_labels, r AS rel, type(r) AS rel_type, b AS tgt, labels(b) AS tgt_labels
            LIMIT $edge_limit
            """,
            {
                "case_id": case_id,
                "rel_types": rel_types,
                "start_time": start_time,
                "end_time": end_time,
                "edge_limit": max(limit_nodes * 4, 400),
            },
        )
        if not rows:
            return None

        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        for row in rows:
            s = dict(row["src"])
            t = dict(row["tgt"])
            r = dict(row["rel"])
            sid = str(s.get("id") or _stable_id(case_id, str(s)))
            tid = str(t.get("id") or _stable_id(case_id, str(t)))
            s_val = s.get("normalized_number") or s.get("normalized_identifier") or s.get("imei") or s.get("tower_id") or ""
            t_val = t.get("normalized_number") or t.get("normalized_identifier") or t.get("imei") or t.get("tower_id") or ""
            if entity_filter and entity_filter not in s_val and entity_filter not in t_val:
                continue
            nodes.setdefault(sid, {**s, "id": sid, "labels": row["src_labels"]})
            nodes.setdefault(tid, {**t, "id": tid, "labels": row["tgt_labels"]})
            edges.append({
                **r,
                "id": str(r.get("id") or _stable_id(sid, tid, row["rel_type"])),
                "source": sid,
                "target": tid,
                "relationship_type": row["rel_type"],
            })
            if len(nodes) >= limit_nodes:
                break
        if not nodes:
            return None
        return list(nodes.values()), edges
    except Exception:
        return None


def _build_graph_from_db(
    case_id: str,
    db: Session,
    entity_filter: Optional[str] = None,
    entity_type: Optional[str] = None,
    rel_types: Optional[list[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit_nodes: int = 200,
) -> tuple[list[dict], list[dict]]:
    """
    Build graph nodes and edges from VALID ParsedRecords belonging ONLY to ACTIVE
    (non-superseded, non-withdrawn) EvidenceItems in PostgreSQL/SQLite.
    """
    rows = (
        db.query(ParsedRecord, EvidenceItem)
        .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
        .filter(
            ParsedRecord.case_id == case_id,
            ParsedRecord.parse_status == "VALID",
            EvidenceItem.lifecycle_status == "ACTIVE",
        )
        .limit(2500)
        .all()
    )

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    want_rels = set(rel_types) if rel_types else None

    def _add_node(nid: str, labels: list[str], props: dict):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "labels": labels, "case_id": case_id, **props}

    for rec, ev in rows:
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        ev_filename = ev.sanitized_filename or ev.original_filename or ""
        ev_hash = ev.sha256_hash or ""
        ev_status = ev.integrity_status or "UNVERIFIED"
        base_prov = {
            "evidence_id": str(rec.evidence_id),
            "source_file_name": ev_filename,
            "source_row_number": rec.source_row_number,
            "source_hash": ev_hash,
            "verification_status": ev_status,
            "confidence_label": "DIRECT_SOURCE_RECORD",
            "evidence_version": getattr(rec, "evidence_version", 1),
        }

        if rec.record_type == "CDR":
            caller = nr.get("calling_number", "")
            callee = nr.get("called_number", "")
            ts = nr.get("start_time_utc", "")
            if not caller or not callee or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in caller and entity_filter not in callee:
                continue
            cid = _stable_id(case_id, "phone", caller)
            did = _stable_id(case_id, "phone", callee)
            _add_node(cid, ["Phone"], {"normalized_number": caller, "first_seen_at": ts, "last_seen_at": ts})
            _add_node(did, ["Phone"], {"normalized_number": callee, "first_seen_at": ts, "last_seen_at": ts})
            nodes[cid]["last_seen_at"] = max(nodes[cid].get("last_seen_at", ""), ts)
            nodes[did]["last_seen_at"] = max(nodes[did].get("last_seen_at", ""), ts)

            if want_rels is None or "CALLED" in want_rels:
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "CALLED", caller, callee, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": cid,
                    "target": did,
                    "relationship_type": "CALLED",
                    "event_timestamp_utc": ts,
                    "duration_seconds": nr.get("duration_seconds"),
                    "call_type": nr.get("call_type", "VOICE"),
                })

            if nr.get("imei") and (want_rels is None or "USED_DEVICE" in want_rels):
                dev_id = _stable_id(case_id, "device", nr["imei"])
                _add_node(dev_id, ["Device"], {"imei": nr["imei"]})
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "USED_DEVICE", caller, nr["imei"], str(rec.evidence_id)),
                    "source": cid,
                    "target": dev_id,
                    "relationship_type": "USED_DEVICE",
                    "event_timestamp_utc": ts,
                })

            if nr.get("tower_id") and (want_rels is None or "CONNECTED_TO_TOWER" in want_rels):
                twr_id = _stable_id(case_id, "tower", nr["tower_id"])
                _add_node(twr_id, ["Tower"], {"tower_id": nr["tower_id"]})
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "CONNECTED_TO_TOWER", caller, nr["tower_id"], str(rec.evidence_id)),
                    "source": cid,
                    "target": twr_id,
                    "relationship_type": "CONNECTED_TO_TOWER",
                    "event_timestamp_utc": ts,
                })

        elif rec.record_type == "TRANSACTION":
            sender = nr.get("sender_identifier", "")
            receiver = nr.get("receiver_identifier", "")
            ts = nr.get("timestamp_utc", "")
            if not sender or not receiver or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in sender and entity_filter not in receiver:
                continue
            sid = _stable_id(case_id, "account", sender)
            rid = _stable_id(case_id, "account", receiver)
            _add_node(sid, ["Account"], {"normalized_identifier": sender, "account_type": nr.get("transaction_type", "UPI")})
            _add_node(rid, ["Account"], {"normalized_identifier": receiver, "account_type": nr.get("transaction_type", "UPI")})

            if want_rels is None or "TRANSFERRED_TO" in want_rels or "TRANSFERRED_MONEY" in want_rels:
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "TRANSFERRED_TO", sender, receiver, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": sid,
                    "target": rid,
                    "relationship_type": "TRANSFERRED_TO",
                    "event_timestamp_utc": ts,
                    "amount": nr.get("amount"),
                    "currency": nr.get("currency", "INR"),
                    "transaction_id": nr.get("transaction_id"),
                    "transaction_type": nr.get("transaction_type", "UPI"),
                })

        elif rec.record_type == "TRAVEL":
            pid = nr.get("person_id", "")
            dest = nr.get("destination", "")
            ts = nr.get("departure_time_utc", "")
            if not pid or not dest or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in pid and entity_filter not in dest:
                continue
            p_nid = _stable_id(case_id, "person", pid)
            l_nid = _stable_id(case_id, "location", dest)
            _add_node(p_nid, ["Person"], {"normalized_identifier": pid})
            _add_node(l_nid, ["Location"], {"normalized_identifier": dest})
            if want_rels is None or "TRAVELLED_TO" in want_rels:
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "TRAVELLED_TO", pid, dest, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": p_nid,
                    "target": l_nid,
                    "relationship_type": "TRAVELLED_TO",
                    "event_timestamp_utc": ts,
                })

        elif rec.record_type == "DEVICE":
            dev = nr.get("device_id", "")
            pid = nr.get("person_id", "")
            ts = nr.get("timestamp_utc", "")
            if not dev or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in dev and entity_filter not in pid:
                continue
            d_nid = _stable_id(case_id, "device", dev)
            _add_node(d_nid, ["Device"], {"normalized_identifier": dev, "ip_address": nr.get("ip_address")})
            if pid and (want_rels is None or "USED_DEVICE" in want_rels):
                p_nid = _stable_id(case_id, "person", pid)
                _add_node(p_nid, ["Person"], {"normalized_identifier": pid})
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "USED_DEVICE", pid, dev, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": p_nid,
                    "target": d_nid,
                    "relationship_type": "USED_DEVICE",
                    "event_timestamp_utc": ts,
                })

        elif rec.record_type == "VEHICLE":
            veh = nr.get("vehicle_number", "")
            owner = nr.get("owner_person_id", "")
            ts = nr.get("timestamp_utc", "")
            if not veh or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in veh and entity_filter not in owner:
                continue
            v_nid = _stable_id(case_id, "vehicle", veh)
            _add_node(v_nid, ["Vehicle"], {"normalized_identifier": veh})
            if owner and (want_rels is None or "USED_VEHICLE" in want_rels):
                p_nid = _stable_id(case_id, "person", owner)
                _add_node(p_nid, ["Person"], {"normalized_identifier": owner})
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "USED_VEHICLE", owner, veh, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": p_nid,
                    "target": v_nid,
                    "relationship_type": "USED_VEHICLE",
                    "event_timestamp_utc": ts,
                })

        elif rec.record_type == "CHAT":
            sender = nr.get("sender_id", "")
            recipient = nr.get("recipient_id", "")
            ts = nr.get("timestamp_utc", "")
            if not sender or not recipient or not _in_time_window(ts, start_time, end_time):
                continue
            if entity_filter and entity_filter not in sender and entity_filter not in recipient:
                continue
            s_nid = _stable_id(case_id, "social", sender)
            r_nid = _stable_id(case_id, "social", recipient)
            _add_node(s_nid, ["SocialAccount"], {"normalized_identifier": sender})
            _add_node(r_nid, ["SocialAccount"], {"normalized_identifier": recipient})
            if want_rels is None or "MESSAGED" in want_rels:
                edges.append({
                    **base_prov,
                    "id": _stable_id(case_id, "MESSAGED", sender, recipient, str(rec.source_row_number), str(rec.evidence_id)),
                    "source": s_nid,
                    "target": r_nid,
                    "relationship_type": "MESSAGED",
                    "event_timestamp_utc": ts,
                })

        elif rec.record_type == "PERSONS":
            pid = nr.get("person_id", "")
            name = nr.get("raw_name", "")
            if not pid:
                continue
            if entity_filter and entity_filter not in pid and entity_filter not in name:
                continue
            p_nid = _stable_id(case_id, "person", pid)
            _add_node(p_nid, ["Person"], {"normalized_identifier": f"{name} ({pid})" if name else pid, "person_id": pid})

        if len(nodes) >= limit_nodes:
            break

    if entity_type:
        want_type = entity_type.strip().lower()
        nodes = {
            nid: n for nid, n in nodes.items()
            if any(lbl.lower() == want_type for lbl in n.get("labels", []))
        }
        edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]

    seen_edges: set[str] = set()
    deduped_edges = []
    for e in edges:
        if e["id"] not in seen_edges:
            seen_edges.add(e["id"])
            deduped_edges.append(e)

    return list(nodes.values()), deduped_edges


@router.get("/{case_id}/graph/subgraph")
def get_subgraph(
    case_id: str,
    entity: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    depth: int = Query(2, ge=1, le=3),
    relationship_types: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit_nodes: int = Query(200, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case = require_case_access(case_id, current_user, db)
    rel_types = [r.strip().upper() for r in relationship_types.split(",") if r.strip()] if relationship_types else None

    if _neo4j_available():
        neo_res = _query_graph_from_neo4j(
            case_id=str(case.id),
            entity_filter=entity or None,
            rel_types=rel_types,
            start_time=start_time,
            end_time=end_time,
            limit_nodes=limit_nodes,
        )
        if neo_res is not None:
            nodes, edges = neo_res
            return {"nodes": nodes, "edges": edges, "source": "neo4j"}

    nodes, edges = _build_graph_from_db(
        case_id=str(case.id),
        db=db,
        entity_filter=entity or None,
        entity_type=entity_type,
        rel_types=rel_types,
        start_time=start_time,
        end_time=end_time,
        limit_nodes=limit_nodes,
    )
    active_snap = (
        db.query(GraphSnapshot)
        .filter(GraphSnapshot.status == "ACTIVE")
        .order_by(GraphSnapshot.version_number.desc())
        .first()
    )
    return {
        "nodes": nodes,
        "edges": edges,
        "source": "postgresql",
        "graph_snapshot_version": active_snap.version_tag if active_snap else None,
    }


@router.get("/{case_id}/graph/snapshot")
def get_active_graph_snapshot(
    case_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_case_access(case_id, current_user, db)
    snap = (
        db.query(GraphSnapshot)
        .filter(GraphSnapshot.status == "ACTIVE")
        .order_by(GraphSnapshot.version_number.desc())
        .first()
    )
    if not snap:
        return {"active": False, "snapshot": None}
    return {
        "active": True,
        "snapshot": {
            "version_number": snap.version_number,
            "version_tag": snap.version_tag,
            "status": snap.status,
            "node_count": snap.node_count,
            "edge_count": snap.edge_count,
            "activated_at": snap.activated_at.isoformat() if snap.activated_at else None,
        },
    }


@router.get("/{case_id}/graph/entity-search")
def entity_search(
    case_id: str,
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case = require_case_access(case_id, current_user, db)
    nodes, _ = _build_graph_from_db(case_id=str(case.id), db=db, entity_filter=q, limit_nodes=50)
    return [{"labels": n.get("labels", []), "props": n} for n in nodes]


@router.get("/{case_id}/graph/nodes/{node_id}")
def get_node(case_id: str, node_id: str, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    case = require_case_access(case_id, current_user, db)
    nodes, edges = _build_graph_from_db(case_id=str(case.id), db=db, limit_nodes=500)
    node = next((n for n in nodes if n["id"] == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    conn_count = sum(1 for e in edges if e.get("source") == node_id or e.get("target") == node_id)
    return {"labels": node.get("labels", []), "props": node, "connection_count": conn_count}


@router.get("/{case_id}/graph/edges/{edge_id}")
def get_edge(case_id: str, edge_id: str, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    case = require_case_access(case_id, current_user, db)
    _, edges = _build_graph_from_db(case_id=str(case.id), db=db, limit_nodes=500)
    edge = next((e for e in edges if e["id"] == edge_id), None)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")

    nodes, _ = _build_graph_from_db(case_id=str(case.id), db=db, limit_nodes=500)
    node_map = {n["id"]: n for n in nodes}
    src = node_map.get(edge.get("source", ""), {})
    tgt = node_map.get(edge.get("target", ""), {})

    return {
        "edge_id": edge_id,
        "relationship_type": edge.get("relationship_type"),
        "source": {
            "labels": src.get("labels", []),
            "normalized_number": src.get("normalized_number"),
            "normalized_identifier": src.get("normalized_identifier"),
        },
        "target": {
            "labels": tgt.get("labels", []),
            "normalized_number": tgt.get("normalized_number"),
            "normalized_identifier": tgt.get("normalized_identifier"),
        },
        "event": {
            "timestamp_utc": edge.get("event_timestamp_utc"),
            "duration_seconds": edge.get("duration_seconds"),
            "amount": edge.get("amount"),
            "currency": edge.get("currency"),
            "transaction_id": edge.get("transaction_id"),
            "transaction_type": edge.get("transaction_type"),
        },
        "provenance": {
            "evidence_id": edge.get("evidence_id"),
            "source_file_name": edge.get("source_file_name"),
            "source_row_number": edge.get("source_row_number"),
            "source_hash": edge.get("source_hash"),
            "verification_status": edge.get("verification_status"),
            "confidence_label": edge.get("confidence_label"),
        },
        "limitations": LIMITATIONS,
    }


class PathRequest(BaseModel):
    source_entity: str
    target_entity: str
    max_depth: int = 4


@router.post("/{case_id}/graph/path")
def find_path(case_id: str, body: PathRequest, db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    case = require_case_access(case_id, current_user, db)
    nodes, edges = _build_graph_from_db(case_id=str(case.id), db=db, limit_nodes=500)
    node_map = {n["id"]: n for n in nodes}

    src_id = next((n["id"] for n in nodes if
        n.get("normalized_number") == body.source_entity or
        n.get("normalized_identifier") == body.source_entity), None)
    tgt_id = next((n["id"] for n in nodes if
        n.get("normalized_number") == body.target_entity or
        n.get("normalized_identifier") == body.target_entity), None)

    if not src_id or not tgt_id:
        return {"found": False, "path_nodes": [], "path_edges": [], "limitations": LIMITATIONS}

    adj: dict[str, list[tuple[str, dict]]] = {n["id"]: [] for n in nodes}
    for e in edges:
        s, t = e.get("source", ""), e.get("target", "")
        if s in adj:
            adj[s].append((t, e))
        if t in adj:
            adj[t].append((s, e))

    visited = {src_id: None}
    queue = deque([(src_id, 0)])
    while queue:
        cur, d = queue.popleft()
        if cur == tgt_id:
            break
        if d >= body.max_depth:
            continue
        for nxt, edge in adj.get(cur, []):
            if nxt not in visited:
                visited[nxt] = (cur, edge)
                queue.append((nxt, d + 1))

    if tgt_id not in visited:
        return {"found": False, "path_nodes": [], "path_edges": [], "limitations": LIMITATIONS}

    path_nodes, path_edges = [], []
    cur = tgt_id
    while cur is not None:
        path_nodes.append({"labels": node_map[cur].get("labels", []), "props": node_map[cur]})
        prev = visited[cur]
        if prev:
            path_edges.append({"type": prev[1].get("relationship_type"), "props": prev[1]})
            cur = prev[0]
        else:
            cur = None

    return {
        "found": True,
        "path_nodes": list(reversed(path_nodes)),
        "path_edges": list(reversed(path_edges)),
        "limitations": LIMITATIONS,
    }
