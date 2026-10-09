"""
API routes for the Bulk Certificate Generator.

Endpoints
---------
POST   /jobs                              – Create a new certificate generation job.
GET    /jobs/{job_id}                     – Get job status and summary counters.
GET    /jobs/{job_id}/certificates        – List all certificates for a job.
GET    /certificates/{certificate_id}     – Get a single certificate record.
GET    /certificates/{certificate_id}/download – Stream the generated PDF.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.job import Job, JobStatus
from app.models.certificate import Certificate, CertificateStatus
from app.schemas.job import (
    JobCreateRequest,
    JobSummaryResponse,
    JobDetailResponse,
    CertificateResponse,
)
import app.services.job_processor as _job_processor

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cert_to_response(cert: Certificate, request: Request) -> CertificateResponse:
    """Convert an ORM Certificate to a CertificateResponse with a download URL."""
    resp = CertificateResponse.model_validate(cert)
    if cert.status == CertificateStatus.SUCCESS and cert.file_path:
        resp.download_url = str(
            request.url_for("download_certificate", certificate_id=cert.id)
        )
    return resp


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/jobs",
    response_model=JobSummaryResponse,
    status_code=202,
    summary="Create a certificate generation job",
    description=(
        "Submit a list of recipients. The job is accepted immediately and "
        "certificates are generated in the background. Poll GET /jobs/{id} "
        "to track progress."
    ),
)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobSummaryResponse:
    # Create the Job row
    job = Job(
        event_name=payload.event_name,
        status=JobStatus.PENDING,
        total_count=len(payload.recipients),
    )
    db.add(job)
    db.flush()  # get job.id without committing yet

    # Create a Certificate row for every recipient (status=PENDING initially)
    for recipient in payload.recipients:
        cert = Certificate(
            job_id=job.id,
            recipient_name=recipient.name,
            recipient_email=str(recipient.email),
            course_name=recipient.course_name,
            completion_date=recipient.completion_date,
            status=CertificateStatus.PENDING,
        )
        db.add(cert)

    db.commit()
    db.refresh(job)

    # Kick off background processing – look up via module so monkeypatching works
    background_tasks.add_task(_job_processor.process_job, job.id)

    return JobSummaryResponse.model_validate(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobSummaryResponse,
    summary="Get job status",
)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobSummaryResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return JobSummaryResponse.model_validate(job)


@router.get(
    "/jobs/{job_id}/certificates",
    response_model=List[CertificateResponse],
    summary="List certificates for a job",
)
def list_certificates(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> List[CertificateResponse]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    certs = (
        db.query(Certificate)
        .filter(Certificate.job_id == job_id)
        .order_by(Certificate.created_at)
        .all()
    )
    return [_cert_to_response(c, request) for c in certs]


# ---------------------------------------------------------------------------
# Certificate endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/certificates/{certificate_id}",
    response_model=CertificateResponse,
    summary="Get a single certificate record",
)
def get_certificate(
    certificate_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> CertificateResponse:
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=404, detail=f"Certificate {certificate_id!r} not found"
        )
    return _cert_to_response(cert, request)


@router.get(
    "/certificates/{certificate_id}/download",
    summary="Download a generated certificate PDF",
    response_class=FileResponse,
    name="download_certificate",
)
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    cert = db.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=404, detail=f"Certificate {certificate_id!r} not found"
        )
    if cert.status != CertificateStatus.SUCCESS or not cert.file_path:
        raise HTTPException(
            status_code=409,
            detail="Certificate has not been successfully generated yet.",
        )
    if not Path(cert.file_path).exists():
        raise HTTPException(
            status_code=410,
            detail="Certificate file no longer exists on the server.",
        )

    safe_name = "".join(
        c if c.isalnum() or c in ("-", "_", " ") else "_"
        for c in cert.recipient_name
    )
    filename = f"certificate_{safe_name}.pdf"

    return FileResponse(
        path=cert.file_path,
        media_type="application/pdf",
        filename=filename,
    )
