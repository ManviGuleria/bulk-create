"""
Tests for job creation, status tracking, and certificate retrieval.

Covers:
- Creating a generation job
- Input validation (missing/invalid fields)
- Certificate generation
- Job status / progress
- Handling an individual certificate failure
- Retrieving generated certificates

Note: Because conftest patches process_job to run synchronously, the job is
fully processed by the time POST /jobs returns. There is no need to poll.
"""

import pytest
from fastapi.testclient import TestClient


BASE = "/api/v1"

VALID_RECIPIENT = {
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "course_name": "Introduction to Python",
    "completion_date": "2026-10-08",
}

VALID_PAYLOAD = {
    "event_name": "Python Bootcamp 2026",
    "recipients": [VALID_RECIPIENT],
}


def create_job(client: TestClient, payload=None) -> dict:
    payload = payload or VALID_PAYLOAD
    resp = client.post(f"{BASE}/jobs", json=payload)
    assert resp.status_code == 202, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Creating a generation job
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_create_job_returns_202(self, client):
        resp = client.post(f"{BASE}/jobs", json=VALID_PAYLOAD)
        assert resp.status_code == 202

    def test_create_job_response_structure(self, client):
        data = create_job(client)
        assert "id" in data
        assert data["event_name"] == "Python Bootcamp 2026"
        assert data["total_count"] == 1
        assert data["status"] in ("pending", "processing", "completed")

    def test_create_job_multiple_recipients(self, client):
        payload = {
            "event_name": "Bulk Test Event",
            "recipients": [
                {
                    "name": f"Recipient {i}",
                    "email": f"user{i}@example.com",
                    "course_name": "Data Science 101",
                    "completion_date": "2026-09-01",
                }
                for i in range(5)
            ],
        }
        data = create_job(client, payload)
        assert data["total_count"] == 5

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# 2. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_event_name(self, client):
        payload = {"recipients": [VALID_RECIPIENT]}
        resp = client.post(f"{BASE}/jobs", json=payload)
        assert resp.status_code == 422

    def test_empty_recipients_list(self, client):
        payload = {"event_name": "Test", "recipients": []}
        resp = client.post(f"{BASE}/jobs", json=payload)
        assert resp.status_code == 422

    def test_invalid_email(self, client):
        bad = {**VALID_RECIPIENT, "email": "not-an-email"}
        resp = client.post(f"{BASE}/jobs", json={"event_name": "Test", "recipients": [bad]})
        assert resp.status_code == 422

    def test_blank_name(self, client):
        bad = {**VALID_RECIPIENT, "name": "  "}
        resp = client.post(f"{BASE}/jobs", json={"event_name": "Test", "recipients": [bad]})
        assert resp.status_code == 422

    def test_invalid_date_format(self, client):
        bad = {**VALID_RECIPIENT, "completion_date": "08-10-2026"}  # wrong format
        resp = client.post(f"{BASE}/jobs", json={"event_name": "Test", "recipients": [bad]})
        assert resp.status_code == 422

    def test_invalid_date_value(self, client):
        bad = {**VALID_RECIPIENT, "completion_date": "2026-13-01"}  # month 13
        resp = client.post(f"{BASE}/jobs", json={"event_name": "Test", "recipients": [bad]})
        assert resp.status_code == 422

    def test_blank_course_name(self, client):
        bad = {**VALID_RECIPIENT, "course_name": "   "}
        resp = client.post(f"{BASE}/jobs", json={"event_name": "Test", "recipients": [bad]})
        assert resp.status_code == 422

    def test_name_with_special_chars(self, client):
        """Names with hyphens and apostrophes should be accepted."""
        good = {**VALID_RECIPIENT, "name": "Mary-Jane O'Brien"}
        resp = client.post(
            f"{BASE}/jobs", json={"event_name": "Test", "recipients": [good]}
        )
        assert resp.status_code == 202

    def test_too_many_recipients(self, client):
        """501 recipients exceeds the 500 limit."""
        payload = {
            "event_name": "Overload Test",
            "recipients": [
                {
                    "name": f"Person {i}",
                    "email": f"p{i}@example.com",
                    "course_name": "Course",
                    "completion_date": "2026-01-01",
                }
                for i in range(501)
            ],
        }
        resp = client.post(f"{BASE}/jobs", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Certificate generation
# ---------------------------------------------------------------------------


class TestCertificateGeneration:
    def test_certificate_generated_successfully(self, client):
        data = create_job(client)
        job_id = data["id"]

        resp = client.get(f"{BASE}/jobs/{job_id}")
        job = resp.json()
        assert job["status"] == "completed"
        assert job["success_count"] == 1
        assert job["failure_count"] == 0

    def test_certificates_list_populated(self, client):
        data = create_job(client)
        job_id = data["id"]

        resp = client.get(f"{BASE}/jobs/{job_id}/certificates")
        assert resp.status_code == 200
        certs = resp.json()
        assert len(certs) == 1
        assert certs[0]["recipient_name"] == "Alice Johnson"
        assert certs[0]["status"] == "success"

    def test_successful_certificate_has_download_url(self, client):
        data = create_job(client)
        job_id = data["id"]

        certs = client.get(f"{BASE}/jobs/{job_id}/certificates").json()
        assert certs[0]["download_url"] is not None
        assert "download" in certs[0]["download_url"]

    def test_bulk_generation_all_succeed(self, client):
        payload = {
            "event_name": "Bulk Success Test",
            "recipients": [
                {
                    "name": f"Student {i}",
                    "email": f"student{i}@example.com",
                    "course_name": "Advanced Python",
                    "completion_date": "2026-08-15",
                }
                for i in range(10)
            ],
        }
        data = create_job(client, payload)
        job_id = data["id"]

        job = client.get(f"{BASE}/jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["success_count"] == 10
        assert job["failure_count"] == 0


# ---------------------------------------------------------------------------
# 4. Job status / progress
# ---------------------------------------------------------------------------


class TestJobStatus:
    def test_get_job_not_found(self, client):
        resp = client.get(f"{BASE}/jobs/nonexistent-id")
        assert resp.status_code == 404

    def test_job_status_is_completed_after_processing(self, client):
        data = create_job(client)
        job = client.get(f"{BASE}/jobs/{data['id']}").json()
        assert job["status"] == "completed"

    def test_job_counters_match_recipients(self, client):
        payload = {
            "event_name": "Counters Test",
            "recipients": [
                {
                    "name": f"Student {i}",
                    "email": f"s{i}@example.com",
                    "course_name": "Math",
                    "completion_date": "2026-06-15",
                }
                for i in range(3)
            ],
        }
        data = create_job(client, payload)
        job = client.get(f"{BASE}/jobs/{data['id']}").json()
        assert job["total_count"] == 3
        assert job["success_count"] + job["failure_count"] == 3

    def test_job_has_timestamps(self, client):
        data = create_job(client)
        assert "created_at" in data
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# 5. Handling an individual certificate failure
# ---------------------------------------------------------------------------


class TestCertificateFailure:
    def test_partial_failure_job_still_completes(self, client, monkeypatch):
        """
        One recipient whose name triggers a simulated failure should result in:
        - Job status = 'completed' (not 'failed', because some succeeded)
        - success_count = 1, failure_count = 1
        - The failed certificate has status='failed'
        - The successful certificate has status='success'
        """
        from app.services import certificate_generator

        original = certificate_generator.generate_certificate_pdf

        def patched(**kwargs):
            if kwargs.get("recipient_name") == "Bad Recipient":
                raise RuntimeError("Simulated generation failure")
            return original(**kwargs)

        monkeypatch.setattr(certificate_generator, "generate_certificate_pdf", patched)

        payload = {
            "event_name": "Partial Failure Test",
            "recipients": [
                {
                    "name": "Good Recipient",
                    "email": "good@example.com",
                    "course_name": "Chemistry",
                    "completion_date": "2026-05-20",
                },
                {
                    "name": "Bad Recipient",
                    "email": "bad@example.com",
                    "course_name": "Chemistry",
                    "completion_date": "2026-05-20",
                },
            ],
        }

        data = create_job(client, payload)
        job = client.get(f"{BASE}/jobs/{data['id']}").json()

        assert job["status"] == "completed"
        assert job["success_count"] == 1
        assert job["failure_count"] == 1

        certs = client.get(f"{BASE}/jobs/{data['id']}/certificates").json()
        statuses = {c["recipient_name"]: c["status"] for c in certs}
        assert statuses["Good Recipient"] == "success"
        assert statuses["Bad Recipient"] == "failed"

    def test_failed_certificate_has_no_download_url(self, client, monkeypatch):
        from app.services import certificate_generator

        monkeypatch.setattr(
            certificate_generator,
            "generate_certificate_pdf",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("always fails")),
        )

        payload = {
            "event_name": "Fail Download Test",
            "recipients": [
                {
                    "name": "Fail Person",
                    "email": "fail@example.com",
                    "course_name": "Biology",
                    "completion_date": "2026-03-01",
                }
            ],
        }
        data = create_job(client, payload)
        certs = client.get(f"{BASE}/jobs/{data['id']}/certificates").json()
        assert certs[0]["status"] == "failed"
        assert certs[0]["download_url"] is None

    def test_all_failures_marks_job_failed(self, client, monkeypatch):
        """If every certificate fails, the job status should be 'failed'."""
        from app.services import certificate_generator

        monkeypatch.setattr(
            certificate_generator,
            "generate_certificate_pdf",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Always fails")),
        )

        payload = {
            "event_name": "All Fail Test",
            "recipients": [
                {
                    "name": "Fail One",
                    "email": "f1@example.com",
                    "course_name": "Maths",
                    "completion_date": "2026-01-01",
                }
            ],
        }
        data = create_job(client, payload)
        job = client.get(f"{BASE}/jobs/{data['id']}").json()
        assert job["status"] == "failed"
        assert job["failure_count"] == 1


# ---------------------------------------------------------------------------
# 6. Retrieving generated certificates
# ---------------------------------------------------------------------------


class TestCertificateRetrieval:
    def test_get_individual_certificate(self, client):
        data = create_job(client)
        job_id = data["id"]

        certs = client.get(f"{BASE}/jobs/{job_id}/certificates").json()
        cert_id = certs[0]["id"]

        resp = client.get(f"{BASE}/certificates/{cert_id}")
        assert resp.status_code == 200
        cert_data = resp.json()
        assert cert_data["id"] == cert_id
        assert cert_data["recipient_name"] == "Alice Johnson"

    def test_download_certificate_pdf(self, client):
        data = create_job(client)
        job_id = data["id"]

        certs = client.get(f"{BASE}/jobs/{job_id}/certificates").json()
        cert_id = certs[0]["id"]

        resp = client.get(f"{BASE}/certificates/{cert_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        # A valid PDF starts with %PDF
        assert resp.content[:4] == b"%PDF"

    def test_download_pending_certificate_returns_409(self, client, monkeypatch):
        """
        A certificate that has not yet been generated returns 409.
        We simulate this by patching process_job to do nothing.
        """
        import app.services.job_processor as _jp

        monkeypatch.setattr(_jp, "process_job", lambda job_id: None)

        resp = client.post(f"{BASE}/jobs", json=VALID_PAYLOAD)
        assert resp.status_code == 202
        job_id = resp.json()["id"]

        certs = client.get(f"{BASE}/jobs/{job_id}/certificates").json()
        cert_id = certs[0]["id"]

        dl_resp = client.get(f"{BASE}/certificates/{cert_id}/download")
        assert dl_resp.status_code == 409

    def test_get_certificate_not_found(self, client):
        resp = client.get(f"{BASE}/certificates/does-not-exist")
        assert resp.status_code == 404

    def test_certificates_list_not_found_job(self, client):
        resp = client.get(f"{BASE}/jobs/no-such-job/certificates")
        assert resp.status_code == 404

    def test_certificate_response_contains_expected_fields(self, client):
        data = create_job(client)
        certs = client.get(f"{BASE}/jobs/{data['id']}/certificates").json()
        cert = certs[0]
        expected_fields = {
            "id", "job_id", "recipient_name", "recipient_email",
            "course_name", "completion_date", "status", "download_url",
            "created_at", "updated_at",
        }
        assert expected_fields.issubset(cert.keys())
