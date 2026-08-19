"""
Pytest configuration and shared fixtures.

Fixtures defined here are available to ALL test files automatically.
"""

import os

# Tests must never inherit live observability or AI-service credentials from the
# repository-level .env file. Set these before importing app.main, which creates
# the application and initializes integrations at module import time.
os.environ["ENVIRONMENT"] = "test"
os.environ["BACKEND_SENTRY_DSN"] = ""
os.environ["DEEPGRAM_API_KEY"] = ""
os.environ["A2A_RETRY_WORKER_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)
