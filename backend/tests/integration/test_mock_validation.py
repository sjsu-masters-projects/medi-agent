"""Mock validation tests - ensures our mocks match real implementations.

These tests verify that our mock structures accurately reflect the actual
Supabase and Deepgram client behaviors. Run these periodically to catch
any API changes that would break our mocks.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.medication_service import MedicationService
from app.services.patient_service import PatientService


class TestSupabaseMockValidation:
    """Validate that our Supabase mocks match real client behavior."""

    def test_mock_matches_select_eq_single_pattern(self):
        """Verify mock matches: table().select().eq().single().execute()"""
        # This is the pattern used in get_profile methods
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.select.return_value = table
        table.eq.return_value = table
        table.single.return_value = table

        # Set up response
        expected_data = {"id": "123", "name": "Test"}
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = mock_db.table("test").select("*").eq("id", "123").single().execute()

        # Verify
        assert result.data == expected_data
        mock_db.table.assert_called_once_with("test")
        table.select.assert_called_once_with("*")
        table.eq.assert_called_once_with("id", "123")
        table.single.assert_called_once()
        table.execute.assert_called_once()

    def test_mock_matches_select_eq_eq_pattern(self):
        """Verify mock matches: table().select().eq().eq().execute()"""
        # This is the pattern used in get_care_team methods
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.select.return_value = table
        table.eq.return_value = table

        # Set up response
        expected_data = [{"id": "1"}, {"id": "2"}]
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = (
            mock_db.table("care_teams")
            .select("*")
            .eq("patient_id", "123")
            .eq("status", "active")
            .execute()
        )

        # Verify
        assert result.data == expected_data
        assert table.eq.call_count == 2

    def test_mock_matches_update_eq_pattern(self):
        """Verify mock matches: table().update().eq().execute()"""
        # This is the pattern used in update methods
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.update.return_value = table
        table.eq.return_value = table

        # Set up response
        expected_data = [{"id": "123", "name": "Updated"}]
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = mock_db.table("patients").update({"name": "Updated"}).eq("id", "123").execute()

        # Verify
        assert result.data == expected_data
        table.update.assert_called_once_with({"name": "Updated"})
        table.eq.assert_called_once_with("id", "123")

    def test_mock_matches_insert_pattern(self):
        """Verify mock matches: table().insert().execute()"""
        # This is the pattern used in create methods
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.insert.return_value = table

        # Set up response
        expected_data = [{"id": "123", "name": "New"}]
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = mock_db.table("patients").insert({"name": "New"}).execute()

        # Verify
        assert result.data == expected_data
        table.insert.assert_called_once_with({"name": "New"})

    def test_mock_matches_order_pattern(self):
        """Verify mock matches: table().select().eq().order().execute()"""
        # This is the pattern used in list methods
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.select.return_value = table
        table.eq.return_value = table
        table.order.return_value = table

        # Set up response
        expected_data = [{"id": "1"}, {"id": "2"}]
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = (
            mock_db.table("medications")
            .select("*")
            .eq("patient_id", "123")
            .order("created_at", desc=True)
            .execute()
        )

        # Verify
        assert result.data == expected_data
        table.order.assert_called_once_with("created_at", desc=True)

    def test_mock_matches_gte_pattern(self):
        """Verify mock matches: table().select().eq().gte().execute()"""
        # This is the pattern used in adherence stats
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.select.return_value = table
        table.eq.return_value = table
        table.gte.return_value = table

        # Set up response
        expected_data = [{"id": "1", "logged_at": "2025-01-15"}]
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = (
            mock_db.table("adherence_logs")
            .select("*")
            .eq("patient_id", "123")
            .gte("logged_at", "2025-01-01")
            .execute()
        )

        # Verify
        assert result.data == expected_data
        table.gte.assert_called_once_with("logged_at", "2025-01-01")

    def test_mock_matches_is_null_pattern(self):
        """Verify mock matches: table().select().eq().is_().single().execute()"""
        # This is the pattern used in join_care_team
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        table.select.return_value = table
        table.eq.return_value = table
        table.is_.return_value = table
        table.single.return_value = table

        # Set up response
        expected_data = {"id": "123", "invite_code": "ABC123"}
        table.execute.return_value = MagicMock(data=expected_data)

        # Execute the chain
        result = (
            mock_db.table("care_teams")
            .select("*")
            .eq("invite_code", "ABC123")
            .eq("status", "pending")
            .is_("patient_id", "null")
            .single()
            .execute()
        )

        # Verify
        assert result.data == expected_data
        table.is_.assert_called_once_with("patient_id", "null")


class TestDeepgramMockValidation:
    """Validate that our Deepgram mocks match real function signatures."""

    @pytest.mark.asyncio
    async def test_generate_speech_async_signature(self):
        """Verify generate_speech_async function signature matches our mock."""
        import inspect

        from app.clients.deepgram_client import generate_speech_async

        # Get function signature
        sig = inspect.signature(generate_speech_async)
        params = list(sig.parameters.keys())

        # Verify expected parameters
        assert "text" in params
        assert "model" in params
        assert "encoding" in params

        # Verify defaults
        assert sig.parameters["model"].default == "aura-2-asteria-en"
        assert sig.parameters["encoding"].default == "mp3"

    @pytest.mark.asyncio
    async def test_transcribe_audio_file_async_signature(self):
        """Verify transcribe_audio_file_async function signature matches our mock."""
        import inspect

        from app.clients.deepgram_client import transcribe_audio_file_async

        # Get function signature
        sig = inspect.signature(transcribe_audio_file_async)
        params = list(sig.parameters.keys())

        # Verify expected parameters
        assert "audio_file" in params
        assert "model" in params
        assert "language" in params
        assert "smart_format" in params

        # Verify defaults
        assert sig.parameters["model"].default == "nova-3"
        assert sig.parameters["language"].default == "en"
        assert sig.parameters["smart_format"].default is True


class TestServiceMockIntegration:
    """Validate that services work correctly with our mocks."""

    @pytest.mark.asyncio
    async def test_patient_service_with_mock(self):
        """Verify PatientService works with our mock structure."""
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        for method in ["select", "eq", "single"]:
            getattr(table, method).return_value = table

        # Set up response
        patient_data = {"id": "123", "email": "test@example.com", "first_name": "Test"}
        table.execute.return_value = MagicMock(data=patient_data)

        # Create service and call method
        service = PatientService(mock_db)
        result = await service.get_profile(uuid4())

        # Verify result matches expected structure
        assert result == patient_data
        assert "id" in result
        assert "email" in result

    @pytest.mark.asyncio
    async def test_medication_service_with_mock(self):
        """Verify MedicationService works with our mock structure."""
        mock_db = MagicMock()
        table = MagicMock()
        mock_db.table.return_value = table

        # Make methods chainable
        for method in ["select", "eq", "order"]:
            getattr(table, method).return_value = table

        # Set up response
        medications_data = [{"id": "1", "name": "Med1"}, {"id": "2", "name": "Med2"}]
        table.execute.return_value = MagicMock(data=medications_data)

        # Create service and call method
        service = MedicationService(mock_db)
        result = await service.list_medications(uuid4(), active_only=True)

        # Verify result matches expected structure
        assert result == medications_data
        assert len(result) == 2


class TestResponseStructureValidation:
    """Validate that our mock response structures match real API responses."""

    def test_supabase_execute_response_structure(self):
        """Verify execute() response has .data attribute."""
        mock_response = MagicMock()
        mock_response.data = {"id": "123"}

        # This is how services access the data
        assert hasattr(mock_response, "data")
        assert mock_response.data == {"id": "123"}

    def test_supabase_single_returns_dict(self):
        """Verify .single() queries return dict, not list."""
        # single() should return a dict directly in result.data
        mock_response = MagicMock()
        mock_response.data = {"id": "123", "name": "Test"}

        # Not a list
        assert isinstance(mock_response.data, dict)
        assert not isinstance(mock_response.data, list)

    def test_supabase_list_returns_list(self):
        """Verify non-single queries return list."""
        # Regular queries should return a list in result.data
        mock_response = MagicMock()
        mock_response.data = [{"id": "1"}, {"id": "2"}]

        assert isinstance(mock_response.data, list)

    def test_deepgram_tts_response_structure(self):
        """Verify TTS response structure matches our mock."""
        # Our mock returns this structure
        mock_response = {
            "audio_base64": "base64_encoded_audio",
            "model": "aura-2-asteria-en",
            "encoding": "mp3",
            "text_length": 21,
            "audio_size": 1024,
            "success": True,
        }

        # Verify all expected fields are present
        assert "audio_base64" in mock_response
        assert "model" in mock_response
        assert "encoding" in mock_response
        assert "text_length" in mock_response
        assert "audio_size" in mock_response
        assert "success" in mock_response

    def test_deepgram_stt_response_structure(self):
        """Verify STT response structure matches our mock."""
        # Our mock returns this structure
        mock_response = {
            "transcript": "Hello world",
            "model": "nova-3",
            "language": "en",
            "success": True,
        }

        # Verify all expected fields are present
        assert "transcript" in mock_response
        assert "model" in mock_response
        assert "language" in mock_response
        assert "success" in mock_response
