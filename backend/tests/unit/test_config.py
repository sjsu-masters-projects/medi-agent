from app.config import Settings


def test_production_model_defaults_use_global_vertex_endpoints() -> None:
    """Default model routes must not regress to retired or regional endpoints."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://test.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service-role",
        supabase_jwt_secret="jwt-secret",
    )

    assert settings.gemini_flash_model == "gemini-3.8-flash"
    assert settings.vertex_ai_location == "global"
    assert settings.gemini_vertex_ai_location == "global"
