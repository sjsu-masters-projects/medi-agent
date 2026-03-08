"""
Pytest configuration and shared fixtures.

Fixtures defined here are available to ALL test files automatically.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)
