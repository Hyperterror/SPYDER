"""
Durable Celery Tasks for Evidence Processing Pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models.evidence import EvidenceItem, EvidenceProcessingJob
from app.services.audit_svc import create_audit_event
from app.worker.celery_app import CELERY_AVAILABLE, celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="spyder.process_evidence_job",
    max_retries=3,
    default_retry_delay=15,
)
def process_evidence_job_task(self, job_id: str) -> dict:
    """
    Execute the canonical evidence processing pipeline in a durable worker
    with bounded retries and safe failure preservation.
    """
    from app.services.evidence_orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    result = orchestrator.execute_pipeline(job_id)

    # Retry only on transient infrastructure/storage errors (never on validation/cancellation)
    if result.get("retryable") and self is not None and CELERY_AVAILABLE:
        db = SessionLocal()
        try:
            job = db.query(EvidenceProcessingJob).filter(EvidenceProcessingJob.id == job_id).first()
            if job and job.retry_count < job.max_retries and job.status != "CANCELLED":
                job.retry_count += 1
                job.status = "RETRYING"
                job.stage = "RETRYING"
                db.commit()
                create_audit_event(
                    db=db,
                    case_id=str(job.case_id),
                    evidence_id=str(job.evidence_id),
                    event_type="EVIDENCE_PIPELINE_RETRYING",
                    metadata={"job_id": str(job.id), "retry_count": job.retry_count},
                )
                countdown = min(60, 5 * (2 ** (job.retry_count - 1)))
                raise self.retry(exc=RuntimeError(result.get("error", "Transient failure")), countdown=countdown)
        finally:
            db.close()

    return result
