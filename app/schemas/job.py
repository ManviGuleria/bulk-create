"""
Pydantic schemas for Jobs and Certificates.

Design notes
------------
* RecipientIn is the per-recipient input object. All four fields are required
  and individually validated (name non-empty, email format, date format, course
  non-empty).
* JobCreateRequest accepts 1-500 recipients per request so the payload stays
  manageable while still being genuinely "bulk".
* Response schemas are kept separate from ORM models (no direct orm_mode
  coupling at the schema layer) to make the API contract explicit.
"""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr

from app.models.job import JobStatus
from app.models.certificate import CertificateStatus

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9\s'\-\.]{2,255}$")


class RecipientIn(BaseModel):
    """A single recipient within a job creation request."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of the certificate recipient.",
        examples=["Alice Johnson"],
    )
    email: EmailStr = Field(
        ...,
        description="Email address of the recipient (used for identification).",
        examples=["alice@example.com"],
    )
    course_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Name of the course or event completed.",
        examples=["Introduction to Python"],
    )
    completion_date: str = Field(
        ...,
        description="Completion date in ISO-8601 format (YYYY-MM-DD).",
        examples=["2026-10-08"],
    )

    @field_validator("name")
    @classmethod
    def name_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        if not _NAME_RE.match(v):
            raise ValueError(
                "name may only contain letters, spaces, hyphens, apostrophes, and dots"
            )
        return v

    @field_validator("course_name")
    @classmethod
    def course_name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("course_name must not be blank")
        return v

    @field_validator("completion_date")
    @classmethod
    def completion_date_must_be_valid(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("completion_date must be a valid date in YYYY-MM-DD format")
        return v


class JobCreateRequest(BaseModel):
    """Request body for POST /jobs."""

    event_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Name of the event or programme for which certificates are issued.",
        examples=["Python Bootcamp 2026"],
    )
    recipients: List[RecipientIn] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of recipients (1–500).",
    )

    @field_validator("event_name")
    @classmethod
    def event_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("event_name must not be blank")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class JobSummaryResponse(BaseModel):
    """Lightweight job summary returned after creation and in status checks."""

    id: str
    event_name: str
    status: JobStatus
    total_count: int
    success_count: int
    failure_count: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_datetimes(cls, data):
        """Convert datetime objects to ISO strings for JSON serialisation."""
        if hasattr(data, "__dict__"):
            # ORM object – pull attributes directly
            return {
                "id": data.id,
                "event_name": data.event_name,
                "status": data.status,
                "total_count": data.total_count,
                "success_count": data.success_count,
                "failure_count": data.failure_count,
                "created_at": data.created_at.isoformat(),
                "updated_at": data.updated_at.isoformat(),
            }
        return data


class CertificateResponse(BaseModel):
    """Certificate detail returned in list and individual lookups."""

    id: str
    job_id: str
    recipient_name: str
    recipient_email: str
    course_name: str
    completion_date: str
    status: CertificateStatus
    error_message: Optional[str] = None
    download_url: Optional[str] = None  # populated by the route layer
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_datetimes(cls, data):
        if hasattr(data, "__dict__"):
            return {
                "id": data.id,
                "job_id": data.job_id,
                "recipient_name": data.recipient_name,
                "recipient_email": data.recipient_email,
                "course_name": data.course_name,
                "completion_date": data.completion_date,
                "status": data.status,
                "error_message": data.error_message,
                "download_url": None,  # set by route after construction
                "created_at": data.created_at.isoformat(),
                "updated_at": data.updated_at.isoformat(),
            }
        return data


class JobDetailResponse(JobSummaryResponse):
    """Full job response including embedded certificate list."""

    certificates: List[CertificateResponse] = []
