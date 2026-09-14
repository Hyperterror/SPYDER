"""
Graph API — builds the knowledge graph from parsed_records in the SQL database.
Falls back to Neo4j if available; always has data from SQLite for local dev.
"""
from __future__ import annotations
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.case import Case, CaseMember
from app.models.evidence import ParsedRecord, EvidenceItem

router = APIRouter(prefix="/api/v1/cases", tags=["graph"])

LIMITATIONS = [
    "This record indicates a communication or financial event between identifiers.",
    "It does not establish who physically used the phone or account.",
    "It does not establish the content, purpose, or legality of the interaction.",
    "A graph path represents recorded relationships — not proof of criminal conduct.",
]


def _require_case_access(case_id: str, user, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user.role not in ("ADMIN", "SUPERVISOR"):
        member = db.query(CaseMember).filter(
            CaseMember.case_id == case_id, CaseMember.user_id == user.id
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    return case


def _stable_id(*parts: str) -> str:
    """Generate a stable short ID from entity fields."""
    return hashlib.md5(":".join(parts).encode()).hexdigest()[:16]


def _build_graph_from_db(
    case_id: str,
    db: Session,
    entity_filter: Optional[str] = None,
    rel_types: Optional[list[str]] = None,
    limit_nodes: int = 200,
) -> tuple[list[dict], list[dict]]:
    """
    Build graph nodes and edges directly from parsed_records in the database.
    Returns (nodes, edges) as lists of dicts ready for Cytoscape.
    """
    records = (
        db.query(ParsedRecord)
        .filter(ParsedRecord.case_id == case_id, ParsedRecord.parse_status == "VALID")
        .limit(2000)
        .all()
    )

    nodes: dict[str, dict] = {}   # id -> node dict
    edges: list[dict] = []

    # Get evidence info for provenance
    evidence_map: dict[str, EvidenceItem] = {}
    for ev in db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all():
        evidence_map[str(ev.id)] = ev

    want_rels = set(rel_types) if rel_types else {"CALLED", "TRANSFERRED_TO", "USED_DEVICE", "CONNECTED_TO_TOWER"}

    for rec in records:
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        ev = evidence_map.get(str(rec.evidence_id))
        ev_filename = ev.original_filename if ev else ""
        ev_hash     = ev.sha256_hash if ev else ""
        ev_status   = ev.integrity_status if ev else "UNVERIFIED"

        if rec.record_type == "CDR":
            caller = nr.get("calling_number", "")
            callee = nr.get("called_number", "")
            if not caller or not callee:
                continue

            # Filter by entity search
            if entity_filter and entity_filter not in (caller, callee):
                continue

            # Phone nodes
            caller_id = _stable_id(case_id, "phone", caller)
            callee_id = _stable_id(case_id, "phone", callee)

            if caller_id not in nodes:
                nodes[caller_id] = {
                    "id": caller_id,
                    "labels": ["Phone"],
                    "normalized_number": caller,
                    "case_id": case_id,
                    "first_seen_at": nr.get("start_time_utc", ""),
                    "last_seen_at":  nr.get("start_time_utc", ""),
                }
            else:
                nodes[caller_id]["last_seen_at"] = nr.get("start_time_utc", "")

            if callee_id not in nodes:
                nodes[callee_id] = {
                    "id": callee_id,
                    "labels": ["Phone"],
                    "normalized_number": callee,
                    "case_id": case_id,
                    "first_seen_at": nr.get("start_time_utc", ""),
                    "last_seen_at":  nr.get("start_time_utc", ""),
                }

            # CALLED edge
            if "CALLED" in want_rels:
                edge_id = _stable_id(case_id, "CALLED", caller, callee, str(rec.source_row_number), str(rec.evidence_id))
                edges.append({
                    "id": edge_id,
                    "source": caller_id,
                    "target": callee_id,
                    "relationship_type": "CALLED",
                    "event_timestamp_utc": nr.get("start_time_utc", ""),
                    "duration_seconds": nr.get("duration_seconds"),
                    "call_type": nr.get("call_type", "VOICE"),
                    "evidence_id": str(rec.evidence_id),
                    "source_file_name": ev_filename,
                    "source_row_number": rec.source_row_number,
                    "source_hash": ev_hash,
                    "verification_status": ev_status,
                    "confidence_label": "DIRECT_SOURCE_RECORD",
                })

            # Device node + USED_DEVICE edge
            imei = nr.get("imei")
            if imei and "USED_DEVICE" in want_rels:
                dev_id = _stable_id(case_id, "device", imei)
                if dev_id not in nodes:
                    nodes[dev_id] = {
                        "id": dev_id, "labels": ["Device"],
                        "imei": imei, "case_id": case_id,
                    }
                edge_id = _stable_id(case_id, "USED_DEVICE", caller, imei, str(rec.evidence_id))
                edges.append({
                    "id": edge_id, "source": caller_id, "target": dev_id,
                    "relationship_type": "USED_DEVICE",
                    "evidence_id": str(rec.evidence_id),
                    "source_file_name": ev_filename,
                    "source_row_number": rec.source_row_number,
                    "source_hash": ev_hash, "verification_status": ev_status,
                    "confidence_label": "DIRECT_SOURCE_RECORD",
                })

            # Tower node + CONNECTED_TO_TOWER edge
            tower = nr.get("tower_id")
            if tower and "CONNECTED_TO_TOWER" in want_rels:
                tower_id = _stable_id(case_id, "tower", tower)
                if tower_id not in nodes:
                    nodes[tower_id] = {
                        "id": tower_id, "labels": ["Tower"],
                        "tower_id": tower, "case_id": case_id,
                    }
                edge_id = _stable_id(case_id, "CONNECTED_TO_TOWER", caller, tower, str(rec.evidence_id))
                edges.append({
                    "id": edge_id, "source": caller_id, "target": tower_id,
                    "relationship_type": "CONNECTED_TO_TOWER",
                    "evidence_id": str(rec.evidence_id),
                    "source_file_name": ev_filename,
                    "source_row_number": rec.source_row_number,
                    "source_hash": ev_hash, "verification_status": ev_status,
                    "confidence_label": "DIRECT_SOURCE_RECORD",
                })

        elif rec.record_type == "TRANSACTION":
            sender   = nr.get("sender_identifier", "")
            receiver = nr.get("receiver_identifier", "")
            if not sender or not receiver:
                continue

            if entity_filter and entity_filter not in (sender, receiver):
                continue

            sender_id   = _stable_id(case_id, "account", sender)
            receiver_id = _stable_id(case_id, "account", receiver)

            if sender_id not in nodes:
                nodes[sender_id] = {
                    "id": sender_id, "labels": ["Account"],
                    "normalized_identifier": sender,
                    "account_type": nr.get("transaction_type", "UPI"),
                    "case_id": case_id,
                }
            if receiver_id not in nodes:
                nodes[receiver_id] = {
                    "id": receiver_id, "labels": ["Account"],
                    "normalized_identifier": receiver,
                    "account_type": nr.get("transaction_type", "UPI"),
                    "case_id": case_id,
                }

            if "TRANSFERRED_TO" in want_rels:
                edge_id = _stable_id(case_id, "TRANSFERRED_TO", sender, receiver, str(rec.source_row_number), str(rec.evidence_id))
                edges.append({
                    "id": edge_id, "source": sender_id, "target": receiver_id,
                    "relationship_type": "TRANSFERRED_TO",
                    "event_timestamp_utc": nr.get("timestamp_utc", ""),
                    "amount": nr.get("amount"),
                    "currency": nr.get("currency", "INR"),
                    "transaction_id": nr.get("transaction_id"),
                    "transaction_type": nr.get("transaction_type", "UPI"),
                    "evidence_id": str(rec.evidence_id),
                    "source_file_name": ev_filename,
                    "source_row_number": rec.source_row_number,
                    "source_hash": ev_hash, "verification_status": ev_status,
                    "confidence_label": "DIRECT_SOURCE_RECORD",
                })

        # Stop once we have enough nodes
        if len(nodes) >= limit_nodes:
            break

    # Deduplicate edges by id
    seen_edges: set[str] = set()
    deduped_edges = []
    for e in edges:
        if e["id"] not in seen_edges:
            seen_edges.add(e["id"])
            deduped_edges.append(e)

    return list(nodes.values()), deduped_edges


# ─── Try Neo4j, fall back to DB ───────────────────────────────────────────────

def _neo4j_available() -> bool:
    try:
        from app.core.neo4j import get_neo4j
        neo4j = get_neo4j()
        neo4j.verify_connectivity()
        return True
    except Exception:
        return False


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
    _require_case_access(case_id, current_user, db)

    rel_types = [r.strip().upper() for r in relationship_types.split(",")] if relationship_types else None

    nodes, edges = _build_graph_from_db(
        case_id=case_id,
        db=db,
        entity_filter=entity or None,
        rel_types=rel_types,
        limit_nodes=limit_nodes,
    )

    return {"nodes": nodes, "edges": edges}


@router.get("/{case_id}/graph/entity-search")
def entity_search(
    case_id: str,
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)
    nodes, _ = _build_graph_from_db(case_id=case_id, db=db, entity_filter=q, limit_nodes=50)
    return [{"labels": n.get("labels", []), "props": n} for n in nodes]


@router.get("/{case_id}/graph/nodes/{node_id}")
def get_node(case_id: str, node_id: str, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    _require_case_access(case_id, current_user, db)
    nodes, edges = _build_graph_from_db(case_id=case_id, db=db, limit_nodes=500)
    node = next((n for n in nodes if n["id"] == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    conn_count = sum(1 for e in edges if e.get("source") == node_id or e.get("target") == node_id)
    return {"labels": node.get("labels", []), "props": node, "connection_count": conn_count}


@router.get("/{case_id}/graph/edges/{edge_id}")
def get_edge(case_id: str, edge_id: str, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    _require_case_access(case_id, current_user, db)
    _, edges = _build_graph_from_db(case_id=case_id, db=db, limit_nodes=500)
    edge = next((e for e in edges if e["id"] == edge_id), None)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")

    nodes, _ = _build_graph_from_db(case_id=case_id, db=db, limit_nodes=500)
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
    _require_case_access(case_id, current_user, db)
    nodes, edges = _build_graph_from_db(case_id=case_id, db=db, limit_nodes=500)
    node_map = {n["id"]: n for n in nodes}

    # Find source and target node IDs by identifier
    src_id = next((n["id"] for n in nodes if
        n.get("normalized_number") == body.source_entity or
        n.get("normalized_identifier") == body.source_entity), None)
    tgt_id = next((n["id"] for n in nodes if
        n.get("normalized_number") == body.target_entity or
        n.get("normalized_identifier") == body.target_entity), None)

    if not src_id or not tgt_id:
        return {"found": False, "path_nodes": [], "path_edges": [], "limitations": LIMITATIONS}

    # BFS shortest path
    from collections import deque
    adj: dict[str, list[tuple[str, dict]]] = {n["id"]: [] for n in nodes}
    for e in edges:
        s, t = e.get("source", ""), e.get("target", "")
        if s in adj: adj[s].append((t, e))
        if t in adj: adj[t].append((s, e))

    visited = {src_id: None}  # node_id -> (prev_node_id, edge)
    queue = deque([src_id])
    while queue:
        cur = queue.popleft()
        if cur == tgt_id:
            break
        for nxt, edge in adj.get(cur, []):
            if nxt not in visited:
                visited[nxt] = (cur, edge)
                queue.append(nxt)

    if tgt_id not in visited:
        return {"found": False, "path_nodes": [], "path_edges": [], "limitations": LIMITATIONS}

    # Reconstruct path
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
