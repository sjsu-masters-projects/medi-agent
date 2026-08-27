"""App config — loads from .env via pydantic-settings.

Searches for .env in:
  1. Project root (../../.. from this file)
  2. CWD (for Docker / CI where layout differs)
"""

from pathlib import Path
from typing import Any

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

    # Google / Gemini (optional until agent work starts)
    google_api_key: str = ""
    google_project_id: str = ""

    # Model routing
    gemini_flash_model: str = "gemini-3.1-flash-lite-preview"
    gemini_pro_model: str = "gemini-3.1-pro-preview"
    medgemma_model: str = "google/medgemma-27b-it"
    google_embedding_model: str = "gemini-embedding-001"
    rag_embedding_dimensions: int = 768
    rag_min_similarity: float = 0.72

    # Vertex AI (for MedGemma deployment)
    vertex_ai_location: str = "us-central1"
    vertex_ai_medgemma_endpoint: str = ""
    vertex_ai_endpoint_type: str = "auto"  # auto, standard, vllm

    # Hugging Face (for MedGemma benchmarking)
    huggingface_api_token: str = ""

    # Deepgram
    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model_en: str = "aura-2-asteria-en"
    deepgram_tts_model_es: str = ""
    voice_max_audio_bytes: int = 5 * 1024 * 1024

    # Resend (email)
    resend_api_key: str = ""
    resend_from_email: str = "MediAgent <onboarding@resend.dev>"
    resend_clinician_onboarding_from_email: str = (
        "MediAgent Clinician Onboarding <onboarding@mail.mediagent.live>"
    )

    # Syncfusion
    syncfusion_license_key: str = ""

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
    smart_scopes: str = (
        "patient/Patient.read patient/Encounter.read patient/Condition.read "
        "patient/AllergyIntolerance.read patient/MedicationRequest.read "
        "patient/MedicationStatement.read patient/Observation.read patient/DiagnosticReport.read "
        "patient/Procedure.read patient/CarePlan.read patient/DocumentReference.read"
    )
    smart_launch_ttl_seconds: int = 600
    smart_handoff_ttl_seconds: int = 300

    # Internal cron auth
    cron_auth_token: str = ""

    environment: str = "development"
    log_level: str = "DEBUG"

    # A2A retry worker
    a2a_retry_worker_enabled: bool = True
    a2a_retry_poll_seconds: int = 15
    a2a_retry_batch_size: int = 25

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
