"""SMART App Launch orchestration with local clinician authorization."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode, urljoin, urlparse
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from supabase import Client

from app.config import settings
from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.services.fhir_import_service import FhirImportService


class SmartLaunchService:
    """Run OAuth server-side and hand results only to an authorized local clinician."""

    def __init__(self, db: Client, http_client: httpx.Client | None = None) -> None:
        self.db = db
        self.http = http_client or httpx.Client(timeout=15.0, follow_redirects=False)
        self.imports = FhirImportService(db)

    def start_launch(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        issuer: str,
        launch_context: str | None = None,
    ) -> dict[str, Any]:
        """Create a PKCE-bound session after confirming local care-team authority.

        An EHR may supply an opaque ``launch`` handle alongside ``iss``.  It is
        echoed only to the authorization endpoint and stored encrypted for the
        short lifetime of the session; it never substitutes for local authority.
        """
        self._require_config()
        self._require_assignment(clinician_id, patient_id)
        issuer = self._validate_issuer(issuer)
        configuration = self._discover(issuer)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        nonce = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.smart_launch_ttl_seconds)
        cipher = self._cipher()
        requested_scopes = self._requested_scopes(launch_context)
        payload = {
            "state_hash": self._digest(state),
            "pkce_verifier_ciphertext": cipher.encrypt(verifier.encode()).decode(),
            "issuer": issuer,
            "authorization_endpoint": configuration["authorization_endpoint"],
            "token_endpoint": configuration["token_endpoint"],
            "launch_context": (
                cipher.encrypt(launch_context.encode()).decode() if launch_context else None
            ),
            "clinician_id": str(clinician_id),
            "patient_id": str(patient_id),
            "requested_scopes": requested_scopes,
            "nonce": nonce,
            "expires_at": expires_at.isoformat(),
        }
        response = self.db.table("smart_launch_sessions").insert(payload).execute()
        if not response.data:
            raise ValidationError("Could not create SMART launch session")
        params = {
            "response_type": "code",
            "client_id": settings.smart_client_id,
            "redirect_uri": self._redirect_uri(),
            "scope": requested_scopes,
            "aud": issuer,
            "state": state,
            "nonce": nonce,
            "code_challenge": self._code_challenge(verifier),
            "code_challenge_method": "S256",
        }
        if launch_context:
            params["launch"] = launch_context
        return {
            "authorization_url": f"{configuration['authorization_endpoint']}?{urlencode(params)}",
            "expires_at": expires_at,
        }

    def handle_callback(self, *, state: str, code: str | None, error: str | None) -> dict[str, Any]:
        """Consume one callback, fetch contextual resources, and mint a local handoff."""
        session = self._load_active_session(state)
        try:
            # A provider error is still a callback for this state. Consume it so
            # it cannot be replayed after a failed authorization attempt.
            if error:
                raise ValidationError(f"SMART authorization failed: {error}")
            if not code:
                raise ValidationError("SMART callback is missing authorization code")
            verifier = self._decrypt_verifier(str(session["pkce_verifier_ciphertext"]))
            token = self._exchange_code(session=session, code=code, verifier=verifier)
            resources, context = self._fetch_contextual_resources(session=session, token=token)
            import_record = self._create_import(session=session, context=context)
            result = self.imports.import_resources(
                import_id=UUID(str(import_record["id"])),
                patient_id=UUID(str(session["patient_id"])),
                actor_id=UUID(str(session["clinician_id"])),
                issuer=str(session["issuer"]),
                resources=resources,
            )
            status = "completed_with_warnings" if result["warnings"] else "completed"
            self.db.table("fhir_imports").update(
                {
                    "status": status,
                    "resource_count": result["resources_persisted"],
                    "candidate_fact_count": result["candidate_facts_created"],
                    "warnings": result["warnings"],
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", str(import_record["id"])).execute()
        except Exception as exc:
            if "import_record" in locals():
                self.db.table("fhir_imports").update(
                    {
                        "status": "failed",
                        "failure_reason": str(exc)[:1000],
                        "completed_at": datetime.now(UTC).isoformat(),
                    }
                ).eq("id", str(import_record["id"])).execute()
            raise
        finally:
            self.db.table("smart_launch_sessions").update(
                {"consumed_at": datetime.now(UTC).isoformat()}
            ).eq("id", str(session["id"])).is_("consumed_at", "null").execute()

        ticket = secrets.token_urlsafe(36)
        handoff = (
            self.db.table("smart_portal_handoffs")
            .insert(
                {
                    "ticket_hash": self._digest(ticket),
                    "import_id": str(import_record["id"]),
                    "clinician_id": str(session["clinician_id"]),
                    "expires_at": (
                        datetime.now(UTC) + timedelta(seconds=settings.smart_handoff_ttl_seconds)
                    ).isoformat(),
                }
            )
            .execute()
        )
        if not handoff.data:
            raise ValidationError("Could not create SMART portal handoff")
        return {"import_id": import_record["id"], "ticket": ticket}

    def redeem_handoff(self, *, clinician_id: UUID, ticket: str) -> dict[str, Any]:
        """Return an import only once, and only to the original local clinician."""
        result = (
            self.db.table("smart_portal_handoffs")
            .select("*")
            .eq("ticket_hash", self._digest(ticket))
            .single()
            .execute()
        )
        handoff = cast(dict[str, Any] | None, result.data)
        if not handoff or handoff.get("consumed_at") or self._expired(handoff.get("expires_at")):
            raise AuthorizationError("SMART handoff is invalid or expired")
        if str(handoff.get("clinician_id")) != str(clinician_id):
            raise AuthorizationError("SMART handoff belongs to another clinician")
        import_result = (
            self.db.table("fhir_imports")
            .select("*")
            .eq("id", handoff["import_id"])
            .single()
            .execute()
        )
        import_record = cast(dict[str, Any] | None, import_result.data)
        if not import_record:
            raise ValidationError("SMART import no longer exists")
        self._require_assignment(clinician_id, UUID(str(import_record["patient_id"])))
        self.db.table("smart_portal_handoffs").update(
            {"consumed_at": datetime.now(UTC).isoformat()}
        ).eq("id", str(handoff["id"])).is_("consumed_at", "null").execute()
        resources = (
            self.db.table("fhir_import_resources")
            .select(
                "id, resource_type, external_resource_id, version_id, validation_errors, mapping_warnings, created_at"
            )
            .eq("import_id", str(import_record["id"]))
            .execute()
        )
        return {"import_record": import_record, "resources": resources.data or []}

    def list_imports(self, *, clinician_id: UUID, patient_id: UUID) -> list[dict[str, Any]]:
        self._require_assignment(clinician_id, patient_id)
        result = (
            self.db.table("fhir_imports")
            .select("*")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    def ensure_assignment(self, *, clinician_id: UUID, patient_id: UUID) -> None:
        """Expose the same care-team gate for read/review routes."""
        self._require_assignment(clinician_id, patient_id)

    def _discover(self, issuer: str) -> dict[str, str]:
        try:
            response = self.http.get(f"{issuer}/.well-known/smart-configuration")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError("SMART discovery", str(exc)) from None
        if not isinstance(payload, dict):
            raise ExternalServiceError("SMART discovery", "Invalid discovery document")
        authorization_endpoint = payload.get("authorization_endpoint")
        token_endpoint = payload.get("token_endpoint")
        if not isinstance(authorization_endpoint, str) or not isinstance(token_endpoint, str):
            raise ExternalServiceError("SMART discovery", "Required OAuth endpoints are missing")
        for endpoint in (authorization_endpoint, token_endpoint):
            if urlparse(endpoint).scheme != "https":
                raise ExternalServiceError("SMART discovery", "OAuth endpoint must use HTTPS")
        return {"authorization_endpoint": authorization_endpoint, "token_endpoint": token_endpoint}

    def _exchange_code(
        self, *, session: dict[str, Any], code: str, verifier: str
    ) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri(),
            "client_id": settings.smart_client_id,
            "code_verifier": verifier,
        }
        if settings.smart_client_secret:
            data["client_secret"] = settings.smart_client_secret
        try:
            response = self.http.post(str(session["token_endpoint"]), data=data)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError("SMART token exchange", str(exc)) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            raise ExternalServiceError("SMART token exchange", "Access token missing from response")
        self._validate_token_response(payload, issuer=str(session["issuer"]))
        return payload

    def _fetch_contextual_resources(
        self, *, session: dict[str, Any], token: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
        issuer = str(session["issuer"]).rstrip("/")
        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/fhir+json",
        }
        patient = token.get("patient") if isinstance(token.get("patient"), str) else None
        encounter = token.get("encounter") if isinstance(token.get("encounter"), str) else None
        if not patient:
            raise ExternalServiceError(
                "SMART launch context", "Token response did not include patient context"
            )
        resources: list[dict[str, Any]] = []
        for resource_type, query in self._resource_queries(patient, encounter):
            url = f"{issuer}/{resource_type}{query}"
            resources.extend(self._get_bundle_resources(url=url, headers=headers, issuer=issuer))
        return resources, {"patient": patient, "encounter": encounter}

    @staticmethod
    def _resource_queries(patient: str, encounter: str | None) -> list[tuple[str, str]]:
        queries = [("Patient", f"/{patient}"), ("Encounter", f"?patient={patient}")]
        for resource_type in (
            "Condition",
            "AllergyIntolerance",
            "MedicationRequest",
            "MedicationStatement",
            "Observation",
            "DiagnosticReport",
            "Procedure",
            "CarePlan",
            "DocumentReference",
        ):
            queries.append((resource_type, f"?patient={patient}"))
        if encounter:
            queries.append(("Encounter", f"/{encounter}"))
        return queries

    def _get_bundle_resources(
        self, *, url: str, headers: dict[str, str], issuer: str
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            try:
                response = self.http.get(next_url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ExternalServiceError("FHIR resource fetch", str(exc)) from None
            if not isinstance(payload, dict):
                raise ExternalServiceError("FHIR resource fetch", "Invalid FHIR response")
            if payload.get("resourceType") != "Bundle":
                resources.append(payload)
                break
            resources.extend(
                entry["resource"]
                for entry in payload.get("entry", [])
                if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
            )
            next_url = self._next_bundle_url(payload, issuer)
        return resources

    @staticmethod
    def _next_bundle_url(bundle: dict[str, Any], issuer: str) -> str | None:
        for link in bundle.get("link", []):
            if (
                isinstance(link, dict)
                and link.get("relation") == "next"
                and isinstance(link.get("url"), str)
            ):
                url = link["url"]
                parsed = urlparse(urljoin(issuer + "/", url))
                if parsed.scheme != "https" or parsed.netloc != urlparse(issuer).netloc:
                    raise ExternalServiceError(
                        "FHIR resource fetch", "Rejected pagination URL outside issuer"
                    )
                return parsed.geturl()
        return None

    def _create_import(
        self, *, session: dict[str, Any], context: dict[str, str | None]
    ) -> dict[str, Any]:
        response = (
            self.db.table("fhir_imports")
            .insert(
                {
                    "launch_session_id": str(session["id"]),
                    "clinician_id": str(session["clinician_id"]),
                    "patient_id": str(session["patient_id"]),
                    "issuer": str(session["issuer"]),
                    "external_patient_id": context["patient"],
                    "external_encounter_id": context["encounter"],
                    "status": "importing",
                }
            )
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise ValidationError("Could not create FHIR import")
        return rows[0]

    def _load_active_session(self, state: str) -> dict[str, Any]:
        response = (
            self.db.table("smart_launch_sessions")
            .select("*")
            .eq("state_hash", self._digest(state))
            .single()
            .execute()
        )
        session = cast(dict[str, Any] | None, response.data)
        if not session or session.get("consumed_at") or self._expired(session.get("expires_at")):
            raise AuthorizationError("SMART launch state is invalid or expired")
        return session

    def _require_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        response = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not response.data:
            raise AuthorizationError("You are not assigned to this patient")

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _code_challenge(verifier: str) -> str:
        return (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )

    @staticmethod
    def _requested_scopes(launch_context: str | None) -> str:
        """Use the SMART scope appropriate to standalone or EHR launch.

        ``launch/patient`` and ``launch/encounter`` request context for a
        standalone launch.  An EHR launch instead requires the generic
        ``launch`` scope and the opaque launch handle in the authorization
        request.  Resource-read scopes remain configuration-owned.
        """
        configured = [
            scope
            for scope in settings.smart_scopes.split()
            if scope not in {"launch", "launch/patient", "launch/encounter"}
        ]
        context_scopes = ["launch"] if launch_context else ["launch/patient", "launch/encounter"]
        return " ".join([*context_scopes, *configured])

    @staticmethod
    def _expired(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")) <= datetime.now(UTC)
        except ValueError:
            return True

    @staticmethod
    def _validate_issuer(issuer: str) -> str:
        parsed = urlparse(issuer)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValidationError("SMART issuer must be an HTTPS base URL")
        normalized = issuer.rstrip("/")
        allowed = {
            value.rstrip("/")
            for value in settings.smart_allowed_issuers.split(",")
            if value.strip()
        }
        if settings.smart_standalone_issuer.strip():
            allowed.add(settings.smart_standalone_issuer.strip().rstrip("/"))
        if normalized not in allowed:
            raise ValidationError("SMART issuer is not enabled for this environment")
        return normalized

    @staticmethod
    def _validate_token_response(payload: dict[str, Any], *, issuer: str) -> None:
        """Reject clearly incomplete token responses without assuming JWT access tokens."""
        expires_in = payload.get("expires_in")
        if not isinstance(expires_in, int | float) or expires_in <= 0:
            raise ExternalServiceError("SMART token exchange", "Token expiry is missing or invalid")
        granted_scope = payload.get("scope")
        if granted_scope is not None:
            if not isinstance(granted_scope, str):
                raise ExternalServiceError("SMART token exchange", "Token scope is malformed")
            grants = set(granted_scope.split())
            required = {"patient/Patient.read"}
            if not required.issubset(grants):
                raise ExternalServiceError(
                    "SMART token exchange", "Required patient read scope was not granted"
                )
        audience = payload.get("aud")
        if audience is not None and not isinstance(audience, str):
            raise ExternalServiceError("SMART token exchange", "Token audience is malformed")
        if isinstance(audience, str) and audience.rstrip("/") != issuer.rstrip("/"):
            raise ExternalServiceError(
                "SMART token exchange", "Token audience does not match issuer"
            )

    @staticmethod
    def _redirect_uri() -> str:
        value = (
            settings.smart_redirect_uri.strip()
            or f"{settings.backend_url.rstrip('/')}/api/v1/smart/callback"
        )
        if urlparse(value).scheme != "https" and settings.environment != "development":
            raise ValidationError("SMART callback must use HTTPS outside development")
        return value

    @staticmethod
    def _cipher() -> Fernet:
        key = settings.smart_state_encryption_key.strip()
        if not key:
            raise ValidationError("SMART_STATE_ENCRYPTION_KEY is not configured")
        try:
            return Fernet(key.encode())
        except (TypeError, ValueError) as exc:
            raise ValidationError("SMART_STATE_ENCRYPTION_KEY is invalid") from exc

    def _decrypt_verifier(self, ciphertext: str) -> str:
        try:
            return self._cipher().decrypt(ciphertext.encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise AuthorizationError("SMART launch verifier is invalid") from exc

    @staticmethod
    def _require_config() -> None:
        if not settings.smart_client_id.strip():
            raise ValidationError("SMART_CLIENT_ID is not configured")
