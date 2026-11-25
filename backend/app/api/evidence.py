from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.case import Case, CaseMember
from app.models.evidence import EvidenceItem, ParsingJob, ParsedRecord
from app.services.storage import get_storage
from app.services.hashing import calculate_sha256, verify_integrity
from app.services.audit_svc import create_audit_event
from app.services.graph_upsert import (
    upsert_phone_node, upsert_account_node, upsert_device_node,
    upsert_tower_node, upsert_document_node,
    create_called_edge, create_transferred_to_edge,
    create_used_device_edge, create_connected_to_tower_edge,
    _base_props,
)
from app.parsers.cdr import parse_cdr_csv
from app.parsers.transaction import parse_transaction_csv

from app.services.evidence_validator import validate_file_security, EvidenceValidationError
from app.services.evidence_orchestrator import get_orchestrator
from app.services.ocr import extract_text_for_upload
from app.models.evidence import EvidenceProcessingJob

router = APIRouter(prefix="/api/v1/cases", tags=["evidence"])
direct_router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json", ".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
EXTRACTED_TEXT_PREVIEW_CHARS = 500


def _sanitize_filename(filename: str) -> str:
    name = re.sub(r"[^\w\s\-\.]", "", filename)
    return name.strip().replace(" ", "_")


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


def _next_evidence_code(case_id: str, db: Session) -> str:
    count = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).count()
    return f"EVD-{str(count + 1).zfill(3)}"


@router.get("/{case_id}/evidence")
def list_evidence(case_id: str, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    _require_case_access(case_id, current_user, db)
    items = db.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).order_by(
        EvidenceItem.uploaded_at.desc()).all()
    return [_evidence_to_dict(e) for e in items]


@router.post("/{case_id}/evidence/upload", status_code=201)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    source_label: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)

    file_bytes = await file.read()
    
    # Rigorous file validation and path sanitization
    try:
        sanitized = validate_file_security(file.filename or "upload.csv", file_bytes, max_size=MAX_FILE_SIZE)
    except EvidenceValidationError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    import os
    ext = os.path.splitext(sanitized)[1].lower()

    # Best-effort text recovery for PDF / image evidence. A failure here must not
    # block the upload: the original bytes are still hashed and preserved.
    extracted_text = extract_text_for_upload(sanitized, file_bytes)

    # Compute hash BEFORE storing
    sha256 = calculate_sha256(file_bytes)

    # Duplicate detection within same case
    existing = db.query(EvidenceItem).filter(
        EvidenceItem.case_id == case_id, EvidenceItem.sha256_hash == sha256
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate file: SHA-256 matches existing evidence {existing.evidence_code}",
        )

    evidence_id = uuid.uuid4()
    object_key = f"cases/{case_id}/evidence/{evidence_id}/original/{sanitized}"

    # Upload to storage (MinIO or local filesystem)
    storage = get_storage()
    storage.upload(object_key, file_bytes, file.content_type or "application/octet-stream")

    # Persist evidence record
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        evidence_code=_next_evidence_code(case_id, db),
        original_filename=file.filename,
        sanitized_filename=sanitized,
        file_extension=ext,
        mime_type=file.content_type,
        file_size_bytes=len(file_bytes),
        object_storage_bucket=get_storage().bucket,
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
    )
    db.add(evidence)

    # Initial processing job tracking
    job = EvidenceProcessingJob(
        evidence_id=evidence_id,
        case_id=case_id,
        job_type="EVIDENCE_INGESTION",
        status="UPLOADED",
        pipeline_version="7A.1.0",
        initiated_by=current_user.id,
        records_processed=0,
    )
    db.add(job)

    db.commit()
    db.refresh(evidence)

    # Also upsert Document node in graph if service available
    try:
        upsert_document_node(
            case_id=case_id, evidence_id=str(evidence_id),
            evidence_code=evidence.evidence_code, filename=sanitized,
            sha256_hash=sha256, integrity_status="UNVERIFIED",
        )
    except Exception:
        pass

    create_audit_event(
        db=db, event_type="EVIDENCE_UPLOADED", case_id=case_id,
        evidence_id=str(evidence_id), actor_user_id=str(current_user.id),
        metadata={
            "filename": file.filename,
            "sha256": sha256,
            "size_bytes": len(file_bytes),
            "extracted_text_chars": len(extracted_text) if extracted_text else 0,
        },
    )

    return _evidence_to_dict(evidence)


@router.get("/{case_id}/evidence/{evidence_id}")
def get_evidence(case_id: str, evidence_id: str, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    _require_case_access(case_id, current_user, db)
    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    create_audit_event(db=db, event_type="EVIDENCE_VIEWED", case_id=case_id,
                       evidence_id=evidence_id, actor_user_id=str(current_user.id), metadata={})
    return _evidence_to_dict(ev)


@router.post("/{case_id}/evidence/{evidence_id}/verify-integrity")
def verify_evidence_integrity(case_id: str, evidence_id: str,
                               db: Session = Depends(get_db),
                               current_user=Depends(get_current_user)):
    _require_case_access(case_id, current_user, db)
    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    result = verify_integrity(ev, db, str(current_user.id))
    return result


@router.post("/{case_id}/evidence/{evidence_id}/parse")
def trigger_parse(
    case_id: str, evidence_id: str,
    column_mapping: Optional[dict] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_case_access(case_id, current_user, db)
    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if ev.file_extension not in (".csv", ".xlsx"):
        raise HTTPException(status_code=422, detail="Only CSV/XLSX files can be parsed")

    # Determine job type from source label or filename
    job_type = "CDR"
    fname_lower = (ev.original_filename or "").lower()
    if any(kw in fname_lower for kw in ["transaction", "txn", "upi", "bank", "financial"]):
        job_type = "TRANSACTION"

    job = ParsingJob(
        case_id=case_id, evidence_id=evidence_id,
        job_type=job_type, status="QUEUED", initiated_by=current_user.id,
    )
    db.add(job)
    ev.parsing_status = "PROCESSING"
    db.commit()
    db.refresh(job)

    create_audit_event(db=db, event_type="EVIDENCE_PARSING_STARTED", case_id=case_id,
                       evidence_id=evidence_id, actor_user_id=str(current_user.id),
                       metadata={"job_type": job_type, "job_id": str(job.id)})

    # Run in background
    background_tasks.add_task(
        _run_parse_job, str(job.id), ev, column_mapping or {}, db
    )
    return {"job_id": str(job.id), "status": "QUEUED", "job_type": job_type}


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

        # Download original from MinIO
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

        # Update job and evidence status
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
    """Persist CDR parsed records and upsert Neo4j graph."""
    case_id = str(ev.case_id)
    provenance_base = dict(
        evidence_id=str(ev.id), case_id=case_id,
        source_file_name=ev.original_filename, source_hash=ev.sha256_hash,
        verification_status=ev.integrity_status,
        relationship_status="DIRECT_RECORD", confidence_label="DIRECT_SOURCE_RECORD",
    )

    for rec in result["records"]:
        nr = rec["normalized_record"]
        # Persist to PostgreSQL
        db.add(ParsedRecord(
            case_id=case_id, evidence_id=str(ev.id), record_type="CDR",
            source_row_number=rec["source_row_number"],
            raw_record=rec["raw_record"], normalized_record=nr,
            parse_status="VALID",
        ))

        # Upsert Phone nodes
        upsert_phone_node(case_id, nr["calling_number"],
                          [nr.get("raw_record", {}).get("calling_number", nr["calling_number"])],
                          nr["start_time_utc"], nr["start_time_utc"])
        upsert_phone_node(case_id, nr["called_number"],
                          [nr.get("raw_record", {}).get("called_number", nr["called_number"])],
                          nr["start_time_utc"], nr["start_time_utc"])

        # CALLED relationship
        prov = {**provenance_base,
                "source_row_number": rec["source_row_number"],
                "event_timestamp_utc": nr["start_time_utc"],
                "raw_timestamp": nr.get("raw_start_time", "")}
        create_called_edge(case_id, nr["calling_number"], nr["called_number"],
                           prov, nr.get("duration_seconds"))

        # USED_DEVICE
        if nr.get("imei"):
            upsert_device_node(case_id, nr["imei"])
            create_used_device_edge(case_id, nr["calling_number"], nr["imei"], prov)

        # CONNECTED_TO_TOWER
        if nr.get("tower_id"):
            upsert_tower_node(case_id, nr["tower_id"])
            create_connected_to_tower_edge(case_id, nr["calling_number"], nr["tower_id"], prov)

    for err in result["errors"]:
        db.add(ParsedRecord(
            case_id=case_id, evidence_id=str(ev.id), record_type="CDR",
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
            case_id=case_id, evidence_id=str(ev.id), record_type="TRANSACTION",
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
            case_id=case_id, evidence_id=str(ev.id), record_type="TRANSACTION",
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
    _require_case_access(case_id, current_user, db)
    q = db.query(ParsedRecord).filter(
        ParsedRecord.case_id == case_id, ParsedRecord.evidence_id == evidence_id
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
    from app.models.audit import AuditEvent
    _require_case_access(case_id, current_user, db)
    events = db.query(AuditEvent).filter(
        AuditEvent.evidence_id == evidence_id
    ).order_by(AuditEvent.event_timestamp.desc()).all()
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "event_timestamp": e.event_timestamp.isoformat(),
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "event_metadata": e.event_metadata,
            "event_hash": e.event_hash,
        }
        for e in events
    ]


@router.post("/{case_id}/evidence/{evidence_id}/process")
def process_evidence_case(
    case_id: str,
    evidence_id: str,
    background_tasks: BackgroundTasks,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Phase 7A: Trigger automated pipeline ingestion for an uploaded evidence item.
    Performs validation, normalization, graph update, and cache refresh.
    """
    _require_case_access(case_id, current_user, db)
    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    orchestrator = get_orchestrator()
    job = orchestrator.create_processing_job(
        evidence_id=str(ev.id),
        case_id=case_id,
        user_id=str(current_user.id),
        db=db,
    )

    if run_sync:
        res = orchestrator.execute_pipeline(str(job.id), db=db)
        return {
            "job_id": str(job.id),
            "evidence_id": str(ev.id),
            "case_id": case_id,
            "status": res.get("status", "COMPLETED"),
            "records_processed": res.get("records_processed", 0),
            "pipeline_version": job.pipeline_version,
            "error_message": res.get("error"),
        }
    else:
        background_tasks.add_task(orchestrator.execute_pipeline, str(job.id))
        return {
            "job_id": str(job.id),
            "evidence_id": str(ev.id),
            "case_id": case_id,
            "status": "QUEUED",
            "pipeline_version": job.pipeline_version,
        }


@router.get("/{case_id}/evidence/{evidence_id}/status")
def get_evidence_case_status(
    case_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Phase 7A: Retrieve processing status and metadata for an evidence item.
    """
    _require_case_access(case_id, current_user, db)
    ev = db.query(EvidenceItem).filter(
        EvidenceItem.id == evidence_id, EvidenceItem.case_id == case_id
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")

    job = (
        db.query(EvidenceProcessingJob)
        .filter(EvidenceProcessingJob.evidence_id == evidence_id)
        .order_by(EvidenceProcessingJob.created_at.desc())
        .first()
    )

    return {
        "evidence_id": str(ev.id),
        "case_id": case_id,
        "status": job.status if job else getattr(ev, "processing_status", "UPLOADED"),
        "records_processed": job.records_processed if job else 0,
        "started_at": job.started_at.isoformat() if job and job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job and job.completed_at else None,
        "error_message": job.error_message if job else None,
        "pipeline_version": job.pipeline_version if job else "7A.1.0",
        "result_summary": job.result_summary if job else None,
    }


# Direct evidence endpoints for flexibility
@direct_router.post("/{evidence_id}/process")
def process_evidence_direct(
    evidence_id: str,
    background_tasks: BackgroundTasks,
    run_sync: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ev = db.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return process_evidence_case(
        case_id=str(ev.case_id),
        evidence_id=evidence_id,
        background_tasks=background_tasks,
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
    ev = db.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return get_evidence_case_status(
        case_id=str(ev.case_id),
        evidence_id=evidence_id,
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
        "extracted_text_chars": len(ev.extracted_text or ""),
        "extracted_text_preview": (ev.extracted_text or "")[:EXTRACTED_TEXT_PREVIEW_CHARS] or None,
    }
