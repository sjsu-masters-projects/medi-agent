# Testing Guide

## Overview

This guide provides comprehensive information about testing practices, patterns, and requirements for the MediAgent backend.

## Code Coverage Requirements

### Minimum Coverage Threshold

- **Overall Coverage**: 80% minimum (enforced in CI/CD)
- **Current Coverage**: 83.95%
- **Coverage Report**: Generated in `htmlcov/` directory after running tests

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
addopts = "-v --tb=short --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=80"

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
│   ├── services/           # Service layer tests
│   └── test_mcp_servers.py # MCP server tests
├── integration/            # Integration tests (multiple components)
│   ├── routers/           # API endpoint tests
│   ├── test_middleware.py # Middleware tests
│   └── test_mock_validation.py # Mock validation tests
└── MOCK_VALIDATION.md     # Mock validation documentation
```

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

Tests are automatically run in GitHub Actions on every push and pull request.

**CI Configuration** (`.github/workflows/backend-tests.yml`):

```yaml
- name: Run tests with coverage
  run: |
    cd backend
    python -m pytest tests/ --cov=app --cov-fail-under=80
```

## Pre-commit Hooks

Pre-commit hooks ensure tests pass before committing code.

**Setup:**

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

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
- [Mock Validation Guide](./MOCK_VALIDATION.md)
