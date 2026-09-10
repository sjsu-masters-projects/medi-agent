from app.config import Settings


def test_stable_flash_lite_is_the_default_model() -> None:
    """The retired preview model must never be the application default."""
    settings = Settings(
        _env_file=None,
        supabase_url="https://test.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service-role",
        supabase_jwt_secret="jwt-secret",
    )

    assert settings.gemini_flash_model == "gemini-3.1-flash-lite"
