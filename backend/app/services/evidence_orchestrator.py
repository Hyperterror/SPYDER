"""
Canonical Evidence Processing Pipeline Orchestrator (Milestone 2).

Stages:
1. Job check & cancellation guard
2. Original evidence retrieval & SHA-256 verification
3. Security validation & modality/schema classification
4. Parsing & normalization (with parser version & extraction method provenance)
5. Idempotent database persistence (ParsedRecord upsert/replace by evidence_id)
6. Cross-entity resolution candidate check (non-self-comparing)
7. Atomic versioned Knowledge Graph publication (GraphSnapshot + Neo4j sync)
8. Intelligence caches refresh
9. Audit completion & safe failure preservation
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.intelligence.evidence_matcher import EvidenceMatcher
from app.intelligence.leads import LeadRepository
from app.intelligence.priority_engine import InvestigationPriorityEngine
from app.models.evidence import EvidenceItem, EvidenceProcessingJob, ParsedRecord
from app.parsers.unified import PARSER_VERSION, parse_unified_evidence_csv
from app.services.audit_svc import create_audit_event
from app.services.evidence_validator import (
    EvidenceValidationError,
    inspect_and_classify_schema,
    validate_file_security,
)
from app.services.er_live_service import evaluate_live_entity_resolution
from app.services.graph_publisher import publish_graph_snapshot
from app.services.hashing import calculate_sha256
from app.services.storage import get_storage

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graph_analysis.config import EVIDENCE_DIR, OUTPUT_DIR as GRAPH_OUTPUT_DIR

PIPELINE_VERSION = "2.0.0"


class EvidencePipelineOrchestrator:
    """
    Thread-safe orchestrator managing canonical idempotent evidence ingestion,
    versioned graph publication, and intelligence cache refreshes.
    """

    _instance: Optional["EvidencePipelineOrchestrator"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.orchestration_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "EvidencePipelineOrchestrator":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def create_processing_job(
        self,
        evidence_id: str,
        case_id: str,
        user_id: Optional[str],
        db: Session,
        job_type: str = "EVIDENCE_INGESTION",
    ) -> EvidenceProcessingJob:
        """Create an EvidenceProcessingJob record in QUEUED status."""
        ev_uuid = uuid.UUID(str(evidence_id))
        case_uuid = uuid.UUID(str(case_id))
        user_uuid = uuid.UUID(str(user_id)) if user_id else None

        ev = db.query(EvidenceItem).filter(EvidenceItem.id == ev_uuid).first()
        idem_key = f"{ev_uuid}:v{getattr(ev, 'version_number', 1)}:{PIPELINE_VERSION}" if ev else str(ev_uuid)

        job = EvidenceProcessingJob(
            id=uuid.uuid4(),
            evidence_id=ev_uuid,
            case_id=case_uuid,
            job_type=job_type,
            status="QUEUED",
            stage="QUEUED",
            pipeline_version=PIPELINE_VERSION,
            idempotency_key=idem_key,
            initiated_by=user_uuid,
            records_processed=0,
        )
        db.add(job)

        if ev:
            ev.processing_status = "QUEUED"
            ev.parsing_status = "PROCESSING"

        db.commit()
        db.refresh(job)

        create_audit_event(
            db=db,
            case_id=str(case_uuid),
            evidence_id=str(ev_uuid),
            actor_user_id=str(user_uuid) if user_uuid else None,
            event_type="EVIDENCE_PROCESSING_QUEUED",
            metadata={"job_id": str(job.id), "pipeline_version": PIPELINE_VERSION, "idempotency_key": idem_key},
        )
        return job

    def _is_cancelled(self, db: Session, job_id: uuid.UUID) -> bool:
        job = db.query(EvidenceProcessingJob).filter(EvidenceProcessingJob.id == job_id).first()
        return bool(job and job.status == "CANCELLED")

    def execute_pipeline(
        self,
        job_id: str,
        db: Optional[Session] = None,
        simulate_graph_failure: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute the canonical, idempotent evidence processing pipeline.
        Preserves original evidence and previously active GraphSnapshot on failure.
        """
        close_db_at_end = False
        if db is None:
            db = SessionLocal()
            close_db_at_end = True

        job_uuid = uuid.UUID(str(job_id))

        with self.orchestration_lock:
            try:
                job = db.query(EvidenceProcessingJob).filter(EvidenceProcessingJob.id == job_uuid).first()
                if not job:
                    return {"status": "FAILED", "error": "Job not found", "retryable": False}

                if job.status == "CANCELLED":
                    return {"job_id": str(job.id), "status": "CANCELLED", "retryable": False}

                evidence = db.query(EvidenceItem).filter(EvidenceItem.id == job.evidence_id).first()
                if not evidence:
                    job.status = "FAILED"
                    job.stage = "LOOKUP"
                    job.error_message = "Associated EvidenceItem not found"
                    db.commit()
                    return {"status": "FAILED", "error": job.error_message, "retryable": False}

                if getattr(evidence, "lifecycle_status", "ACTIVE") == "WITHDRAWN":
                    raise EvidenceValidationError("Cannot process withdrawn evidence.")

                # Stage 1: VALIDATING
                job.status = "VALIDATING"
                job.stage = "VALIDATING"
                job.started_at = job.started_at or datetime.now(timezone.utc)
                evidence.processing_status = "VALIDATING"
                db.commit()

                storage = get_storage()
                file_bytes = storage.download(evidence.object_storage_bucket, evidence.object_storage_key)

                # Verify cryptographic integrity of stored original bytes before parsing
                computed_sha = calculate_sha256(file_bytes)
                if computed_sha != evidence.sha256_hash:
                    evidence.integrity_status = "MISMATCH"
                    db.commit()
                    raise EvidenceValidationError("Stored evidence bytes failed SHA-256 integrity verification.")

                ext = evidence.file_extension or os.path.splitext(evidence.sanitized_filename or "")[1].lower()
                sanitized_name = validate_file_security(
                    evidence.original_filename or "upload.csv",
                    file_bytes,
                )
                modality, _ = inspect_and_classify_schema(file_bytes, file_extension=ext)

                if self._is_cancelled(db, job_uuid):
                    return {"job_id": str(job.id), "status": "CANCELLED", "retryable": False}

                # Stage 2: PROCESSING / PARSING
                job.status = "PROCESSING"
                job.stage = "PARSING"
                evidence.processing_status = "PROCESSING"
                db.commit()

                parse_result = parse_unified_evidence_csv(
                    file_bytes=file_bytes,
                    modality=modality,
                    case_id=str(evidence.case_id),
                    evidence_id=str(evidence.id),
                    source_file_name=sanitized_name,
                    sha256_hash=evidence.sha256_hash,
                    file_extension=ext,
                )

                if parse_result["valid_rows"] == 0 and parse_result["invalid_rows"] > 0:
                    first_err = (
                        parse_result["errors"][0]["parse_error"]
                        if parse_result["errors"]
                        else "Unknown parsing error"
                    )
                    raise EvidenceValidationError(
                        f"All {parse_result['invalid_rows']} rows failed parsing: {first_err}"
                    )

                # Stage 3: IDEMPOTENT DATABASE PERSISTENCE
                job.stage = "PERSISTING_RECORDS"
                db.commit()

                now_dt = datetime.now(timezone.utc)
                ev_version = getattr(evidence, "version_number", 1) or 1

                # Replace prior parsed records for this evidence item idempotently inside transaction
                db.query(ParsedRecord).filter(
                    ParsedRecord.evidence_id == evidence.id
                ).delete(synchronize_session=False)

                for rec in parse_result["records"]:
                    db.add(ParsedRecord(
                        id=uuid.uuid4(),
                        case_id=evidence.case_id,
                        evidence_id=evidence.id,
                        record_type=modality,
                        source_row_number=rec["source_row_number"],
                        raw_record=rec["raw_record"],
                        normalized_record=rec["normalized_record"],
                        parse_status="VALID",
                        evidence_version=ev_version,
                        extraction_method=rec.get("extraction_method"),
                        parser_version=rec.get("parser_version", PARSER_VERSION),
                        extracted_at=now_dt,
                        extraction_confidence="HIGH",
                    ))

                for err in parse_result["errors"]:
                    db.add(ParsedRecord(
                        id=uuid.uuid4(),
                        case_id=evidence.case_id,
                        evidence_id=evidence.id,
                        record_type=modality,
                        source_row_number=err["source_row_number"],
                        raw_record=err["raw_record"],
                        normalized_record={},
                        parse_status="INVALID",
                        parse_error=err["parse_error"],
                        evidence_version=ev_version,
                        extraction_method=err.get("extraction_method"),
                        parser_version=err.get("parser_version", PARSER_VERSION),
                        extracted_at=now_dt,
                        extraction_confidence="LOW",
                    ))
                db.commit()

                # Stage 4: ENTITY RESOLUTION CANDIDATE EVALUATION
                er_candidates_checked = 0
                if modality == "PERSONS":
                    job.stage = "ENTITY_RESOLUTION"
                    db.commit()
                    er_candidates_checked = self._evaluate_novel_persons(
                        parse_result["records"], str(evidence.case_id), db
                    )

                # Stage 5: ATOMIC VERSIONED GRAPH PUBLICATION
                job.stage = "PUBLISHING_GRAPH"
                db.commit()
                snapshot = publish_graph_snapshot(
                    db=db,
                    created_by=str(job.initiated_by) if job.initiated_by else None,
                    output_dir=GRAPH_OUTPUT_DIR,
                    include_baseline_dataset=True,
                    simulate_validation_failure=simulate_graph_failure,
                )

                # Stage 6: INTELLIGENCE CACHE REFRESH
                job.stage = "REFRESHING_INTELLIGENCE"
                db.commit()
                LeadRepository.get_instance().reload()
                InvestigationPriorityEngine.get_instance().reload()
                EvidenceMatcher.get_instance().reload()

                # Stage 7: COMPLETION
                final_status = "COMPLETED" if parse_result["invalid_rows"] == 0 else "PARTIALLY_COMPLETED"
                job.status = final_status
                job.stage = "DONE"
                job.records_processed = parse_result["valid_rows"]
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = None
                job.result_summary = {
                    "modality": modality,
                    "extraction_method": parse_result.get("extraction_method"),
                    "parser_version": parse_result.get("parser_version", PARSER_VERSION),
                    "total_rows": parse_result["total_rows"],
                    "valid_rows": parse_result["valid_rows"],
                    "invalid_rows": parse_result["invalid_rows"],
                    "graph_snapshot_version": snapshot.version_tag,
                    "graph_nodes": snapshot.node_count,
                    "graph_edges": snapshot.edge_count,
                    "er_candidates_evaluated": er_candidates_checked,
                }
                evidence.processing_status = final_status
                evidence.parsing_status = final_status
                evidence.parsing_error = None
                db.commit()

                create_audit_event(
                    db=db,
                    case_id=str(evidence.case_id),
                    evidence_id=str(evidence.id),
                    actor_user_id=str(job.initiated_by) if job.initiated_by else None,
                    event_type="EVIDENCE_PIPELINE_COMPLETED",
                    metadata=job.result_summary,
                )

                return {
                    "job_id": str(job.id),
                    "evidence_id": str(evidence.id),
                    "status": final_status,
                    "records_processed": parse_result["valid_rows"],
                    "modality": modality,
                    "graph_snapshot_version": snapshot.version_tag,
                    "pipeline_version": PIPELINE_VERSION,
                    "retryable": False,
                }

            except EvidenceValidationError as ve:
                self._mark_failed(db, job_uuid, str(ve))
                return {"job_id": str(job_uuid), "status": "FAILED", "error": str(ve), "retryable": False}
            except Exception as exc:
                self._mark_failed(db, job_uuid, str(exc))
                is_transient = isinstance(exc, (OSError, ConnectionError, TimeoutError))
                return {"job_id": str(job_uuid), "status": "FAILED", "error": str(exc), "retryable": is_transient}
            finally:
                if close_db_at_end:
                    db.close()

    def _mark_failed(self, db: Session, job_uuid: uuid.UUID, err_text: str) -> None:
        try:
            job = db.query(EvidenceProcessingJob).filter(EvidenceProcessingJob.id == job_uuid).first()
            ev = db.query(EvidenceItem).filter(EvidenceItem.id == job.evidence_id).first() if job else None
            err_msg = err_text.split("\n")[0][:500]
            if job:
                job.status = "FAILED"
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = err_msg
            if ev:
                ev.processing_status = "FAILED"
                ev.parsing_status = "FAILED"
                ev.parsing_error = err_msg
            db.commit()

            if ev and job:
                create_audit_event(
                    db=db,
                    case_id=str(ev.case_id),
                    evidence_id=str(ev.id),
                    actor_user_id=str(job.initiated_by) if job.initiated_by else None,
                    event_type="EVIDENCE_PIPELINE_FAILED",
                    metadata={"error": err_msg, "stage": job.stage},
                )
        except Exception:
            pass

    def _evaluate_novel_persons(
        self,
        records: List[Dict[str, Any]],
        case_id: str,
        db: Session,
    ) -> int:
        """
        Evaluate newly ingested PERSONS observations against distinct existing PERSONS
        observations across cases, persisting provisional IdentityHypothesis rows.
        """
        try:
            return evaluate_live_entity_resolution(db, case_id)
        except Exception as exc:
            logging.getLogger(__name__).warning("Live entity resolution evaluation failed for case %s: %s", case_id, exc)
            return 0


_orchestrator_instance: Optional[EvidencePipelineOrchestrator] = None


def get_orchestrator() -> EvidencePipelineOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = EvidencePipelineOrchestrator.get_instance()
    return _orchestrator_instance
