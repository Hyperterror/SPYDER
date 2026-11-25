"""
Live Entity Resolution Service (Milestone 3).

Bridges live evidence ingestion (PostgreSQL ParsedRecord) with the Entity Resolution
pipeline (entity_resolution.predict.EntityResolutionPredictor) without touching
synthetic ground_truth files and without self-comparing identical records.
"""
from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.evidence import EvidenceItem, ParsedRecord
from app.models.intelligence import IdentityHypothesis, IntelligenceLeadRecord, ModelArtifactRegistry

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from entity_resolution.normalize import (  # noqa: E402
    levenshtein_similarity,
    normalize_alias,
    normalize_imei,
    normalize_ip,
    normalize_name,
    normalize_phone,
    normalize_vehicle_reg,
    token_jaccard_similarity,
)
from entity_resolution.predict import EntityResolutionPredictor  # noqa: E402

ER_MODEL_VERSION = "er-xgb-1.0.0"


def _ensure_model_registered(db: Session) -> None:
    existing = db.query(ModelArtifactRegistry).filter(
        ModelArtifactRegistry.model_name == "entity_resolution_xgb",
        ModelArtifactRegistry.version == ER_MODEL_VERSION,
    ).first()
    if not existing:
        db.add(ModelArtifactRegistry(
            id=uuid.uuid4(),
            model_name="entity_resolution_xgb",
            version=ER_MODEL_VERSION,
            feature_schema_version="28f-v1",
            artifact_uri="output/entity_resolution/model/xgboost_entity_resolution.json",
            training_snapshot_id="synthetic_v1",
            evaluation_report={"note": "Prototype synthetic baseline; see docs/ML_EVALUATION.md"},
            is_active=True,
        ))
        db.commit()


def _hypothesis_key(case_a: str, person_a: str, case_b: str, person_b: str) -> str:
    left = f"{case_a}:{person_a}"
    right = f"{case_b}:{person_b}"
    pair = sorted([left, right])
    return hashlib.sha256(f"{pair[0]}|{pair[1]}".encode("utf-8")).hexdigest()[:32]


def _serialize_profile_for_snapshot(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "person_id": profile["person_id"],
        "case_id": profile["case_id"],
        "case_code": profile.get("case_code"),
        "raw_name": profile["raw_name"],
        "raw_alias": profile.get("raw_alias", ""),
        "age_group": profile.get("age_group", "UNKNOWN"),
        "address": profile.get("address", ""),
        "phone_id": profile.get("phone_id", ""),
        "device_id": profile.get("device_id", ""),
        "phones": sorted(list(profile.get("phone_last10s", set()))),
        "imeis": sorted(list(profile.get("imeis", set()))),
        "ip_addresses": sorted(list(profile.get("ip_addresses", set()))),
        "vehicles": sorted(list(profile.get("vehicles", set()))),
        "locations": sorted(list(profile.get("locations", set()))),
        "social_handles": sorted(list(profile.get("social_handles", set()))),
        "contacts": sorted(list(profile.get("contacts", set()))),
    }


def build_observable_profiles_from_db(db: Session) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Build normalized observable person profiles keyed by (case_id_str, person_id)
    strictly from ACTIVE EvidenceItem ParsedRecords in PostgreSQL.
    """
    cases = {str(c.id): c for c in db.query(Case).all()}
    rows = (
        db.query(ParsedRecord, EvidenceItem)
        .join(EvidenceItem, ParsedRecord.evidence_id == EvidenceItem.id)
        .filter(
            ParsedRecord.parse_status == "VALID",
            EvidenceItem.lifecycle_status == "ACTIVE",
        )
        .all()
    )

    profiles: Dict[Tuple[str, str], Dict[str, Any]] = {}
    records_by_case: Dict[str, List[Tuple[ParsedRecord, EvidenceItem]]] = {}
    for rec, ev in rows:
        records_by_case.setdefault(str(rec.case_id), []).append((rec, ev))

    # 1. Base PERSONS records
    for rec, ev in rows:
        if rec.record_type != "PERSONS":
            continue
        nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
        raw = rec.raw_record if isinstance(rec.raw_record, dict) else {}
        cid = str(rec.case_id)
        pid = nr.get("person_id") or raw.get("person_id") or ""
        name = nr.get("raw_name") or raw.get("name") or ""
        if not pid or not name:
            continue

        alias = raw.get("alias", "") or nr.get("alias", "")
        norm_name = normalize_name(name)
        norm_alias = normalize_alias(alias)
        phone_raw = nr.get("phone_id") or raw.get("phone_id") or ""
        phone_norm = normalize_phone(phone_raw)["last10"]
        dev_id = nr.get("device_id") or raw.get("device_id") or ""
        case_obj = cases.get(cid)

        key = (cid, pid)
        prof = profiles.setdefault(key, {
            "person_id": pid,
            "case_id": cid,
            "case_code": case_obj.case_code if case_obj else cid,
            "raw_name": name,
            "norm_name": norm_name["clean"],
            "name_tokens": norm_name["tokens"],
            "name_initials": norm_name["initials"],
            "raw_alias": alias,
            "norm_alias": norm_alias["clean"],
            "alias_tokens": norm_alias["tokens"],
            "age_group": raw.get("age_group", "UNKNOWN"),
            "role": raw.get("role", "Person of Interest"),
            "occupation": raw.get("occupation", ""),
            "address": raw.get("address", ""),
            "phone_id": phone_raw,
            "device_id": dev_id,
            "phones": set(),
            "phone_last10s": set(),
            "imeis": set(),
            "ip_addresses": set(),
            "locations": set(),
            "vehicles": set(),
            "bank_accounts": set(),
            "social_handles": set(),
            "emails": set(),
            "contacts": set(),
            "source_records": [],
        })
        if phone_norm:
            prof["phones"].add(phone_norm)
            prof["phone_last10s"].add(phone_norm)
        prof["source_records"].append({
            "reason": f"Observable person dossier entry for {name} ({pid})",
            "evidence_type": "PERSONS",
            "record_id": str(ev.id),
            "evidence_id": str(ev.id),
            "source_file": ev.sanitized_filename,
            "source_row": rec.source_row_number,
            "case_id": case_obj.case_code if case_obj else cid,
            "record_type": "PERSONS",
        })

    # 2. Enrich profiles from CDR, DEVICE, VEHICLE, TRAVEL, CHAT in same case
    for (cid, pid), prof in profiles.items():
        for rec, ev in records_by_case.get(cid, []):
            nr = rec.normalized_record if isinstance(rec.normalized_record, dict) else {}
            if rec.record_type == "DEVICE":
                if (nr.get("person_id") == pid) or (prof["device_id"] and nr.get("device_id") == prof["device_id"]):
                    ip = normalize_ip(nr.get("ip_address", ""))["clean"]
                    if ip:
                        prof["ip_addresses"].add(ip)
                    if nr.get("device_id") and not prof["device_id"]:
                        prof["device_id"] = nr["device_id"]
            elif rec.record_type == "VEHICLE":
                if nr.get("owner_person_id") == pid and nr.get("vehicle_number"):
                    vreg = normalize_vehicle_reg(nr["vehicle_number"])["clean"]
                    if vreg:
                        prof["vehicles"].add(vreg)
                    if nr.get("sighting_location"):
                        prof["locations"].add(nr["sighting_location"])
            elif rec.record_type == "TRAVEL":
                if nr.get("person_id") == pid:
                    if nr.get("origin"):
                        prof["locations"].add(nr["origin"])
                    if nr.get("destination"):
                        prof["locations"].add(nr["destination"])
            elif rec.record_type == "CDR":
                caller10 = normalize_phone(nr.get("calling_number", ""))["last10"]
                callee10 = normalize_phone(nr.get("called_number", ""))["last10"]
                if caller10 and caller10 in prof["phone_last10s"]:
                    if callee10:
                        prof["contacts"].add(callee10)
                    if nr.get("imei"):
                        imei_clean = normalize_imei(nr["imei"])["clean"]
                        if imei_clean:
                            prof["imeis"].add(imei_clean)
                elif callee10 and callee10 in prof["phone_last10s"]:
                    if caller10:
                        prof["contacts"].add(caller10)

    return profiles


def _blocking_reasons(p1: Dict[str, Any], p2: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    shared_phones = p1["phone_last10s"] & p2["phone_last10s"]
    if shared_phones:
        reasons.append(f"shared_phone:{sorted(shared_phones)[0]}")

    if p1["device_id"] and p1["device_id"] == p2["device_id"] and p1["device_id"] != "DEV_UNVERIFIED":
        reasons.append(f"shared_device_id:{p1['device_id']}")

    shared_imeis = p1["imeis"] & p2["imeis"]
    if shared_imeis:
        reasons.append(f"shared_imei:{sorted(shared_imeis)[0]}")

    shared_vehs = p1["vehicles"] & p2["vehicles"]
    if shared_vehs:
        reasons.append(f"shared_vehicle:{sorted(shared_vehs)[0]}")

    lev_sim = levenshtein_similarity(p1["norm_name"], p2["norm_name"])
    tok_sim = token_jaccard_similarity(p1["name_tokens"], p2["name_tokens"])
    if lev_sim >= 0.65 or tok_sim >= 0.5:
        reasons.append(f"name_similarity:lev={lev_sim:.2f},tok={tok_sim:.2f}")

    if p1["norm_alias"] and p2["norm_alias"]:
        if levenshtein_similarity(p1["norm_alias"], p2["norm_alias"]) >= 0.75:
            reasons.append(f"alias_similarity:{p1['norm_alias']}")

    return reasons


def evaluate_live_entity_resolution(db: Session, target_case_id: str) -> int:
    """
    Generate cross-case IdentityHypothesis records for PERSONS in target_case_id
    against distinct PERSONS in other cases using conservative blocking + EntityResolutionPredictor.
    Never self-compares and never auto-merges identities.
    """
    profiles = build_observable_profiles_from_db(db)
    target_profiles = [p for (cid, _), p in profiles.items() if cid == str(target_case_id)]
    other_profiles = [p for (cid, _), p in profiles.items() if cid != str(target_case_id)]

    if not target_profiles or not other_profiles:
        return 0

    _ensure_model_registered(db)
    predictor = EntityResolutionPredictor()
    evaluated = 0

    for p1 in target_profiles:
        for p2 in other_profiles:
            reasons = _blocking_reasons(p1, p2)
            if not reasons:
                continue

            pred = predictor.predict_pair(p1, p2)
            evaluated += 1
            prob = float(pred["match_probability"])
            tier = pred["confidence_tier"]
            expl = pred["explanation"]

            # Canonical ordering so key is deterministic regardless of upload order
            if f"{p1['case_id']}:{p1['person_id']}" <= f"{p2['case_id']}:{p2['person_id']}":
                left, right = p1, p2
            else:
                left, right = p2, p1

            hkey = _hypothesis_key(left["case_id"], left["person_id"], right["case_id"], right["person_id"])
            existing = db.query(IdentityHypothesis).filter(IdentityHypothesis.hypothesis_key == hkey).first()

            new_status = "PENDING_REVIEW" if prob >= 0.70 else "CANDIDATE"
            if existing:
                existing.match_probability = prob
                existing.confidence_tier = tier
                existing.model_version = ER_MODEL_VERSION
                existing.feature_explanation = pred["features"]
                existing.supporting_evidence = expl.get("supporting_reasons", [])
                existing.conflicting_evidence = expl.get("conflicting_reasons", [])
                existing.blocking_reasons = reasons
                existing.profile_a_snapshot = _serialize_profile_for_snapshot(left)
                existing.profile_b_snapshot = _serialize_profile_for_snapshot(right)
                # Preserve explicit human review decisions!
                if existing.status in ("CANDIDATE", "PENDING_REVIEW"):
                    existing.status = new_status
                hyp = existing
            else:
                hyp = IdentityHypothesis(
                    id=uuid.uuid4(),
                    hypothesis_key=hkey,
                    person_a_ref=left["person_id"],
                    person_b_ref=right["person_id"],
                    person_a_name=left["raw_name"],
                    person_b_name=right["raw_name"],
                    case_a_id=uuid.UUID(left["case_id"]),
                    case_b_id=uuid.UUID(right["case_id"]),
                    case_a_ref=left.get("case_code") or left["case_id"],
                    case_b_ref=right.get("case_code") or right["case_id"],
                    match_probability=prob,
                    confidence_tier=tier,
                    model_version=ER_MODEL_VERSION,
                    feature_explanation=pred["features"],
                    supporting_evidence=expl.get("supporting_reasons", []),
                    conflicting_evidence=expl.get("conflicting_reasons", []),
                    blocking_reasons=reasons,
                    profile_a_snapshot=_serialize_profile_for_snapshot(left),
                    profile_b_snapshot=_serialize_profile_for_snapshot(right),
                    status=new_status,
                )
                db.add(hyp)

            # Surface high-confidence cross-case hypothesis as an actionable Investigation Lead
            if prob >= 0.70:
                lead_code = f"LEAD_ER_{hkey[:12].upper()}"
                existing_lead = db.query(IntelligenceLeadRecord).filter(
                    IntelligenceLeadRecord.lead_code == lead_code
                ).first()
                src_cases = sorted({left["case_id"], left.get("case_code") or left["case_id"]})
                tgt_cases = sorted({right["case_id"], right.get("case_code") or right["case_id"]})
                sup_records = left.get("source_records", []) + right.get("source_records", [])
                caveats = [
                    "Provisional cross-case identity hypothesis generated by Entity Resolution; requires human verification.",
                    "Does not establish criminal conduct or automatically merge observational identities.",
                ]
                if existing_lead:
                    existing_lead.prediction_score = prob
                    existing_lead.priority_tier = "HIGH" if prob >= 0.90 else "REVIEW"
                    existing_lead.explanation = expl.get("summary", "")
                    existing_lead.supporting_records = sup_records
                    existing_lead.common_intermediates = reasons
                else:
                    db.add(IntelligenceLeadRecord(
                        id=uuid.uuid4(),
                        lead_code=lead_code,
                        source_entity=f"{left['raw_name']} ({left['person_id']})",
                        target_entity=f"{right['raw_name']} ({right['person_id']})",
                        source_case_ids=[left.get("case_code") or left["case_id"]],
                        target_case_ids=[right.get("case_code") or right["case_id"]],
                        is_cross_case=True,
                        candidate_relationship_type="Candidate Identity Association",
                        model_version=ER_MODEL_VERSION,
                        prediction_score=round(prob, 4),
                        priority_tier="HIGH" if prob >= 0.90 else "REVIEW",
                        evidence_strength="STRONG" if prob >= 0.90 else "MODERATE",
                        explanation=expl.get("summary", f"Potential cross-case identity match between {left['person_id']} and {right['person_id']}."),
                        supporting_modalities=["ENTITY_RESOLUTION", "PERSONS"],
                        common_intermediates=reasons,
                        caveats=caveats,
                        supporting_records=sup_records,
                        conflicting_records=[{"reason": c} for c in expl.get("conflicting_reasons", [])],
                        status="NEW",
                    ))

    db.commit()
    return evaluated
