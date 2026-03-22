"""Tests for MCP servers."""

import base64
import os
from unittest.mock import patch

import pytest

from app.mcp import deepgram_server, supabase_server

# Skip Deepgram tests if API key not available
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
skip_deepgram = pytest.mark.skipif(
    not DEEPGRAM_API_KEY, reason="DEEPGRAM_API_KEY not set in environment"
)


class TestSupabaseMCPServer:
    """Tests for Supabase MCP server."""

    def test_get_tools(self):
        """Test that Supabase server exposes correct tools."""
        tools = supabase_server.get_tools()

        assert len(tools) == 6
        tool_names = [t["name"] for t in tools]
        assert "get_patient_medications" in tool_names
        assert "get_patient_conditions" in tool_names
        assert "get_patient_allergies" in tool_names
        assert "get_patient_adherence_stats" in tool_names
        assert "get_recent_symptoms" in tool_names
        assert "get_patient_context" in tool_names

        # Check schema structure
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "patient_id" in tool["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_get_patient_medications_empty(self):
        """Test get_patient_medications with non-existent patient."""
        result = await supabase_server.call_tool(
            "get_patient_medications", {"patient_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "patient_id" in result
        assert "medications" in result
        assert "count" in result
        assert isinstance(result["medications"], list)
        assert result["count"] == len(result["medications"])

    @pytest.mark.asyncio
    async def test_get_patient_conditions_empty(self):
        """Test get_patient_conditions with non-existent patient."""
        result = await supabase_server.call_tool(
            "get_patient_conditions", {"patient_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "patient_id" in result
        assert "conditions" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_get_patient_allergies_empty(self):
        """Test get_patient_allergies with non-existent patient."""
        result = await supabase_server.call_tool(
            "get_patient_allergies", {"patient_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "patient_id" in result
        assert "allergies" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_get_patient_adherence_stats(self):
        """Test get_patient_adherence_stats."""
        result = await supabase_server.call_tool(
            "get_patient_adherence_stats",
            {"patient_id": "00000000-0000-0000-0000-000000000000", "days": 30},
        )

        assert "patient_id" in result
        assert "adherence_rate" in result
        assert "streak" in result
        assert "total_doses" in result
        assert "taken_doses" in result
        assert "days" in result
        assert result["days"] == 30

    @pytest.mark.asyncio
    async def test_get_recent_symptoms(self):
        """Test get_recent_symptoms."""
        result = await supabase_server.call_tool(
            "get_recent_symptoms", {"patient_id": "00000000-0000-0000-0000-000000000000", "days": 7}
        )

        assert "patient_id" in result
        assert "symptoms" in result
        assert "count" in result
        assert "days" in result
        assert result["days"] == 7

    @pytest.mark.asyncio
    async def test_get_patient_context(self):
        """Test get_patient_context (aggregated data)."""
        result = await supabase_server.call_tool(
            "get_patient_context", {"patient_id": "00000000-0000-0000-0000-000000000000"}
        )

        assert "patient_id" in result
        assert "medications" in result
        assert "conditions" in result
        assert "allergies" in result
        assert "recent_symptoms" in result
        assert "adherence" in result
        assert "rate" in result["adherence"]
        assert "streak" in result["adherence"]

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self):
        """Test calling invalid tool name."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await supabase_server.call_tool(
                "invalid_tool", {"patient_id": "00000000-0000-0000-0000-000000000000"}
            )


class TestDeepgramMCPServer:
    """Tests for Deepgram MCP server."""

    def test_get_tools(self):
        """Test that Deepgram server exposes correct tools."""
        tools = deepgram_server.get_tools()

        assert len(tools) == 3
        tool_names = [t["name"] for t in tools]
        assert "transcribe_audio" in tool_names
        assert "generate_speech" in tool_names
        assert "transcribe_patient_message" in tool_names

        # Check schema structure
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    @pytest.mark.asyncio
    async def test_generate_speech_success(self):
        """Test TTS generation with mocked Deepgram client."""
        with patch("app.mcp.deepgram_server.generate_speech_async") as mock_generate:
            # Mock the TTS response
            mock_audio = b"fake_audio_data"
            mock_generate.return_value = mock_audio

            result = await deepgram_server.call_tool(
                "generate_speech",
                {"text": "Hello, this is a test", "model": "aura-2-asteria-en", "encoding": "mp3"},
            )

            assert result["success"] is True
            assert "audio_base64" in result
            assert len(result["audio_base64"]) > 0
            assert result["model"] == "aura-2-asteria-en"
            assert result["encoding"] == "mp3"
            assert result["text_length"] == 21  # "Hello, this is a test" without trailing space
            assert result["audio_size"] > 0

            # Verify it's valid base64
            audio_bytes = base64.b64decode(result["audio_base64"])
            assert len(audio_bytes) > 0

            # Verify the mock was called
            mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self):
        """Test STT transcription with mocked Deepgram client."""
        with patch("app.mcp.deepgram_server.transcribe_audio_file_async") as mock_transcribe:
            # Mock the STT response
            mock_transcribe.return_value = "Hello world"

            # Create fake audio data
            fake_audio = base64.b64encode(b"fake_audio_data").decode()

            stt_result = await deepgram_server.call_tool(
                "transcribe_audio",
                {
                    "audio_base64": fake_audio,
                    "model": "nova-3",
                    "language": "en",
                    "smart_format": True,
                },
            )

            assert stt_result["success"] is True
            assert "transcript" in stt_result
            assert stt_result["transcript"] == "Hello world"
            assert stt_result["model"] == "nova-3"
            assert stt_result["language"] == "en"

            # Verify the mock was called
            mock_transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_patient_message(self):
        """Test patient message transcription with mocked Deepgram client."""
        with patch("app.mcp.deepgram_server.transcribe_audio_file_async") as mock_transcribe:
            # Mock the STT response
            mock_transcribe.return_value = "I have a headache"

            # Create fake audio data
            fake_audio = base64.b64encode(b"fake_audio_data").decode()

            result = await deepgram_server.call_tool(
                "transcribe_patient_message",
                {"audio_base64": fake_audio, "patient_id": "00000000-0000-0000-0000-000000000000"},
            )

            assert result["success"] is True
            assert "transcript" in result
            assert result["transcript"] == "I have a headache"
            assert "patient_id" in result
            assert result["patient_id"] == "00000000-0000-0000-0000-000000000000"
            assert result["model"] == "nova-3"

            # Verify the mock was called
            mock_transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcribe_invalid_audio(self):
        """Test transcription with invalid audio."""
        result = await deepgram_server.call_tool(
            "transcribe_audio",
            {"audio_base64": "invalid_base64_data", "model": "nova-3", "language": "en"},
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self):
        """Test calling invalid tool name."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await deepgram_server.call_tool("invalid_tool", {"text": "test"})

    @pytest.mark.asyncio
    async def test_generate_speech_empty_text(self):
        """Test TTS with empty text."""
        result = await deepgram_server.call_tool(
            "generate_speech", {"text": "", "model": "aura-2-asteria-en", "encoding": "mp3"}
        )

        # Should handle gracefully (may succeed with silence or fail)
        assert "success" in result
        if result["success"]:
            assert "audio_base64" in result
        else:
            assert "error" in result
