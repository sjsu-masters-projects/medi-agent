"""Database dependency — gives routers and services a Supabase client.

Usage in a router:
    from app.db.connection import get_db

    @router.get("/patients")
    async def list_patients(db: Client = Depends(get_db)):
        result = db.table("patients").select("*").execute()
        ...
"""

from supabase import Client

from app.clients.supabase import get_admin_client


def get_db() -> Client:
    """FastAPI dependency — returns the admin Supabase client.

    Why admin? Because routers call services, and services need
    full DB access (RLS is enforced by the DB policies, not the
    application layer). User-scoped queries are already protected
    by the RLS policies we set up in migration 002.
    """
    return get_admin_client()
