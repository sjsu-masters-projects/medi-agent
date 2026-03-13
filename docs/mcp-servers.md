# MCP Servers

MCP servers expose tools to AI agents for operations that benefit from shared state or connection management.

## Architecture

```
AI Agent (LangGraph)
    ↓ call_tool()
MCP Server (supabase_server / deepgram_server)
    ↓
Client (Supabase admin / Deepgram async)
    ↓
External Service
```

Simple HTTP APIs (DailyMed, RxNorm) live in the **service layer** (`app/services/`) instead — no shared state needed.

## Supabase Server

Queries patient data via a shared Supabase connection pool.

| Tool | Description |
|------|-------------|
| `get_patient_medications` | Active medications |
| `get_patient_conditions` | Active conditions |
| `get_patient_allergies` | Allergies |
| `get_patient_adherence_stats` | Adherence rate, streak, doses |
| `get_recent_symptoms` | Recent symptom reports |
| `get_patient_context` | All of the above in parallel |

```python
from app.mcp import supabase_server

context = await supabase_server.call_tool("get_patient_context", {
    "patient_id": "uuid-here"
})
```

## Deepgram Server

Voice STT/TTS via a shared async Deepgram client.

| Tool | Description |
|------|-------------|
| `transcribe_audio` | Base64 audio → text |
| `generate_speech` | Text → base64 audio |
| `transcribe_patient_message` | STT with medical-optimised settings |

```python
from app.mcp import deepgram_server

result = await deepgram_server.call_tool("transcribe_audio", {
    "audio_base64": "...",
    "model": "nova-3"
})
```

## Adding a New MCP Server

1. Create `app/mcp/<name>_server.py` extending `MCPServer`
2. Implement `get_tools()` and `call_tool()`
3. Export singleton from `app/mcp/__init__.py`
