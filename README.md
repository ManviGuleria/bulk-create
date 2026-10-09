# Bulk Certificate Generator

A FastAPI backend that accepts bulk certificate generation requests, generates PDF certificates from a predefined template, and lets clients track progress and download results.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Setup](#setup)
3. [Running the Application](#running-the-application)
4. [Running Tests](#running-tests)
5. [API Usage](#api-usage)
6. [Design Decisions](#design-decisions)

---

## Project Structure

```
assignment_bulk_creator/
├── app/
│   ├── api/
│   │   └── routes.py          # All API endpoints
│   ├── core/
│   │   ├── config.py          # Settings (env-based)
│   │   └── database.py        # SQLAlchemy engine + session factory
│   ├── models/
│   │   ├── job.py             # Job ORM model
│   │   └── certificate.py     # Certificate ORM model
│   ├── schemas/
│   │   └── job.py             # Pydantic request/response schemas
│   ├── services/
│   │   ├── certificate_generator.py  # ReportLab PDF generation
│   │   └── job_processor.py          # Background processing logic
│   └── main.py                # FastAPI app factory
├── certificates/              # Generated PDFs (auto-created)
├── tests/
│   ├── conftest.py            # Pytest fixtures
│   └── test_jobs.py           # Full test suite
├── requirements.txt
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.9+
- `pip`

### Install dependencies

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install requirements
pip install -r requirements.txt
```

### Environment variables (optional)

The app works with defaults. To override, create a `.env` file in the project root:

```env
DATABASE_URL=sqlite:///./certificates.db
CERTIFICATES_DIR=./certificates
CERTIFICATE_ISSUER=My Organisation
CERTIFICATE_TITLE=Certificate of Completion
DEBUG=false
```

---

## Running the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs are available at:

- Swagger UI → http://localhost:8000/docs
- ReDoc      → http://localhost:8000/redoc

---

## Running Tests

```bash
python -m pytest tests/ -v
```

The test suite uses a file-based SQLite database (`test_certificates.db`) that is created and torn down automatically.

---

## API Usage

### Base URL

```
http://localhost:8000/api/v1
```

---

### 1. Create a Certificate Generation Job

**`POST /api/v1/jobs`**

Submit a list of recipients. The job is accepted immediately (HTTP 202) and certificates are generated in the background.

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Bootcamp 2026",
    "recipients": [
      {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "course_name": "Introduction to Python",
        "completion_date": "2026-10-08"
      },
      {
        "name": "Bob Smith",
        "email": "bob@example.com",
        "course_name": "Introduction to Python",
        "completion_date": "2026-10-08"
      }
    ]
  }'
```

**Response (202 Accepted):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "event_name": "Python Bootcamp 2026",
  "status": "pending",
  "total_count": 2,
  "success_count": 0,
  "failure_count": 0,
  "created_at": "2026-10-08T10:00:00+00:00",
  "updated_at": "2026-10-08T10:00:00+00:00"
}
```

---

### 2. Check Job Status

**`GET /api/v1/jobs/{job_id}`**

```bash
curl http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

**Response:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "event_name": "Python Bootcamp 2026",
  "status": "completed",
  "total_count": 2,
  "success_count": 2,
  "failure_count": 0,
  "created_at": "2026-10-08T10:00:00+00:00",
  "updated_at": "2026-10-08T10:00:05+00:00"
}
```

**Job status values:**

| Status       | Meaning                                         |
|--------------|-------------------------------------------------|
| `pending`    | Accepted, not yet started                       |
| `processing` | Generation in progress                          |
| `completed`  | All certificates processed (may include failures) |
| `failed`     | Every single certificate failed                 |

---

### 3. List Certificates for a Job

**`GET /api/v1/jobs/{job_id}/certificates`**

```bash
curl http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/certificates
```

Returns an array of certificate objects. Successful ones include a `download_url`.

---

### 4. Get a Single Certificate

**`GET /api/v1/certificates/{certificate_id}`**

```bash
curl http://localhost:8000/api/v1/certificates/abc123
```

---

### 5. Download a Certificate PDF

**`GET /api/v1/certificates/{certificate_id}/download`**

```bash
curl -OJ http://localhost:8000/api/v1/certificates/abc123/download
```

Returns the PDF file with `Content-Type: application/pdf`.

---

### Validation Rules

| Field             | Rules                                                  |
|-------------------|--------------------------------------------------------|
| `event_name`      | 2–255 characters, non-blank                           |
| `recipients`      | 1–500 items                                           |
| `name`            | 2–255 chars; letters, spaces, hyphens, apostrophes    |
| `email`           | Valid email address format                            |
| `course_name`     | 2–255 characters, non-blank                           |
| `completion_date` | ISO-8601 format: `YYYY-MM-DD`                         |

---

## Design Decisions

### Framework – FastAPI

FastAPI provides automatic request validation via Pydantic, auto-generated OpenAPI docs, and async-friendly design. DRF/Django would introduce unnecessary boilerplate for a pure API service.

### Database – SQLite + SQLAlchemy

SQLite requires zero infrastructure setup (no server process, no credentials) while being a proper relational database. The SQLAlchemy ORM layer makes swapping to PostgreSQL trivial — just change `DATABASE_URL`.

### Background Processing – FastAPI `BackgroundTasks`

**Why not Celery?** Celery requires a broker (Redis or RabbitMQ), a separate worker process, and significant configuration overhead. For this service, FastAPI's built-in `BackgroundTasks` is sufficient because:

- PDF generation is CPU/I/O-bound but fast (~50ms per certificate).
- The processor runs on a separate thread, so the HTTP response is returned immediately.
- The full system starts with a single `uvicorn` command.

**Trade-off acknowledged:** For horizontal scaling across multiple server instances, or for very large batches (10,000+ recipients), a proper queue (Celery, ARQ) would be the right choice. The `process_job` function is intentionally decoupled from `BackgroundTasks` so it can be wired into any task runner without modification.

### Certificate Format – PDF via ReportLab

ReportLab is the industry-standard Python PDF library. It gives pixel-level layout control without requiring a headless browser (Puppeteer/WeasyPrint). The template is defined entirely in Python code, making it self-contained and easy to modify.

### Failure Isolation

Each certificate is generated and committed independently. An exception on one certificate is caught, logged, and recorded against that certificate row with an `error_message`. The loop continues for all remaining recipients. The job is only marked `failed` if **every** certificate fails; otherwise it is `completed` (which can include partial failures — the counters tell the full story).

### API Design

- `POST /jobs` returns HTTP **202 Accepted** (not 201) because work is not complete at response time.
- Job and certificate IDs are UUIDs to prevent enumeration.
- The `download_url` is injected into certificate responses dynamically so clients don't need to construct URLs.
- A `/health` endpoint is included for infrastructure probes.
