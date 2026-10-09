"""
Shared pytest fixtures for the test suite.

Architecture notes
------------------
BackgroundTasks in FastAPI run *after* the response is sent, in the same
thread pool. They open their own database session via SessionLocal, which
is separate from any per-request session. This makes it tricky to observe
background work in tests.

Our solution: patch ``process_job`` to run *synchronously* inside the
request using the same underlying engine as the test. We use a single
persistent SQLite file (``test_certificates.db``) and wipe + recreate
tables between tests so each test gets a clean slate.
"""

import os
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set the test DB URL *before* anything in app/ is imported
TEST_DATABASE_URL = "sqlite:///./test_certificates.db"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.database import Base, get_db   # noqa: E402 (must be after env set)
from app.main import create_app              # noqa: E402


# ---------------------------------------------------------------------------
# Engine – one engine for the whole session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    if os.path.exists("test_certificates.db"):
        os.remove("test_certificates.db")


# ---------------------------------------------------------------------------
# Per-test: wipe and recreate tables + provide a session
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(test_engine):
    """Drop and recreate all tables for a perfectly clean slate each test."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    TestingSession = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSession()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Per-test: FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session, test_engine, tmp_path, monkeypatch):
    """
    FastAPI TestClient wired to the test DB.

    Key trick: we monkeypatch ``process_job`` so that it runs *synchronously
    within the same request* and uses the *test engine* (not the app's
    default SessionLocal). This means:

    * The background task commits to the same DB file the test reads.
    * No polling / sleeping required – the job is finished by the time
      POST /jobs returns.
    """
    import app.core.config as cfg
    cfg.settings.CERTIFICATES_DIR = str(tmp_path / "certificates")

    # Patch SessionLocal inside job_processor to use the test engine
    from sqlalchemy.orm import sessionmaker as _sm
    import app.services.job_processor as _jp

    TestSession = _sm(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(_jp, "SessionLocal", TestSession)

    # NOTE: We do NOT wrap process_job here. FastAPI's TestClient runs
    # BackgroundTasks *synchronously* (before returning the response when
    # raise_server_exceptions=False is set and the ASGI lifespan is active),
    # so no extra threading tricks are needed. Patching SessionLocal is
    # sufficient to make background tasks use the test database.

    app_instance = create_app()

    def override_get_db():
        yield db_session

    app_instance.dependency_overrides[get_db] = override_get_db

    with TestClient(app_instance, raise_server_exceptions=False) as c:
        yield c
