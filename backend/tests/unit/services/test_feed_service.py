"""Tests for Feed service."""

from datetime import date
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.services.feed_service import FeedService


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    client = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def feed_service(mock_supabase_client):
    """Create FeedService instance with mocked client."""
    return FeedService(db=mock_supabase_client)


# ── Helper Data Fixtures ──────────────────────────────────────


@pytest.fixture
def sample_medication():
    """Sample medication data."""
    return {
        "id": str(uuid4()),
        "name": "Ibuprofen",
        "dosage": "200mg",
        "frequency": "twice daily",
        "instructions": "Take with food",
        "care_teams": {
            "id": str(uuid4()),
            "clinicians": {
                "id": str(uuid4()),
                "first_name": "Jane",
                "last_name": "Smith",
                "specialty": "Primary Care",
                "clinic_name": "Health Clinic",
            },
        },
    }


@pytest.fixture
def sample_obligation():
    """Sample obligation data."""
    return {
        "id": str(uuid4()),
        "description": "Morning walk",
        "frequency": "daily",
        "care_teams": {
            "id": str(uuid4()),
            "clinicians": {
                "id": str(uuid4()),
                "first_name": "John",
                "last_name": "Doe",
                "specialty": "Cardiology",
                "clinic_name": "Heart Center",
            },
        },
    }


@pytest.fixture
def sample_adherence_log():
    """Sample adherence log data."""
    return {
        "target_id": str(uuid4()),
        "target_type": "medication",
        "status": "completed",
        "logged_at": "2024-01-15T08:15:00Z",
        "scheduled_time": "08:00:00",
    }


# ── _build_adherence_map Tests ────────────────────────────────


def test_build_adherence_map_empty_logs(feed_service):
    """Test building adherence map with empty logs."""
    result = feed_service._build_adherence_map([])
    assert result == {}


def test_build_adherence_map_single_log(feed_service, sample_adherence_log):
    """Test building adherence map with single log."""
    result = feed_service._build_adherence_map([sample_adherence_log])

    key = (sample_adherence_log["target_type"], sample_adherence_log["target_id"])
    assert key in result
    assert result[key] == sample_adherence_log


def test_build_adherence_map_multiple_logs_same_target(feed_service):
    """Test building adherence map keeps most recent log for same target."""
    target_id = str(uuid4())
    older_log = {
        "target_id": target_id,
        "target_type": "medication",
        "status": "pending",
        "logged_at": "2024-01-15T08:00:00Z",
        "scheduled_time": "08:00:00",
    }
    newer_log = {
        "target_id": target_id,
        "target_type": "medication",
        "status": "completed",
        "logged_at": "2024-01-15T08:15:00Z",
        "scheduled_time": "08:00:00",
    }

    result = feed_service._build_adherence_map([older_log, newer_log])

    key = ("medication", target_id)
    assert result[key] == newer_log


def test_build_adherence_map_different_target_types(feed_service):
    """Test building adherence map with different target types."""
    med_id = str(uuid4())
    obl_id = str(uuid4())

    med_log = {
        "target_id": med_id,
        "target_type": "medication",
        "status": "completed",
        "logged_at": "2024-01-15T08:15:00Z",
        "scheduled_time": "08:00:00",
    }
    obl_log = {
        "target_id": obl_id,
        "target_type": "obligation",
        "status": "pending",
        "logged_at": "2024-01-15T07:00:00Z",
        "scheduled_time": "07:00:00",
    }

    result = feed_service._build_adherence_map([med_log, obl_log])

    assert ("medication", med_id) in result
    assert ("obligation", obl_id) in result
    assert len(result) == 2


# ── _determine_status Tests ───────────────────────────────────


def test_determine_status_no_adherence(feed_service):
    """Test status determination with no adherence log."""
    result = feed_service._determine_status(None)
    assert result == "pending"


def test_determine_status_completed(feed_service):
    """Test status determination with completed status."""
    adherence = {"status": "completed"}
    result = feed_service._determine_status(adherence)
    assert result == "completed"


def test_determine_status_taken(feed_service):
    """Test status determination with taken status."""
    adherence = {"status": "taken"}
    result = feed_service._determine_status(adherence)
    assert result == "completed"


def test_determine_status_skipped(feed_service):
    """Test status determination with skipped status."""
    adherence = {"status": "skipped"}
    result = feed_service._determine_status(adherence)
    assert result == "skipped"


def test_determine_status_other(feed_service):
    """Test status determination with other status."""
    adherence = {"status": "unknown"}
    result = feed_service._determine_status(adherence)
    assert result == "pending"


# ── _extract_provider Tests ───────────────────────────────────


def test_extract_provider_none(feed_service):
    """Test provider extraction with None care_teams."""
    result = feed_service._extract_provider(None)
    assert result is None


def test_extract_provider_no_clinician(feed_service):
    """Test provider extraction with care_teams but no clinician."""
    care_teams = {"id": str(uuid4())}
    result = feed_service._extract_provider(care_teams)
    assert result is None


def test_extract_provider_complete_data(feed_service):
    """Test provider extraction with complete data."""
    clinician_id = str(uuid4())
    care_teams = {
        "id": str(uuid4()),
        "clinicians": {
            "id": clinician_id,
            "first_name": "Jane",
            "last_name": "Smith",
            "specialty": "Primary Care",
            "clinic_name": "Health Clinic",
        },
    }

    result = feed_service._extract_provider(care_teams)

    assert result is not None
    assert result["id"] == clinician_id
    assert result["name"] == "Dr. Jane Smith"
    assert result["specialty"] == "Primary Care"
    assert result["clinic_name"] == "Health Clinic"


# ── _medications_to_tasks Tests ───────────────────────────────


def test_medications_to_tasks_no_adherence(feed_service, sample_medication):
    """Test medication transformation with no adherence."""
    result = feed_service._medications_to_tasks([sample_medication], {})

    assert len(result) == 1
    task = result[0]
    assert task["type"] == "medication"
    assert task["target_id"] == sample_medication["id"]
    assert task["name"] == "Ibuprofen 200mg"
    assert task["description"] == "Take with food"
    assert task["frequency"] == "twice daily"
    assert task["status"] == "pending"
    assert task["completed_at"] is None
    assert task["scheduled_time"] is None
    assert task["provider"] is not None
    assert task["provider"]["name"] == "Dr. Jane Smith"


def test_medications_to_tasks_with_completed_adherence(feed_service, sample_medication):
    """Test medication transformation with completed adherence."""
    adherence_log = {
        "target_id": sample_medication["id"],
        "target_type": "medication",
        "status": "completed",
        "logged_at": "2024-01-15T08:15:00Z",
        "scheduled_time": "08:00:00",
    }
    adherence_map = {("medication", sample_medication["id"]): adherence_log}

    result = feed_service._medications_to_tasks([sample_medication], adherence_map)

    assert len(result) == 1
    task = result[0]
    assert task["status"] == "completed"
    assert task["completed_at"] == "2024-01-15T08:15:00Z"
    assert task["scheduled_time"] == "08:00:00"


def test_medications_to_tasks_null_provider(feed_service):
    """Test medication transformation with null provider."""
    medication = {
        "id": str(uuid4()),
        "name": "Aspirin",
        "dosage": "81mg",
        "frequency": "daily",
        "instructions": None,
        "care_teams": None,
    }

    result = feed_service._medications_to_tasks([medication], {})

    assert len(result) == 1
    task = result[0]
    assert task["provider"] is None


# ── _obligations_to_tasks Tests ───────────────────────────────


def test_obligations_to_tasks_no_adherence(feed_service, sample_obligation):
    """Test obligation transformation with no adherence."""
    result = feed_service._obligations_to_tasks([sample_obligation], {})

    assert len(result) == 1
    task = result[0]
    assert task["type"] == "obligation"
    assert task["target_id"] == sample_obligation["id"]
    assert task["name"] == "Morning walk"
    assert task["description"] is None
    assert task["frequency"] == "daily"
    assert task["status"] == "pending"
    assert task["provider"] is not None
    assert task["provider"]["name"] == "Dr. John Doe"


def test_obligations_to_tasks_with_skipped_adherence(feed_service, sample_obligation):
    """Test obligation transformation with skipped adherence."""
    adherence_log = {
        "target_id": sample_obligation["id"],
        "target_type": "obligation",
        "status": "skipped",
        "logged_at": "2024-01-15T07:00:00Z",
        "scheduled_time": "07:00:00",
    }
    adherence_map = {("obligation", sample_obligation["id"]): adherence_log}

    result = feed_service._obligations_to_tasks([sample_obligation], adherence_map)

    assert len(result) == 1
    task = result[0]
    assert task["status"] == "skipped"


# ── _calculate_summary Tests ──────────────────────────────────


def test_calculate_summary_empty_tasks(feed_service):
    """Test summary calculation with empty tasks."""
    result = feed_service._calculate_summary([])

    assert result["total"] == 0
    assert result["completed"] == 0
    assert result["pending"] == 0
    assert result["skipped"] == 0
    assert result["missed"] == 0


def test_calculate_summary_mixed_statuses(feed_service):
    """Test summary calculation with various task statuses."""
    tasks = [
        {"status": "completed"},
        {"status": "completed"},
        {"status": "pending"},
        {"status": "pending"},
        {"status": "skipped"},
        {"status": "missed"},
    ]

    result = feed_service._calculate_summary(tasks)

    assert result["total"] == 6
    assert result["completed"] == 2
    assert result["pending"] == 2
    assert result["skipped"] == 1
    assert result["missed"] == 1


def test_calculate_summary_all_completed(feed_service):
    """Test summary calculation with all completed tasks."""
    tasks = [
        {"status": "completed"},
        {"status": "completed"},
        {"status": "completed"},
    ]

    result = feed_service._calculate_summary(tasks)

    assert result["total"] == 3
    assert result["completed"] == 3
    assert result["pending"] == 0
    assert result["skipped"] == 0
    assert result["missed"] == 0


# ── get_today Integration Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_get_today_empty_feed(feed_service, mock_supabase_client):
    """Test get_today with no medications or obligations."""
    # Mock empty responses
    mock_result = Mock()
    mock_result.data = []

    mock_table = Mock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.gte.return_value = mock_table
    mock_table.lt.return_value = mock_table
    mock_table.execute.return_value = mock_result

    mock_supabase_client.table.return_value = mock_table

    patient_id = uuid4()
    result = await feed_service.get_today(patient_id)

    assert result["date"] == date.today().isoformat()
    assert result["timezone"] == "UTC"
    assert result["tasks"] == []
    assert result["summary"]["total"] == 0


@pytest.mark.asyncio
async def test_get_today_with_custom_date(feed_service, mock_supabase_client):
    """Test get_today with custom date parameter."""
    # Mock empty responses
    mock_result = Mock()
    mock_result.data = []

    mock_table = Mock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.gte.return_value = mock_table
    mock_table.lt.return_value = mock_table
    mock_table.execute.return_value = mock_result

    mock_supabase_client.table.return_value = mock_table

    patient_id = uuid4()
    target_date = date(2024, 1, 15)
    result = await feed_service.get_today(patient_id, target_date=target_date)

    assert result["date"] == "2024-01-15"


@pytest.mark.asyncio
async def test_get_today_with_timezone(feed_service, mock_supabase_client):
    """Test get_today with custom timezone."""
    # Mock empty responses
    mock_result = Mock()
    mock_result.data = []

    mock_table = Mock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.gte.return_value = mock_table
    mock_table.lt.return_value = mock_table
    mock_table.execute.return_value = mock_result

    mock_supabase_client.table.return_value = mock_table

    patient_id = uuid4()
    result = await feed_service.get_today(patient_id, timezone="America/New_York")

    assert result["timezone"] == "America/New_York"
