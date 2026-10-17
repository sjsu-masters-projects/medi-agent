# Testing Guide

## Overview

This guide provides comprehensive information about testing practices, patterns, and requirements for the MediAgent backend.

## Code Coverage Requirements

### Minimum Coverage Threshold

- **Overall Coverage**: 80% minimum (`--cov-fail-under=80`, enforced in CI)
- **HTML report**: `./scripts/generate_html_coverage.sh` writes `backend/htmlcov/`

### Running Tests with Coverage

```bash
# Run all tests with coverage report
python -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

# Run specific test file with coverage
python -m pytest tests/unit/services/test_dailymed_service.py --cov=app.services.dailymed_service

# Run tests without coverage (faster for development)
python -m pytest tests/ --no-cov
```

### Coverage Configuration

Coverage settings are defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-v --tb=short --cov=app --cov-report=term-missing --cov-fail-under=80"

[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/site-packages/*",
]
```

## Test Structure

```
backend/tests/
├── unit/                    # Unit tests (isolated, mocked dependencies)
│   ├── adk/                 # Agent runtime, registry, tools and plugins
│   ├── services/            # Service layer tests
│   ├── safety/              # Deterministic triage floor and escalation
│   ├── workers/             # Cloud Run Job entry points
│   └── ...                  # agents, clients, core, db, followup, middleware, pharmacovigilance, scripts, tools, utils
├── integration/             # Integration tests (multiple components)
│   ├── routers/             # API endpoint tests
│   ├── test_*_postgres.py   # Opt-in real PostgreSQL contract suites
│   ├── test_middleware.py
│   └── test_mock_validation.py
└── fixtures/                # Synthetic documents, eval, Nora and PAT-005 fixtures
```

### Opt-in PostgreSQL suites

These run real migrations against disposable PostgreSQL 16 and skip unless enabled:

| Suite | Enable with |
|-------|-------------|
| `integration/test_care_conversation_postgres.py` | `CARE_CONVERSATION_TEST_POSTGRES_DOCKER=1` (official `postgres:16` image) |
| `integration/test_notification_centre_postgres.py` | `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1` (official `postgres:16` image) |
| `integration/test_adr_loop_postgres.py`, `integration/test_medwatch_3500_postgres.py`, `integration/test_clinic_memberships_postgres.py` | `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1` (same fixture) |
| `integration/test_public_grants_postgres.py` | `NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1` (same fixture) |
| `integration/test_email_postgres.py` | `EMAIL_TEST_POSTGRES_DOCKER=1` (same fixture) |
| `integration/test_care_plan_postgres.py` | `CARE_PLAN_TEST_POSTGRES=1` (local `initdb`/`pg_ctl`), plus `CARE_PLAN_TEST_POSTGRES_DOCKER=1` to use Docker instead |
| `integration/test_appointment_offer_transactions.py` | Runs when PostgreSQL server binaries are on `PATH`; skips otherwise |

Run them for any migration with functions or triggers; mocked RPC tests cannot see SQL bugs.

Every suite starts from hosted Supabase's default grants (`integration/supabase_roles.py`): new
`public` tables, sequences and functions are granted to `anon`, `authenticated` and `service_role`,
set in the connected database and in `template1` so per-test databases inherit them. A migration
must therefore enable RLS or revoke what it does not intend to expose;
`integration/test_public_grants_postgres.py` fails when a public table without RLS is open to a
browser role. Do not hand-grant table privileges to browser roles in a test. Unit and router tests
cannot reach a real model provider (autouse `no_real_model_calls` in `tests/conftest.py`), whatever
credentials the machine has.

## Testing Patterns

### 1. Unit Tests (Services)

Unit tests should mock all external dependencies (HTTP APIs, databases, etc.).

**Example: DailyMed Service Test**

```python
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.services.dailymed_service import search_drug

@pytest.mark.asyncio
async def test_search_drug_success():
    """Test successful drug search."""
    mock_response = {
        "metadata": {"total_elements": 25},
        "data": [
            {"drug_name": "Ibuprofen", "name_type": "G"},
        ],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None
        )

        result = await search_drug("ibuprofen")

        assert "error" not in result
        assert result["query"] == "ibuprofen"
        assert result["total_results"] == 25
```

**Key Points:**
- Use `unittest.mock.patch` to mock external HTTP calls
- Mock `httpx.AsyncClient.get` for HTTP requests
- Use `AsyncMock` for async functions
- Use `lambda` for simple return values (json, raise_for_status)
- Test both success and error cases

### 2. Integration Tests (API Endpoints)

Integration tests should use FastAPI's `TestClient` and mock only external services (not internal dependencies).

**Example: Patient API Test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user

client = TestClient(app)

def mock_current_user():
    return {"id": "test-user-id", "role": "patient"}

@pytest.fixture(autouse=True)
def override_dependencies():
    app.dependency_overrides[get_current_user] = mock_current_user
    yield
    app.dependency_overrides.clear()

def test_get_patient_profile():
    """Test getting patient profile."""
    response = client.get("/api/v1/patients/me")
    assert response.status_code == 200
    assert "id" in response.json()
```

**Key Points:**
- Use `app.dependency_overrides` for authentication mocking
- Use `autouse=True` fixture to apply overrides to all tests
- Clear overrides after tests with `yield`
- Test actual HTTP responses and status codes

### 3. Mock Validation Tests

Mock validation tests ensure that mocks match real implementations to prevent production failures.

**Example: Supabase Mock Validation**

```python
@pytest.mark.asyncio
async def test_supabase_select_query_structure():
    """Validate that mocked select queries match real Supabase client structure."""
    from app.clients.supabase import get_supabase_client
    
    client = get_supabase_client()
    
    # Verify client has expected methods
    assert hasattr(client, "table")
    
    # Verify query builder pattern
    query = client.table("patients")
    assert hasattr(query, "select")
    assert hasattr(query, "eq")
    assert hasattr(query, "execute")
```

**Key Points:**
- Validate mock structure matches real client
- Check method signatures and return types
- Ensure query patterns are correct
- Run these tests periodically to catch API changes

## Common Testing Patterns

### Mocking HTTP Errors

```python
@pytest.mark.asyncio
async def test_http_error():
    """Test HTTP error handling."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=500)
        
        def raise_for_status():
            raise httpx.HTTPStatusError(
                "Server error",
                request=AsyncMock(),
                response=mock_response
            )
        
        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response
        
        result = await my_function()
        
        assert "error" in result
```

### Mocking Timeouts

```python
@pytest.mark.asyncio
async def test_timeout():
    """Test timeout handling."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")
        
        result = await my_function()
        
        assert "error" in result
        assert result["error"] == "Request timed out"
```

### Testing Multiple API Calls

```python
@pytest.mark.asyncio
async def test_multiple_calls():
    """Test function that makes multiple API calls."""
    with patch("httpx.AsyncClient.get") as mock_get:
        # Return different responses for each call
        mock_get.side_effect = [
            AsyncMock(status_code=200, json=lambda: {"rxcui": "5640"}),
            AsyncMock(status_code=200, json=lambda: {"name": "Ibuprofen"}),
        ]
        
        result = await my_function()
        
        assert result["rxcui"] == "5640"
        assert result["name"] == "Ibuprofen"
```

## Best Practices

### 1. Test Naming

- Use descriptive test names that explain what is being tested
- Format: `test_<function>_<scenario>`
- Examples:
  - `test_search_drug_success`
  - `test_search_drug_not_found`
  - `test_search_drug_timeout`

### 2. Test Organization

- Group related tests in the same file
- Use test classes for complex scenarios
- Keep tests focused and independent

### 3. Assertions

- Use specific assertions (not just `assert result`)
- Test both positive and negative cases
- Verify error messages and status codes

### 4. Mocking

- Mock external dependencies (APIs, databases)
- Don't mock the code you're testing
- Validate mocks match real implementations

### 5. Coverage

- Aim for 80%+ coverage on all new code
- Focus on critical paths and error handling
- Don't write tests just to increase coverage

## Running Tests in CI/CD

`.github/workflows/ci.yml` runs the backend tests on every push and pull request in four
sharded jobs (`integration-routers`, `integration-workflows`, `unit-foundation`,
`unit-services`) without coverage, a full-suite coverage job that enforces the 80%
threshold, and a parallel `backend-postgres-contracts` job that runs the Docker PostgreSQL
suites in three shards (notifications and email, ADR loop and MedWatch, care conversations
and clinic memberships)
and fails if any expected case is skipped or missing. The containers are disposable and run
with `--network=none`; no CI job touches a hosted database. `test_care_plan_postgres.py` is
not run in CI.

## Pre-commit Hooks

Husky and lint-staged (root `package.json`) run on staged files at commit time: Ruff
check/format and mypy for `backend/src/**/*.py` (using `backend/.venv`), and ESLint for
portal TypeScript. They do not run the test suite. Install them with `npm ci` at the
repository root.

## Troubleshooting

### Tests Failing Locally But Passing in CI

- Check Python version (CI uses 3.12)
- Verify dependencies are up to date
- Check for environment-specific issues

### Coverage Below Threshold

- Run coverage report to see missing lines:
  ```bash
  python -m pytest tests/ --cov=app --cov-report=term-missing
  ```
- Add tests for uncovered code paths
- Focus on critical business logic first

### Slow Tests

- Use `--no-cov` flag during development
- Run specific test files instead of full suite
- Check for unnecessary API calls (should be mocked)

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [Mock validation tests](./integration/test_mock_validation.py)
