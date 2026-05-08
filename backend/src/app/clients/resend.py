"""Resend email client helpers."""

from __future__ import annotations

import logging
from html import escape
from typing import Any, cast
from urllib.parse import urlencode

import resend

from app.config import settings

logger = logging.getLogger(__name__)


class ResendClient:
    """Thin wrapper over Resend SDK with best-effort delivery semantics."""

    def __init__(self) -> None:
        self.api_key = settings.resend_api_key.strip()
        self.default_from_email = settings.resend_from_email.strip()
        self.clinician_onboarding_from_email = (
            settings.resend_clinician_onboarding_from_email.strip() or self.default_from_email
        )
        self.enabled = bool(self.api_key and self.clinician_onboarding_from_email)
        if self.enabled:
            resend.api_key = self.api_key

    def send_clinician_invite(
        self,
        *,
        to_email: str,
        clinic_name: str,
        role: str,
        clinic_code: str | None,
    ) -> bool:
        """Send clinician invite email. Returns True on successful API call."""
        if not self.enabled:
            logger.info("Resend invite email skipped: client not configured")
            return False

        query = urlencode(
            {
                "email": to_email,
                "clinic": clinic_name,
                "role": role,
                "code": clinic_code or "",
            }
        )
        join_url = settings.clinician_portal_url.rstrip("/") + "/signup?" + query
        role_label = role.replace("_", " ").title()
        safe_clinic = escape(clinic_name)
        safe_role = escape(role_label)
        safe_code = escape(clinic_code) if clinic_code else None
        clinic_code_row = (
            f"""
            <tr>
              <td style="padding:8px 0;color:#475569;font-size:14px;">Clinic code</td>
              <td style="padding:8px 0;color:#0f172a;font-size:14px;font-weight:700;">{safe_code}</td>
            </tr>
            """
            if safe_code
            else ""
        )

        subject_clinic = " ".join(clinic_name.split())
        subject = f"You're invited to join {subject_clinic} on MediAgent"
        text = (
            f"You've been invited to join {clinic_name} on MediAgent as {role_label}.\n\n"
            + (f"Clinic code: {clinic_code}\n" if clinic_code else "")
            + f"Complete setup: {join_url}\n\n"
            + "If you already have an account, sign in and complete clinic setup in Settings."
        )
        html = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f8fafc;font-family:Inter,Segoe UI,Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="background:#0f172a;color:#f8fafc;padding:20px 24px;font-size:18px;font-weight:700;">
                MediAgent Clinic Invitation
              </td>
            </tr>
            <tr>
              <td style="padding:24px;">
                <p style="margin:0 0 12px;color:#0f172a;font-size:16px;">Hi there,</p>
                <p style="margin:0 0 18px;color:#334155;font-size:15px;line-height:1.6;">
                  You were invited to join <strong>{safe_clinic}</strong> on MediAgent as
                  <strong>{safe_role}</strong>.
                </p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;">
                  <tr>
                    <td style="padding:8px 0;color:#475569;font-size:14px;">Clinic</td>
                    <td style="padding:8px 0;color:#0f172a;font-size:14px;font-weight:700;">{safe_clinic}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;color:#475569;font-size:14px;">Role access</td>
                    <td style="padding:8px 0;color:#0f172a;font-size:14px;font-weight:700;">{safe_role}</td>
                  </tr>
                  {clinic_code_row}
                </table>
                <table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:22px;">
                  <tr>
                    <td style="border-radius:10px;background:#2563eb;">
                      <a href="{join_url}" style="display:inline-block;padding:12px 18px;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;">
                        Complete Setup
                      </a>
                    </td>
                  </tr>
                </table>
                <p style="margin:16px 0 0;color:#64748b;font-size:13px;line-height:1.6;">
                  If you already have an account, sign in and complete clinic setup in Settings.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

        payload: dict[str, Any] = {
            "from": self.clinician_onboarding_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        }

        try:
            resend.Emails.send(cast(Any, payload))
            return True
        except Exception:
            logger.warning("Failed to send clinician invite email via Resend", exc_info=True)
            return False
