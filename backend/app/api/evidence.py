from __future__ import annotations
import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.authz import require_case_access, require_evidence_access
from app.models.audit import AuditEvent
from app.models.evidence import EvidenceItem, ParsingJob, ParsedRecord, EvidenceProcessingJob
from app.services.storage import get_storage
from app.services.hashing import calculate_sha256, verify_integrity
from app.services.audit_svc import create_audit_event
from app.services.graph_upsert import (
    upsert_phone_node, upsert_account_node, upsert_device_node,
    upsert_tower_node, upsert_document_node,
    create_called_edge, create_transferred_to_edge,
    create_used_device_edge, create_connected_to_tower_edge,
)
from app.services.evidence_validator import validate_file_security, EvidenceValidationError
from app.services.evidence_orchestrator import get_orchestrator
from app.services.ocr import extract_text_for_upload
from app.worker.tasks import process_evidence_job_task

router = APIRouter(prefix="/api/v1/cases", tags=["evidence"])
direct_router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json", ".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = settings.MAX_UPLOAD_BYTES
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB bounded streaming chunks
EXTRACTED_TEXT_PREVIEW_CHARS = 500


async def _read_upload_bounded(file: UploadFile, max_size: int) -> tuple[bytes, str]:
    """
    Read UploadFile in bounded 1 MB chunks into a temporary file on disk,
    computing SHA-256 incrementally and aborting immediately if size exceeds max_size.
    """
    hasher = hashlib.sha256()
    total_bytes = 0
    with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b") as tmp:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {max_size // (1024 * 1024)} MB.",
                )
            hasher.update(chunk)
            tmp.write(chunk)
        tmp.seek(0)
        return tmp.read(), hasher.hexdigest()


def _next_evidence_code(case_id: uuid.UUID, db: Session) -> str:
    count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).count()
    return f"EVD-{str(count + 1).zfill(3)}"


class WithdrawEvidenceRequest(BaseModel):
    reason: str


@router.get("/{case_id}/evidence")
def list_evidence(
    case_id: str,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case = require_case_access(case_id, current_user, db)
    q = db.query(EvidenceItem).filter(EvidenceItem.case_id == case.id)
    if not include_inactive:
        q = q.filter(EvidenceItem.lifecycle_status == "ACTIVE")
    items = q.order_by(EvidenceItem.uploaded_at.desc()).all()
    return [_evidence_to_dict(e) for e in items]


@router.post("/{case_id}/evidence/upload", status_code=201)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    source_label: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    acquisition_source: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case = require_case_access(
        case_id, current_user, db, required_case_roles=["CASE_OWNER", "INVESTIGATOR", "LEAD_INVESTIGATOR", "ANALYST"]
    )

    file_bytes, sha256 = await _read_upload_bounded(file, MAX_FILE_SIZE)

    try:
        sanitized = validate_file_security(file.filename or "upload.csv", file_bytes, max_size=MAX_FILE_SIZE)
    except EvidenceValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    ext = os.path.splitext(sanitized)[1].lower()
    extracted_text = extract_text_for_upload(sanitized, file_bytes)

    # Duplicate detection within same case for active evidence
    existing = db.query(EvidenceItem).filter(
        EvidenceItem.case_id == case.id,
        EvidenceItem.sha256_hash == sha256,
        EvidenceItem.lifecycle_status == "ACTIVE",
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate file: SHA-256 matches existing evidence {existing.evidence_code}",
        )

    evidence_id = uuid.uuid4()
    object_key = f"cases/{case.id}/evidence/{evidence_id}/original/{sanitized}"

    storage = get_storage()
    storage.upload(object_key, file_bytes, file.content_type or "application/octet-stream")

    acq_meta = {"acquisition_source": acquisition_source} if acquisition_source else None

    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case.id,
        evidence_code=_next_evidence_code(case.id, db),
        original_filename=file.filename or sanitized,
        sanitized_filename=sanitized,
        file_extension=ext,
        mime_type=file.content_type,
        file_size_bytes=len(file_bytes),
        object_storage_bucket=storage.bucket,
        object_storage_key=object_key,
        source_label=source_label,
        description=description,
        extracted_text=extracted_text,
        sha256_hash=sha256,
        integrity_status="UNVERIFIED",
        uploaded_by=current_user.id,
        parsing_status="PENDING",
        processing_status="UPLOADED",
        is_original=True,
        version_number=1,
        lifecycle_status="ACTIVE",
        acquisition_metadata=acq_meta,
    )
    db.add(evidence)

    job = EvidenceProcessingJob(
        evidence_id=evidence_id,
        case_id=case.id,
        job_type="EVIDENCE_INGESTION",
        status="UPLOADED",
        pipeline_version="7A.1.0",
        initiated_by=current_user.id,
        records_processed=0,
    )
    db.add(job)

    db.commit()
    db.refresh(evidence)

    try:
        upsert_document_node(
            case_id=str(case.id), evidence_id=str(evidence_id),
            evidence_code=evidence.evidence_code, filename=sanitized,
            sha256_hash=sha256, integrity_status="UNVERIFIED",
        )
    except Exception:
        pass

    create_audit_event(
        db=db, event_type="EVIDENCE_UPLOADED", case_id=str(case.id),
        evidence_id=str(evidence_id), actor_user_id=str(current_user.id),
        metadata={
            "filename": evidence.original_filename,
            "sanitized_filename": sanitized,
            "sha256": sha256,
            "size_bytes": len(file_bytes),
            "version_number": 1,
            "extracted_text_chars": len(extracted_text) if extracted_text else 0,
        },
    )

    return _evidence_to_dict(evidence)


@router.post("/{case_id}/evidence/{evidence_id}/supersede", status_code=201)
async def supersede_evidence(
    case_id: str,
    evidence_id: str,
    file: UploadFile = File(...),
    reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Preserve original evidence untouched and register a new replacement version."""
    case, old_ev = require_evidence_access(
        case_id, evidence_id, current_user, db,
        required_case_roles=["CASE_OWNER", "INVESTIGATOR", "LEAD_INVESTIGATOR"],
    )

    file_bytes, sha256 = await _read_upload_bounded(file, MAX_FILE_SIZE)
    try:
        sanitized = validate_file_security(file.filename or "upload.csv", file_bytes, max_size=MAX_FILE_SIZE)
    except EvidenceValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    ext = os.path.splitext(sanitized)[1].lower()
    extracted_text = extract_text_for_upload(sanitized, file_bytes)

    new_id = uuid.uuid4()
    new_version = (old_ev.version_number or 1) + 1
    object_key = f"cases/{case.id}/evidence/{new_id}/v{new_version}/{sanitized}"

    storage = get_storage()
    storage.upload(object_key, file_bytes, file.content_type or "application/octet-stream")

    old_ev.lifecycle_status = "SUPERSEDED"
    old_ev.updated_at = datetime.now(timezone.utc)

    new_ev = EvidenceItem(
        id=new_id,
        case_id=case.id,
        evidence_code=f"{old_ev.evidence_code}-v{new_version}",
        original_filename=file.filename or sanitized,
        sanitized_filename=sanitized,
        file_extension=ext,
        mime_type=file.content_type,
        file_size_bytes=len(file_bytes),
        object_storage_bucket=storage.bucket,
        object_storage_key=object_key,
        source_label=old_ev.source_label,
        description=reason or old_ev.description,
        extracted_text=extracted_text,
        sha256_hash=sha256,
        integrity_status="UNVERIFIED",
        uploaded_by=current_user.id,
        parsing_status="PENDING",
        processing_status="UPLOADED",
        is_original=True,
        version_number=new_version,
        supersedes_evidence_id=old_ev.id,
        lifecycle_status="ACTIVE",
    )
    db.add(new_ev)
    db.commit()
    db.refresh(new_ev)

    create_audit_event(
        db=db,
        event_type="EVIDENCE_SUPERSEDED",
        case_id=str(case.id),
        evidence_id=str(new_ev.id),
        actor_user_id=str(current_user.id),
        metadata={
            "superseded_evidence_id": str(old_ev.id),
            "superseded_sha256": old_ev.sha256_hash,
            "new_sha256": sha256,
            "version_number": new_version,
            "reason": reason,
        },
    )
    return _evidence_to_dict(new_ev)


@router.post("/{case_id}/evidence/{evidence_id}/withdraw")
def withdraw_evidence(
    case_id: str,
    evidence_id: str,
    body: WithdrawEvidenceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark evidence withdrawn without deleting original bytes or audit history."""
    if current_user.role not in ("ADMIN", "SUPERVISOR", "INVESTIGATOR"):
        raise HTTPException(status_code=403, detail="Not authorized to withdraw evidence")
    case, ev = require_evidence_access(
        case_id, evidence_id, current_user, db,
        required_case_roles=["CASE_OWNER", "INVESTIGATOR", "LEAD_INVESTIGATOR"],
    )
    ev.lifecycle_status = "WITHDRAWN"
    ev.withdrawn_reason = body.reason
    ev.withdrawn_by = current_user.id
    ev.withdrawn_at = datetime.now(timezone.utc)
    ev.updated_at = datetime.now(timezone.utc)
    db.commit()

    create_audit_event(
        db=db,
        event_type="EVIDENCE_WITHDRAWN",
        case_id=str(case.id),
        evidence_id=str(ev.id),
        actor_user_id=str(current_user.id),
        metadata={"reason": body.reason, "sha256": ev.sha256_hash},
    )
    return _evidence_to_dict(ev)


@router.get("/{case_id}/evidence/{evidence_id}")
def get_evidence(case_id: str, evidence_id: str, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    create_audit_event(db=db, event_type="EVIDENCE_VIEWED", case_id=str(case.id),
                       evidence_id=str(ev.id), actor_user_id=str(current_user.id), metadata={})
    return _evidence_to_dict(ev)


@router.get("/{case_id}/evidence/{evidence_id}/download")
def download_evidence(case_id: str, evidence_id: str, db: Session = Depends(get_db),
                      current_user=Depends(get_current_user)):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    storage = get_storage()
    try:
        file_bytes = storage.download(ev.object_storage_bucket, ev.object_storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stored evidence object not found")

    create_audit_event(
        db=db,
        event_type="EVIDENCE_DOWNLOADED",
        case_id=str(case.id),
        evidence_id=str(ev.id),
        actor_user_id=str(current_user.id),
        metadata={"sha256": ev.sha256_hash, "filename": ev.sanitized_filename},
    )
    return StreamingResponse(
        iter([file_bytes]),
        media_type=ev.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{ev.sanitized_filename}"',
            "X-Content-SHA256": ev.sha256_hash,
        },
    )


@router.post("/{case_id}/evidence/{evidence_id}/verify-integrity")
def verify_evidence_integrity(case_id: str, evidence_id: str,
                               db: Session = Depends(get_db),
                               current_user=Depends(get_current_user)):
    _, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    return verify_integrity(ev, db, str(current_user.id))


@router.post("/{case_id}/evidence/{evidence_id}/parse")
def trigger_parse(
    case_id: str,
    evidence_id: str,
    response: Response,
    column_mapping: Optional[dict] = None,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Deprecated compatibility endpoint: delegates directly to the canonical
    evidence processing pipeline.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</api/v1/cases/{case_id}/evidence/{evidence_id}/process>; rel="successor-version"'
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)

    if ev.file_extension not in (".csv", ".xlsx", ".json"):
        raise HTTPException(status_code=422, detail="Only CSV/XLSX/JSON files can be parsed via /parse")

    orchestrator = get_orchestrator()
    job = orchestrator.create_processing_job(
        evidence_id=str(ev.id),
        case_id=str(case.id),
        user_id=str(current_user.id),
        db=db,
        job_type="LEGACY_PARSE_DELEGATED",
    )

    if run_sync:
        res = orchestrator.execute_pipeline(str(job.id), db=db)
        return {
            "job_id": str(job.id),
            "status": res.get("status", "COMPLETED"),
            "job_type": job.job_type,
            "deprecated": True,
        }

    async_res = process_evidence_job_task.delay(str(job.id))
    job.celery_task_id = getattr(async_res, "id", None)
    db.commit()
    return {"job_id": str(job.id), "status": "QUEUED", "job_type": job.job_type, "deprecated": True}


def _run_parse_job(job_id: str, evidence: EvidenceItem, column_mapping: dict, db: Session):
    """Background task: parse evidence file and upsert graph nodes/edges."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(ParsingJob).filter(ParsingJob.id == job_id).first()
        ev = db.query(EvidenceItem).filter(EvidenceItem.id == evidence.id).first()
        if not job or not ev:
            return

        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        storage = get_storage()
        file_bytes = storage.download(ev.object_storage_bucket, ev.object_storage_key)

        if job.job_type == "CDR":
            result = parse_cdr_csv(
                file_bytes, column_mapping, str(ev.case_id),
                str(ev.id), ev.original_filename, ev.sha256_hash,
            )
            _store_cdr_records(result, ev, db)
        else:
            result = parse_transaction_csv(
                file_bytes, column_mapping, str(ev.case_id),
                str(ev.id), ev.original_filename, ev.sha256_hash,
            )
            _store_transaction_records(result, ev, db)

        job.status = "COMPLETED" if result["invalid_rows"] == 0 else "PARTIALLY_COMPLETED"
        job.completed_at = datetime.now(timezone.utc)
        job.result_summary = {
            "total_rows": result["total_rows"],
            "valid_rows": result["valid_rows"],
            "invalid_rows": result["invalid_rows"],
        }
        ev.parsing_status = "COMPLETED" if result["invalid_rows"] == 0 else "PARTIALLY_COMPLETED"
        db.commit()

        create_audit_event(
            db=db, event_type="EVIDENCE_PARSING_COMPLETED",
            case_id=str(ev.case_id), evidence_id=str(ev.id),
            metadata=job.result_summary,
        )
    except Exception as e:
        try:
            job = db.query(ParsingJob).filter(ParsingJob.id == job_id).first()
            ev = db.query(EvidenceItem).filter(EvidenceItem.id == evidence.id).first()
            if job:
                job.status = "FAILED"
                job.error_message = str(e)
            if ev:
                ev.parsing_status = "FAILED"
                ev.parsing_error = str(e)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _store_cdr_records(result: dict, ev: EvidenceItem, db: Session):
    case_id = str(ev.case_id)
    provenance_base = dict(
        evidence_id=str(ev.id), case_id=case_id,
        source_file_name=ev.original_filename, source_hash=ev.sha256_hash,
        verification_status=ev.integrity_status,
        relationship_status="DIRECT_RECORD", confidence_label="DIRECT_SOURCE_RECORD",
    )

    for rec in result["records"]:
        nr = rec["normalized_record"]
        db.add(ParsedRecord(
            case_id=ev.case_id, evidence_id=ev.id, record_type="CDR",
            source_row_number=rec["source_row_number"],
            raw_record=rec["raw_record"], normalized_record=nr,
            parse_status="VALID",
        ))

        upsert_phone_node(case_id, nr["calling_number"],
                          [nr.get("raw_record", {}).get("calling_number", nr["calling_number"])],
                          nr["start_time_utc"], nr["start_time_utc"])
        upsert_phone_node(case_id, nr["called_number"],
                          [nr.get("raw_record", {}).get("called_number", nr["called_number"])],
                          nr["start_time_utc"], nr["start_time_utc"])

        prov = {**provenance_base,
                "source_row_number": rec["source_row_number"],
                "event_timestamp_utc": nr["start_time_utc"],
                "raw_timestamp": nr.get("raw_start_time", "")}
        create_called_edge(case_id, nr["calling_number"], nr["called_number"],
                           prov, nr.get("duration_seconds"))

        if nr.get("imei"):
            upsert_device_node(case_id, nr["imei"])
            create_used_device_edge(case_id, nr["calling_number"], nr["imei"], prov)

        if nr.get("tower_id"):
            upsert_tower_node(case_id, nr["tower_id"])
            create_connected_to_tower_edge(case_id, nr["calling_number"], nr["tower_id"], prov)

    for err in result["errors"]:
        db.add(ParsedRecord(
            case_id=ev.case_id, evidence_id=ev.id, record_type="CDR",
            source_row_number=err["source_row_number"],
            raw_record=err["raw_record"], normalized_record={},
            parse_status="INVALID", parse_error=err["parse_error"],
        ))

    db.commit()


def _store_transaction_records(result: dict, ev: EvidenceItem, db: Session):
    case_id = str(ev.case_id)
    provenance_base = dict(
        evidence_id=str(ev.id), case_id=case_id,
        source_file_name=ev.original_filename, source_hash=ev.sha256_hash,
        verification_status=ev.integrity_status,
        relationship_status="DIRECT_RECORD", confidence_label="DIRECT_SOURCE_RECORD",
    )

    for rec in result["records"]:
        nr = rec["normalized_record"]
        db.add(ParsedRecord(
            case_id=ev.case_id, evidence_id=ev.id, record_type="TRANSACTION",
            source_row_number=rec["source_row_number"],
            raw_record=rec["raw_record"], normalized_record=nr,
            parse_status="VALID",
        ))

        upsert_account_node(case_id, nr["sender_identifier"],
                            nr.get("transaction_type", "UPI"),
                            nr["timestamp_utc"], nr["timestamp_utc"])
        upsert_account_node(case_id, nr["receiver_identifier"],
                            nr.get("transaction_type", "UPI"),
                            nr["timestamp_utc"], nr["timestamp_utc"])

        prov = {**provenance_base,
                "source_row_number": rec["source_row_number"],
                "event_timestamp_utc": nr["timestamp_utc"],
                "raw_timestamp": nr.get("raw_timestamp", "")}
        create_transferred_to_edge(
            case_id, nr["sender_identifier"], nr["receiver_identifier"],
            prov, nr["amount"], nr["currency"], nr.get("transaction_id"), nr.get("transaction_type"),
        )

    for err in result["errors"]:
        db.add(ParsedRecord(
            case_id=ev.case_id, evidence_id=ev.id, record_type="TRANSACTION",
            source_row_number=err["source_row_number"],
            raw_record=err["raw_record"], normalized_record={},
            parse_status="INVALID", parse_error=err["parse_error"],
        ))

    db.commit()


@router.get("/{case_id}/evidence/{evidence_id}/parsed-records")
def get_parsed_records(
    case_id: str, evidence_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    q = db.query(ParsedRecord).filter(
        ParsedRecord.case_id == case.id, ParsedRecord.evidence_id == ev.id
    )
    if status:
        q = q.filter(ParsedRecord.parse_status == status.upper())
    total = q.count()
    records = q.order_by(ParsedRecord.source_row_number).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": [
            {
                "id": str(r.id),
                "record_type": r.record_type,
                "source_row_number": r.source_row_number,
                "raw_record": r.raw_record,
                "normalized_record": r.normalized_record,
                "parse_status": r.parse_status,
                "parse_error": r.parse_error,
            }
            for r in records
        ],
    }


@router.get("/{case_id}/evidence/{evidence_id}/audit")
def get_evidence_audit(case_id: str, evidence_id: str,
                       db: Session = Depends(get_db),
                       current_user=Depends(get_current_user)):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    events = db.query(AuditEvent).filter(
        AuditEvent.case_id == case.id,
        AuditEvent.evidence_id == ev.id,
    ).order_by(AuditEvent.event_timestamp.desc(), AuditEvent.sequence_number.desc()).all()
    return [
        {
            "id": str(e.id),
            "sequence_number": e.sequence_number,
            "event_type": e.event_type,
            "event_timestamp": e.event_timestamp.isoformat(),
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "event_metadata": e.event_metadata,
            "event_hash": e.event_hash,
            "previous_event_hash": e.previous_event_hash,
        }
        for e in events
    ]


@router.post("/{case_id}/evidence/{evidence_id}/process")
def process_evidence_case(
    case_id: str,
    evidence_id: str,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)

    orchestrator = get_orchestrator()
    job = orchestrator.create_processing_job(
        evidence_id=str(ev.id),
        case_id=str(case.id),
        user_id=str(current_user.id),
        db=db,
    )

    if run_sync:
        res = orchestrator.execute_pipeline(str(job.id), db=db)
        return {
            "job_id": str(job.id),
            "evidence_id": str(ev.id),
            "case_id": str(case.id),
            "status": res.get("status", "COMPLETED"),
            "records_processed": res.get("records_processed", 0),
            "pipeline_version": job.pipeline_version,
            "graph_snapshot_version": res.get("graph_snapshot_version"),
            "error_message": res.get("error"),
        }
    else:
        async_res = process_evidence_job_task.delay(str(job.id))
        job.celery_task_id = getattr(async_res, "id", None)
        db.commit()
        db.refresh(job)
        return {
            "job_id": str(job.id),
            "evidence_id": str(ev.id),
            "case_id": str(case.id),
            "status": job.status,
            "celery_task_id": job.celery_task_id,
            "pipeline_version": job.pipeline_version,
        }


@router.post("/{case_id}/evidence/{evidence_id}/cancel")
def cancel_evidence_processing(
    case_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)
    job = (
        db.query(EvidenceProcessingJob)
        .filter(EvidenceProcessingJob.evidence_id == ev.id)
        .order_by(EvidenceProcessingJob.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="No processing job found")
    if job.status in ("COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel job in '{job.status}' state")

    job.status = "CANCELLED"
    job.stage = "CANCELLED"
    job.cancelled_at = datetime.now(timezone.utc)
    job.cancelled_by = current_user.id
    ev.processing_status = "CANCELLED"
    db.commit()

    create_audit_event(
        db=db,
        event_type="EVIDENCE_PIPELINE_CANCELLED",
        case_id=str(case.id),
        evidence_id=str(ev.id),
        actor_user_id=str(current_user.id),
        metadata={"job_id": str(job.id)},
    )
    return {"job_id": str(job.id), "status": "CANCELLED"}


@router.post("/{case_id}/evidence/{evidence_id}/retry")
def retry_evidence_processing(
    case_id: str,
    evidence_id: str,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return process_evidence_case(
        case_id=case_id,
        evidence_id=evidence_id,
        run_sync=run_sync,
        db=db,
        current_user=current_user,
    )


@router.get("/{case_id}/evidence/{evidence_id}/status")
def get_evidence_case_status(
    case_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    case, ev = require_evidence_access(case_id, evidence_id, current_user, db)

    job = (
        db.query(EvidenceProcessingJob)
        .filter(EvidenceProcessingJob.evidence_id == ev.id)
        .order_by(EvidenceProcessingJob.created_at.desc())
        .first()
    )

    return {
        "job_id": str(job.id) if job else None,
        "evidence_id": str(ev.id),
        "case_id": str(case.id),
        "status": job.status if job else getattr(ev, "processing_status", "UPLOADED"),
        "stage": getattr(job, "stage", "UPLOADED") if job else getattr(ev, "processing_status", "UPLOADED"),
        "retry_count": getattr(job, "retry_count", 0) if job else 0,
        "celery_task_id": getattr(job, "celery_task_id", None) if job else None,
        "records_processed": job.records_processed if job else 0,
        "started_at": job.started_at.isoformat() if job and job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job and job.completed_at else None,
        "error_message": job.error_message if job else None,
        "pipeline_version": job.pipeline_version if job else "2.0.0",
        "result_summary": job.result_summary if job else None,
    }


@direct_router.post("/{evidence_id}/process")
def process_evidence_direct(
    evidence_id: str,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        ev_uuid = uuid.UUID(str(evidence_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Evidence not found")
    ev = db.query(EvidenceItem).filter(EvidenceItem.id == ev_uuid).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return process_evidence_case(
        case_id=str(ev.case_id),
        evidence_id=str(ev.id),
        run_sync=run_sync,
        db=db,
        current_user=current_user,
    )


@direct_router.get("/{evidence_id}/status")
def get_evidence_direct_status(
    evidence_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        ev_uuid = uuid.UUID(str(evidence_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Evidence not found")
    ev = db.query(EvidenceItem).filter(EvidenceItem.id == ev_uuid).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return get_evidence_case_status(
        case_id=str(ev.case_id),
        evidence_id=str(ev.id),
        db=db,
        current_user=current_user,
    )


def _evidence_to_dict(ev: EvidenceItem) -> dict:
    return {
        "id": str(ev.id),
        "case_id": str(ev.case_id),
        "evidence_code": ev.evidence_code,
        "original_filename": ev.original_filename,
        "sanitized_filename": ev.sanitized_filename,
        "file_extension": ev.file_extension,
        "mime_type": ev.mime_type,
        "file_size_bytes": ev.file_size_bytes,
        "source_label": ev.source_label,
        "description": ev.description,
        "sha256_hash": ev.sha256_hash,
        "hash_algorithm": ev.hash_algorithm,
        "integrity_status": ev.integrity_status,
        "uploaded_by": str(ev.uploaded_by) if ev.uploaded_by else None,
        "uploaded_at": ev.uploaded_at.isoformat(),
        "parsing_status": ev.parsing_status,
        "processing_status": getattr(ev, "processing_status", "UPLOADED"),
        "parsing_error": ev.parsing_error,
        "is_original": ev.is_original,
        "version_number": getattr(ev, "version_number", 1),
        "supersedes_evidence_id": str(ev.supersedes_evidence_id) if getattr(ev, "supersedes_evidence_id", None) else None,
        "lifecycle_status": getattr(ev, "lifecycle_status", "ACTIVE"),
        "extracted_text_chars": len(ev.extracted_text or ""),
        "extracted_text_preview": (ev.extracted_text or "")[:EXTRACTED_TEXT_PREVIEW_CHARS] or None,
    }
