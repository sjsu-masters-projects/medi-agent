"""
Unit-level conftest — overrides the root conftest for pure unit tests.

This conftest is picked up for all tests/ in the unit directory and
is intentionally minimal — no FastAPI client, no real Supabase settings.
"""
