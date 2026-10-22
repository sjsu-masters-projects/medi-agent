"""App config — loads from .env via pydantic-settings.

Searches for .env in:
  1. Project root (../../.. from this file)
  2. CWD (for Docker / CI where layout differs)
"""

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve project root:  config.py → app/ → src/ → backend/ → project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env" if (_PROJECT_ROOT / ".env").exists() else ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase (required — app won't boot without these)
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str  # Dashboard → Settings → API → JWT Secret

    # Independent notification snapshot key; never an authentication signing key.
    # If absent, use a domain-separated derived key during compatible rollout.
    notification_token_signing_secret: str | None = Field(default=None, min_length=32)

    # Google / Gemini (optional until agent work starts)
    google_api_key: str = ""
    google_project_id: str = ""

    # Model routing
    # 3.8 Flash is the model measured under the rebuilt evaluation protocol, so it is what
    # production runs. Google classifies it as short-term availability, meaning it can be
    # retired 45 days after a replacement ships — an accepted trade, because the model id
    # is configuration and switching is a one-line change here plus a redeploy. Watch the
    # release notes: a retired id fails as a 404 at call time, which is how
    # `gemini-3.1-flash-lite-preview` once broke chat in production.
    gemini_triage_model: str = "gemini-3.5-flash-lite"
    gemini_flash_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.5-flash"
    gemini_pro_model: str = "gemini-3.1-pro-preview"
    google_embedding_model: str = "gemini-embedding-001"
    rag_embedding_dimensions: int = 768
    rag_min_similarity: float = 0.72

    # Vertex AI transports keep separate settings so either can move independently.
    # Interactive Gemini models use the global Gen AI endpoint. The MaaS location remains
    # for evaluation of managed open-weight models; no patient chat route depends on it.
    vertex_ai_location: str = "global"
    gemini_vertex_ai_location: str = "global"
    # The chat pipeline makes two sequential model calls. Per-workload deadlines live in
    # the registry; this outer ceiling prevents their fallbacks from accumulating into a
    # minute-long websocket turn. MaaS failures open a short process-local cooldown so a
    # burst of patients does not repeat the same throttled call.
    chat_turn_timeout_seconds: float = 30.0
    model_circuit_breaker_cooldown_seconds: float = 60.0
    model_max_concurrency: int = Field(default=2, ge=1, le=32)
    model_min_start_interval_seconds: float = Field(default=0.25, ge=0, le=10)

    # Per-workload kill switches. Turning one off routes that workload to the
    # deterministic path recorded beside it in `app/adk/registry.py`, which is why every
    # workload is required to have one. The registry checks these names at import, so a
    # switch renamed here without being renamed there fails loudly rather than reading
    # as "disabled".
    triage_ai_enabled: bool = True
    reply_ai_enabled: bool = True
    extraction_ai_enabled: bool = True
    discrepancy_ai_enabled: bool = True
    adr_extraction_ai_enabled: bool = True
    explanation_ai_enabled: bool = True
    care_plan_ai_enabled: bool = True
    care_plan_translation_ai_enabled: bool = True
    soap_ai_enabled: bool = True
    # Operational ceiling per SOAP attempt, not measured task performance.
    soap_generation_timeout_seconds: float = Field(default=90.0, gt=0, le=300)

    # NVIDIA NIM (independent provider for evaluation comparison)
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_model: str = "openai/gpt-oss-20b"

    # Deepgram
    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model_en: str = "aura-2-asteria-en"
    # Female Mexican-Spanish voice, matching the English one, so Nora keeps one persona.
    deepgram_tts_model_es: str = "aura-2-estrella-es"
    voice_max_audio_bytes: int = 5 * 1024 * 1024
    # Live voice mode (VOICE-001): speech is streamed to Deepgram through our websocket, the
    # key never reaches the browser, and the transcript is TEXT that takes the normal chat
    # turn path. Every value is a bound, not a target.
    voice_live_enabled: bool = True
    # nova-3 "multi" transcribes English and Spanish (and mixes) without pinning a language.
    deepgram_live_language: str = "multi"
    # Silence after speech that ends an utterance (Deepgram `endpointing`), in ms.
    deepgram_endpointing_ms: int = Field(default=500, ge=10, le=5000)
    # Word-gap fallback end of speech (Deepgram `utterance_end_ms`); Deepgram's minimum is 1000.
    deepgram_utterance_end_ms: int = Field(default=1200, ge=1000, le=5000)
    voice_live_sample_rate: int = 16000
    voice_live_max_utterance_seconds: float = Field(default=45.0, gt=0, le=300)
    voice_live_max_utterance_chars: int = Field(default=2000, ge=50, le=8000)
    voice_live_max_session_seconds: float = Field(default=900.0, gt=0, le=3600)
    voice_live_idle_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    # Streaming sessions at once in this process (a bulkhead on provider cost and sockets).
    voice_live_max_sessions: int = Field(default=20, ge=1, le=500)
    voice_live_audio_queue_frames: int = Field(default=64, ge=4, le=512)
    voice_live_max_frame_bytes: int = Field(default=32 * 1024, ge=512, le=256 * 1024)
    voice_live_connect_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    voice_live_send_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    # Streaming text to speech (Aura-2 over the Speak websocket, linear16 PCM).
    voice_tts_stream_enabled: bool = True
    voice_tts_sample_rate: int = 24000
    voice_tts_max_chars_per_reply: int = Field(default=2500, ge=100, le=10000)
    voice_tts_sentence_max_chars: int = Field(default=240, ge=40, le=1000)
    voice_tts_connect_timeout_seconds: float = Field(default=6.0, gt=0, le=30)
    voice_tts_idle_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    # Resend (email)
    resend_api_key: str = ""
    resend_from_email: str = ""
    resend_clinician_onboarding_from_email: str = (
        "MediAgent Clinician Onboarding <onboarding@mail.mediagent.live>"
    )
    # Optional dedicated key for hashing email verification codes. Falls back to the
    # Supabase JWT secret when empty.
    email_code_hmac_secret: str = ""

    # Sentry
    sentry_environment: str = "development"
    sentry_release: str = ""
    sentry_debug: bool = False
    backend_sentry_dsn: str = ""

    # App URLs
    backend_url: str = "http://localhost:8000"
    patient_portal_url: str = "http://localhost:3000"
    clinician_portal_url: str = "http://localhost:3001"

    # SMART on FHIR (empty values keep the integration disabled outside configured demos)
    smart_client_id: str = ""
    smart_client_secret: str = ""
    smart_redirect_uri: str = ""
    smart_state_encryption_key: str = ""
    smart_allowed_issuers: str = "https://launch.smarthealthit.org/v/r4/fhir"
    # SMART Health IT's launcher uses a simulator-specific issuer for a direct
    # standalone launch. The sim segment is the launcher's base64url launch
    # options array; this one decodes to
    # [3,"","","AUTO",0,0,0,"","","","","","","",0,1,""]: patient-standalone,
    # patient login and picker, public client, PKCE "auto". EHR-initiated
    # launches continue to use the issuer received from the EHR launch context
    # and must still match the allowlist.
    smart_standalone_issuer: str = (
        "https://launch.smarthealthit.org/v/r4/sim/"
        "WzMsIiIsIiIsIkFVVE8iLDAsMCwwLCIiLCIiLCIiLCIiLCIiLCIiLCIiLDAsMSwiIl0/fhir"
    )
    smart_scopes: str = (
        "patient/Patient.read patient/Encounter.read patient/Condition.read "
        "patient/AllergyIntolerance.read patient/MedicationRequest.read "
        "patient/MedicationStatement.read patient/Observation.read patient/DiagnosticReport.read "
        "patient/Procedure.read patient/CarePlan.read patient/DocumentReference.read"
    )
    smart_launch_ttl_seconds: int = 600
    smart_handoff_ttl_seconds: int = 300

    # OPS-006 phase 2: Nora turns run in a separate worker service behind a Cloud Tasks queue.
    # Both flags default to false, so a deploy changes nothing until they are set.
    #   chat_turns_via_worker  the API queues a turn and never runs model work in-process.
    #   worker_mode            this process IS the worker: it serves only the task endpoint.
    chat_turns_via_worker: bool = False
    worker_mode: bool = False
    cloud_tasks_project: str = ""  # falls back to google_project_id
    cloud_tasks_location: str = "us-central1"
    cloud_tasks_queue: str = "nora-turns"
    chat_worker_url: str = ""  # the worker service's https URL, no trailing slash
    chat_worker_invoker_sa: str = ""  # service account the queue signs its OIDC token as
    chat_worker_oidc_audience: str = ""  # defaults to chat_worker_url
    # How long a queued turn may wait for a worker before it is reconciled to interrupted.
    chat_turn_queue_seconds: int = Field(default=120, ge=10, le=120)
    # Tasks one worker instance runs at once; more are refused with 503 so the queue retries.
    chat_worker_max_concurrency: int = Field(default=4, ge=1, le=32)

    # AI-003: bounded per-workload/model availability counters (migration 090). Off stops both
    # the in-memory counting and the flush; the read endpoint then reports an empty window.
    ai_availability_enabled: bool = True
    ai_availability_flush_seconds: float = Field(default=30.0, ge=5.0, le=600.0)

    # Longest an interactive model call waits for a free slot before it is shed (OPS-006 rule 14).
    model_admission_wait_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    # A reply that fails after text was shown tries the backup model only if at least this much
    # of the reply budget is left; otherwise the reviewed unavailable message is used.
    reply_fallback_min_seconds: float = Field(default=2.0, ge=0.5, le=10.0)

    # Internal cron auth
    cron_auth_token: str = ""

    environment: str = "development"
    log_level: str = "DEBUG"

    # Requires an actually approved paired-locale bundle and schema 050.
    symptom_intake_enabled: bool = False

    # LOC-003: answer translation calls from a deterministic local glossary instead of the
    # model, so the English-first review, guard and attestation paths can be exercised where
    # Vertex AI is unreachable. Ignored in production (see translation_stub.stub_enabled);
    # stubbed wording is marked in telemetry and must never be approved for a patient.
    translation_stub_enabled: bool = False

    # A2A retry worker
    a2a_retry_worker_enabled: bool = True
    a2a_retry_poll_seconds: int = 15
    a2a_retry_batch_size: int = 25

    # Cloud Run Job worker. Upload requests leave documents pending; this bounded
    # batch process owns OCR and model extraction outside request CPU lifetimes.
    document_ingestion_batch_size: int = 10

    @property
    def allowed_origins(self) -> Any:
        origins = {self.patient_portal_url, self.clinician_portal_url}
        if self.environment == "development":
            origins |= {
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
            }
        return list(origins)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


# Deferred init — won't crash at import time if .env is missing,
# only when `settings` is actually accessed.
settings = Settings()  # type: ignore[call-arg]
