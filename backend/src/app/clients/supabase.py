"""Supabase client factory — lazy-initialized, two access levels.

anon_client:  Uses the anon key. Respects RLS. For user-facing operations
              where the JWT is passed through to Supabase.
admin_client: Uses the service_role key. Bypasses RLS. For backend agents,
              cron jobs, and internal operations that need full access.

Both clients are singletons — created once on first access, reused after.
"""

from __future__ import annotations

from supabase import Client, create_client

from app.config import settings

# ── Module-level singletons ────────────────────────────────
_anon_client: Client | None = None
_admin_client: Client | None = None


def get_anon_client() -> Client:
    """Return the anon (RLS-respecting) Supabase client.

    Use this when forwarding a user's JWT — Supabase will enforce
    row-level security based on the token's claims.
    """
    global _anon_client
    if _anon_client is None:
        _anon_client = create_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )
    return _anon_client


def get_admin_client() -> Client:
    """Return the service-role (RLS-bypassing) Supabase client.

    Use this for backend-initiated operations: agent queries,
    cron jobs, profile creation during signup, etc.

    ⚠️  Never expose this client to the frontend.
    """
    global _admin_client
    if _admin_client is None:
        _admin_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _admin_client
