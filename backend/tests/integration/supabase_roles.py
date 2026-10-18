"""Roles and default privileges that the disposable PostgreSQL harnesses share.

Hosted Supabase gives the API roles broad default privileges on every object a migration
creates in ``public``. A harness with plain ``CREATE ROLE`` hides a table that forgot its
REVOKE, so every Docker suite starts from the hosted defaults and the migrations must take
access away where they intend to. ``private`` and ``auth`` get no defaults, as on Supabase.
"""

from __future__ import annotations

HOSTED_DEFAULT_GRANTS = """
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
"""


# Default privileges belong to one database, and several suites create a fresh database per test
# from template1, so the grants are set in the connected database and in template1.
HOSTED_DEFAULT_GRANTS_EVERYWHERE = (
    "SELECT current_database() AS harness_db \\gset\n"
    + HOSTED_DEFAULT_GRANTS
    + "\\connect template1\n"
    + HOSTED_DEFAULT_GRANTS
    + "\\connect :harness_db\n"
)


def create_roles_sql(*, service_role_bypasses_rls: bool = True) -> str:
    """CREATE ROLE statements for the three API roles, followed by the hosted default grants."""
    service = "service_role BYPASSRLS" if service_role_bypasses_rls else "service_role"
    return f"CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE {service};\n{HOSTED_DEFAULT_GRANTS_EVERYWHERE}"
