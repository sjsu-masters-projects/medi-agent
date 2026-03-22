"""Test that the app boots and all expected routes are registered."""

import os

# Set dummy env vars BEFORE importing the app
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")


def test_app_creates_successfully():
    from app.main import create_app

    app = create_app()
    assert app is not None
    assert app.title == "MediAgent API"


def test_all_expected_routes_registered():
    from app.main import create_app

    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, "methods")}

    expected_auth = {
        "/api/v1/auth/signup/patient",
        "/api/v1/auth/signup/clinician",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/password-reset",
        "/api/v1/auth/me",
    }
    expected_patient = {
        "/api/v1/patients/me",
        "/api/v1/patients/me/care-team",
        "/api/v1/patients/me/care-team/join",
    }
    expected_clinician = {
        "/api/v1/clinicians/me",
        "/api/v1/clinicians/me/patients",
        "/api/v1/clinicians/me/patients/{patient_id}",
        "/api/v1/clinicians/me/invite-code",
    }
    expected_document = {
        "/api/v1/documents/",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/explain",
    }
    expected_meds = {
        "/api/v1/medications/",
        "/api/v1/medications/{medication_id}",
        "/api/v1/obligations/",
        "/api/v1/obligations/{obligation_id}",
        "/api/v1/adherence/",
        "/api/v1/adherence/stats",
    }

    all_expected = (
        expected_auth | expected_patient | expected_clinician | expected_document | expected_meds
    )
    missing = all_expected - paths
    assert not missing, f"Missing routes: {missing}"


def test_health_endpoint():
    from app.main import create_app

    app = create_app()
    paths = {r.path for r in app.routes if hasattr(r, "methods")}
    assert "/health" in paths
