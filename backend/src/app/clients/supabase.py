"""Supabase client factory — lazy-initialized, two access levels.

anon_client:  Uses the anon key. Respects RLS. For user-facing operations
              where the JWT is passed through to Supabase.
admin_client: Uses the service_role key. Bypasses RLS. For backend agents,
              cron jobs, and internal operations that need full access.

Both clients are singletons — created once on first access, reused after.
"""

from __future__ import annotations

from threading import RLock

import httpx
from supabase import Client, create_client
from supabase.client import ClientOptions

from app.config import settings

# ── Module-level singletons ────────────────────────────────
_anon_client: Client | None = None
_admin_client: Client | None = None
_client_lock = RLock()


def _build_httpx_client() -> httpx.Client:
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(10.0, connect=5.0, read=10.0, write=10.0, pool=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )


def _build_client_options() -> ClientOptions:
    return ClientOptions(
        auto_refresh_token=False,
        persist_session=False,
        postgrest_client_timeout=10,
        storage_client_timeout=10,
        function_client_timeout=10,
        httpx_client=_build_httpx_client(),
    )


def _close_client(client: Client | None) -> None:
    if client is None:
        return

    for attr in ("postgrest", "storage"):
        component = getattr(client, attr, None)
        session = getattr(component, "session", None)
        if session is None:
            continue
        try:
            session.close()
        except Exception:
            continue


def create_anon_client() -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=_build_client_options(),
    )


def create_admin_client() -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=_build_client_options(),
    )


def get_anon_client() -> Client:
    """Return the anon (RLS-respecting) Supabase client.

    Use this when forwarding a user's JWT — Supabase will enforce
    row-level security based on the token's claims.
    """
    global _anon_client
    with _client_lock:
        if _anon_client is None:
            _anon_client = create_anon_client()
    return _anon_client


def get_admin_client() -> Client:
    """Return the service-role (RLS-bypassing) Supabase client.

    Use this for backend-initiated operations: agent queries,
    cron jobs, profile creation during signup, etc.

    ⚠️  Never expose this client to the frontend.
    """
    global _admin_client
    with _client_lock:
        if _admin_client is None:
            _admin_client = create_admin_client()
    return _admin_client


def reset_anon_client() -> Client:
    global _anon_client
    with _client_lock:
        _close_client(_anon_client)
        _anon_client = create_anon_client()
        return _anon_client


def reset_admin_client() -> Client:
    global _admin_client
    with _client_lock:
        _close_client(_admin_client)
        _admin_client = create_admin_client()
        return _admin_client


def refresh_client(client: Client) -> Client:
    with _client_lock:
        if client is _admin_client:
            return reset_admin_client()
        if client is _anon_client:
            return reset_anon_client()
    return client
