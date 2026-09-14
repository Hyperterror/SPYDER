"""
Neo4j graph upsert service.

All nodes and relationships created here carry full evidence provenance,
per Phase 1 TRD §5. No edge is created without evidence_id and source_row_number.
"""
from __future__ import annotations
from typing import Optional
from app.core.neo4j import get_neo4j


# ──────────────────────────────────────────────────────────────────────────
# Node upserts
# ──────────────────────────────────────────────────────────────────────────

def upsert_phone_node(case_id: str, normalized_number: str, raw_values: list[str],
                      first_seen: str, last_seen: str) -> dict:
    neo4j = get_neo4j()
    query = """
    MERGE (p:Phone {case_id: $case_id, normalized_number: $normalized_number})
    ON CREATE SET p.id = randomUUID(), p.case_id = $case_id,
                  p.normalized_number = $normalized_number,
                  p.raw_values = $raw_values,
                  p.first_seen_at = $first_seen,
                  p.last_seen_at = $last_seen,
                  p.created_at = datetime()
    ON MATCH SET  p.last_seen_at = CASE WHEN $last_seen > p.last_seen_at THEN $last_seen ELSE p.last_seen_at END,
                  p.raw_values = p.raw_values + [x IN $raw_values WHERE NOT x IN p.raw_values],
                  p.updated_at = datetime()
    RETURN p.id AS id
    """
    result = neo4j.run_query(query, {
        "case_id": case_id,
        "normalized_number": normalized_number,
        "raw_values": raw_values,
        "first_seen": first_seen,
        "last_seen": last_seen,
    })
    return result[0] if result else {}


def upsert_account_node(case_id: str, normalized_identifier: str, account_type: str,
                        first_seen: str, last_seen: str) -> dict:
    neo4j = get_neo4j()
    query = """
    MERGE (a:Account {case_id: $case_id, normalized_identifier: $normalized_identifier})
    ON CREATE SET a.id = randomUUID(), a.case_id = $case_id,
                  a.normalized_identifier = $normalized_identifier,
                  a.account_type = $account_type,
                  a.first_seen_at = $first_seen,
                  a.last_seen_at = $last_seen,
                  a.created_at = datetime()
    ON MATCH SET  a.last_seen_at = CASE WHEN $last_seen > a.last_seen_at THEN $last_seen ELSE a.last_seen_at END,
                  a.updated_at = datetime()
    RETURN a.id AS id
    """
    result = neo4j.run_query(query, {
        "case_id": case_id,
        "normalized_identifier": normalized_identifier,
        "account_type": account_type,
        "first_seen": first_seen,
        "last_seen": last_seen,
    })
    return result[0] if result else {}


def upsert_device_node(case_id: str, imei: str) -> dict:
    neo4j = get_neo4j()
    query = """
    MERGE (d:Device {case_id: $case_id, imei: $imei})
    ON CREATE SET d.id = randomUUID(), d.case_id = $case_id, d.imei = $imei, d.created_at = datetime()
    RETURN d.id AS id
    """
    result = neo4j.run_query(query, {"case_id": case_id, "imei": imei})
    return result[0] if result else {}


def upsert_tower_node(case_id: str, tower_id: str) -> dict:
    neo4j = get_neo4j()
    query = """
    MERGE (t:Tower {case_id: $case_id, tower_id: $tower_id})
    ON CREATE SET t.id = randomUUID(), t.case_id = $case_id, t.tower_id = $tower_id, t.created_at = datetime()
    RETURN t.id AS id
    """
    result = neo4j.run_query(query, {"case_id": case_id, "tower_id": tower_id})
    return result[0] if result else {}


def upsert_document_node(case_id: str, evidence_id: str, evidence_code: str,
                          filename: str, sha256_hash: str, integrity_status: str) -> dict:
    neo4j = get_neo4j()
    query = """
    MERGE (d:Document {id: $evidence_id})
    ON CREATE SET d.id = $evidence_id, d.case_id = $case_id,
                  d.evidence_code = $evidence_code, d.filename = $filename,
                  d.sha256_hash = $sha256_hash, d.integrity_status = $integrity_status,
                  d.created_at = datetime()
    ON MATCH SET  d.integrity_status = $integrity_status, d.updated_at = datetime()
    RETURN d.id AS id
    """
    result = neo4j.run_query(query, {
        "evidence_id": evidence_id, "case_id": case_id, "evidence_code": evidence_code,
        "filename": filename, "sha256_hash": sha256_hash, "integrity_status": integrity_status,
    })
    return result[0] if result else {}


# ──────────────────────────────────────────────────────────────────────────
# Relationship upserts — every relationship carries full provenance
# ──────────────────────────────────────────────────────────────────────────

def _base_props(evidence_id: str, case_id: str, source_file_name: str,
                source_row_number: int, source_hash: str, event_timestamp_utc: str,
                raw_timestamp: str, verification_status: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "case_id": case_id,
        "source_file_name": source_file_name,
        "source_row_number": source_row_number,
        "source_hash": source_hash,
        "event_timestamp_utc": event_timestamp_utc,
        "raw_timestamp": raw_timestamp,
        "verification_status": verification_status,
        "relationship_status": "DIRECT_RECORD",
        "confidence_label": "DIRECT_SOURCE_RECORD",
    }


def create_called_edge(case_id: str, calling_number: str, called_number: str,
                       provenance: dict, duration_seconds: Optional[int] = None) -> dict:
    neo4j = get_neo4j()
    query = """
    MATCH (caller:Phone {case_id: $case_id, normalized_number: $calling_number})
    MATCH (callee:Phone {case_id: $case_id, normalized_number: $called_number})
    CREATE (caller)-[r:CALLED {
        id: randomUUID(),
        case_id: $case_id,
        evidence_id: $evidence_id,
        source_file_name: $source_file_name,
        source_row_number: $source_row_number,
        source_hash: $source_hash,
        event_timestamp_utc: $event_timestamp_utc,
        raw_timestamp: $raw_timestamp,
        duration_seconds: $duration_seconds,
        verification_status: $verification_status,
        relationship_status: $relationship_status,
        confidence_label: $confidence_label,
        created_at: datetime()
    }]->(callee)
    RETURN r.id AS id
    """
    params = {
        "case_id": case_id,
        "calling_number": calling_number,
        "called_number": called_number,
        "duration_seconds": duration_seconds,
        **provenance,
    }
    result = neo4j.run_query(query, params)
    return result[0] if result else {}


def create_transferred_to_edge(case_id: str, sender_id: str, receiver_id: str,
                                provenance: dict, amount: float, currency: str,
                                transaction_id: Optional[str], transaction_type: Optional[str]) -> dict:
    neo4j = get_neo4j()
    query = """
    MATCH (sender:Account {case_id: $case_id, normalized_identifier: $sender_id})
    MATCH (receiver:Account {case_id: $case_id, normalized_identifier: $receiver_id})
    CREATE (sender)-[r:TRANSFERRED_TO {
        id: randomUUID(),
        case_id: $case_id,
        evidence_id: $evidence_id,
        source_file_name: $source_file_name,
        source_row_number: $source_row_number,
        source_hash: $source_hash,
        event_timestamp_utc: $event_timestamp_utc,
        raw_timestamp: $raw_timestamp,
        amount: $amount,
        currency: $currency,
        transaction_id: $transaction_id,
        transaction_type: $transaction_type,
        verification_status: $verification_status,
        relationship_status: $relationship_status,
        confidence_label: $confidence_label,
        created_at: datetime()
    }]->(receiver)
    RETURN r.id AS id
    """
    params = {
        "case_id": case_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "amount": amount,
        "currency": currency,
        "transaction_id": transaction_id,
        "transaction_type": transaction_type,
        **provenance,
    }
    result = neo4j.run_query(query, params)
    return result[0] if result else {}


def create_used_device_edge(case_id: str, phone_number: str, imei: str, provenance: dict) -> dict:
    neo4j = get_neo4j()
    query = """
    MATCH (p:Phone {case_id: $case_id, normalized_number: $phone_number})
    MATCH (d:Device {case_id: $case_id, imei: $imei})
    MERGE (p)-[r:USED_DEVICE {case_id: $case_id, evidence_id: $evidence_id,
                               source_row_number: $source_row_number}]->(d)
    ON CREATE SET r.id = randomUUID(), r.source_file_name = $source_file_name,
                  r.source_hash = $source_hash, r.event_timestamp_utc = $event_timestamp_utc,
                  r.verification_status = $verification_status,
                  r.relationship_status = $relationship_status,
                  r.confidence_label = $confidence_label,
                  r.created_at = datetime()
    RETURN r.id AS id
    """
    params = {"case_id": case_id, "phone_number": phone_number, "imei": imei, **provenance}
    result = neo4j.run_query(query, params)
    return result[0] if result else {}


def create_connected_to_tower_edge(case_id: str, phone_number: str, tower_id: str,
                                   provenance: dict) -> dict:
    neo4j = get_neo4j()
    query = """
    MATCH (p:Phone {case_id: $case_id, normalized_number: $phone_number})
    MATCH (t:Tower {case_id: $case_id, tower_id: $tower_id})
    MERGE (p)-[r:CONNECTED_TO_TOWER {case_id: $case_id, evidence_id: $evidence_id,
                                      source_row_number: $source_row_number}]->(t)
    ON CREATE SET r.id = randomUUID(), r.source_file_name = $source_file_name,
                  r.source_hash = $source_hash, r.event_timestamp_utc = $event_timestamp_utc,
                  r.verification_status = $verification_status,
                  r.relationship_status = $relationship_status,
                  r.confidence_label = $confidence_label,
                  r.created_at = datetime()
    RETURN r.id AS id
    """
    params = {"case_id": case_id, "phone_number": phone_number, "tower_id": tower_id, **provenance}
    result = neo4j.run_query(query, params)
    return result[0] if result else {}
