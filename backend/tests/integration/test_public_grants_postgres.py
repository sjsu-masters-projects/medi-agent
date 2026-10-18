"""Browser roles and public tables, under hosted Supabase's default grants.

The Docker harness gives anon, authenticated and service_role the default privileges hosted
Supabase gives every new object in ``public``. A table that relies on RLS must therefore have
RLS enabled; a table without RLS must have revoked the browser roles' privileges. Migration
070 closed the two tables (clinics, cron_job_runs) this check found. Synthetic only.
"""

import os

import pytest

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check with 070",
)

BROWSER_ROLES = "('anon'),('authenticated')"
API_PRIVILEGES = "('SELECT'),('INSERT'),('UPDATE'),('DELETE')"


def test_hosted_default_grants_are_in_effect_in_the_harness(sql):
    # Guards the harness itself: a table made by a migration-style statement carries the
    # defaults, so the checks below are not passing because nothing was granted.
    sql("CREATE TABLE public.harness_probe(id int);")
    assert (
        sql(
            "SELECT has_table_privilege('anon','public.harness_probe','SELECT')"
            "::text||has_table_privilege('authenticated','public.harness_probe','DELETE')::text"
        )
        == "truetrue"
    )


def test_no_public_table_is_open_to_a_browser_role_without_row_level_security(sql):
    open_tables = sql(f"""SELECT coalesce(string_agg(DISTINCT c.relname||'/'||r.rolname, ', '), '')
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname='public'
      CROSS JOIN (VALUES {BROWSER_ROLES}) r(rolname)
      CROSS JOIN (VALUES {API_PRIVILEGES}) p(privilege)
      WHERE c.relkind IN ('r','p') AND NOT c.relrowsecurity
        AND has_table_privilege(r.rolname, c.oid, p.privilege)""")
    assert open_tables == ""


def test_backend_only_tables_grant_the_browser_roles_nothing(sql):
    granted = sql(f"""SELECT coalesce(string_agg(t.name||'/'||r.rolname||'/'||p.privilege, ', '), '')
      FROM (VALUES ('public.clinics'),('public.cron_job_runs'),('public.message_translations'),
                   ('public.clinic_memberships'),('public.clinic_membership_audit_events'),
                   ('public.authorization_denial_events')) t(name)
      CROSS JOIN (VALUES {BROWSER_ROLES}) r(rolname)
      CROSS JOIN (VALUES {API_PRIVILEGES}) p(privilege)
      WHERE to_regclass(t.name) IS NOT NULL
        AND has_table_privilege(r.rolname, t.name, p.privilege)""")
    # clinic_memberships keeps its documented own-row SELECT for authenticated.
    assert granted in ("", "public.clinic_memberships/authenticated/SELECT")


def test_audit_tables_cannot_be_rewritten_by_a_browser_role(sql):
    rewritable = sql(f"""SELECT coalesce(string_agg(DISTINCT c.relname||'/'||r.rolname, ', '), '')
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname='public'
      CROSS JOIN (VALUES {BROWSER_ROLES}) r(rolname)
      CROSS JOIN (VALUES ('UPDATE'),('DELETE'),('INSERT')) p(privilege)
      WHERE c.relkind='r' AND c.relname ~ '(audit_events|audit_records)$' AND c.relrowsecurity
        AND has_table_privilege(r.rolname, c.oid, p.privilege)
        AND EXISTS (SELECT 1 FROM pg_policies pol WHERE pol.schemaname='public'
                    AND pol.tablename=c.relname AND pol.cmd IN ('INSERT','UPDATE','DELETE','ALL'))""")
    assert rewritable == ""
