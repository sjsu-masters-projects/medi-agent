"""Resend transport. Provider acceptance is not proof of inbox delivery."""

from __future__ import annotations

import logging
from typing import Any, cast

import resend

from app.config import settings
from app.services.email_templates import EmailContent

logger = logging.getLogger(__name__)


class ResendClient:
    def __init__(self) -> None:
        self.api_key = settings.resend_api_key.strip()
        self.default_from_email = settings.resend_from_email.strip()
        self.clinician_onboarding_from_email = (
            settings.resend_clinician_onboarding_from_email.strip() or self.default_from_email
        )
        self.enabled = bool(self.api_key)
        if self.enabled:
            resend.api_key = self.api_key

    @staticmethod
    def deliverable(address: str) -> bool:
        return bool(
            "@" in address
            and not address.lower().endswith("@accounts.mediagent.live")
            and not any(c in address for c in "\r\n")
        )

    def send(self, payload: dict[str, Any], key: str) -> str | None:
        """Send a frozen payload with its stable retry key; never log provider bodies."""
        if not self.enabled or not payload.get("from"):
            return None
        recipients = payload.get("to", [])
        if (
            not isinstance(recipients, list)
            or len(recipients) != 1
            or not self.deliverable(str(recipients[0]))
        ):
            return None
        try:
            result = resend.Emails.send(cast(Any, payload), {"idempotency_key": key})
            identifier = result.get("id") if isinstance(result, dict) else None
            return identifier if isinstance(identifier, str) and identifier else None
        except Exception:
            logger.warning("Email provider request failed; delivery state retained for retry")
            return None

    # Status polling needs a full-access API key. A sending-only key answers 401/403;
    # remember that for the life of the process and log it once instead of repolling.
    _status_unavailable = False
    _STATUS_DENIED_TYPES = {"restricted_api_key", "invalid_api_key", "missing_api_key"}

    def status_available(self) -> bool:
        return self.enabled and not ResendClient._status_unavailable

    def status(self, provider_id: str) -> str | None:
        if not self.status_available():
            return None
        try:
            result = resend.Emails.get(provider_id)
            state = result.get("last_event") if isinstance(result, dict) else None
            return state if isinstance(state, str) else None
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "")
            if code in {"401", "403"} or getattr(exc, "error_type", None) in (
                self._STATUS_DENIED_TYPES
            ):
                ResendClient._status_unavailable = True
                logger.warning(
                    "Email delivery status needs a full-access provider key; "
                    "statuses stay at provider accepted"
                )
                return None
            logger.warning("Email delivery status temporarily unavailable")
            return None

    def payload(
        self, content: EmailContent, to_email: str, *, onboarding: bool = False
    ) -> dict[str, Any]:
        return {
            "from": self.clinician_onboarding_from_email if onboarding else self.default_from_email,
            "to": [to_email],
            "subject": content.subject,
            "html": content.html,
            "text": content.text,
        }
