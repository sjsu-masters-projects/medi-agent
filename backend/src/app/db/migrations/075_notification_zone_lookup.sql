-- NOT-001 production fix: notification reads no longer scan the server's time-zone files per row.
-- Re-runnable; 051 stays untouched.
-- private.notification_zone asked pg_catalog.pg_timezone_names for every reminder row.
-- That view reads the time-zone database from disk (about 4 ms in the offline harness,
-- slower on hosted PostgreSQL), so a patient with a few hundred reminders waited seconds for
-- each of the summary, list and action-item reads, which also hold one lock per person.
-- A private lookup of the same names answers from an index; a name that is not in it still
-- falls through to the live view, so the answer for every input is unchanged.
CREATE TABLE IF NOT EXISTS private.timezone_names (name text PRIMARY KEY);
REVOKE ALL ON TABLE private.timezone_names FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE private.timezone_names TO service_role;

INSERT INTO private.timezone_names(name)
  SELECT name FROM pg_catalog.pg_timezone_names ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION private.notification_zone(p_zone text) RETURNS text
LANGUAGE sql STABLE SET search_path='' AS $$
  SELECT CASE
    WHEN EXISTS(SELECT 1 FROM private.timezone_names WHERE name=p_zone) THEN p_zone
    WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=p_zone) THEN p_zone
    ELSE 'UTC' END
$$;

DO $$
BEGIN
  IF (SELECT count(*) FROM private.timezone_names) < (SELECT count(*) FROM pg_catalog.pg_timezone_names) THEN
    RAISE EXCEPTION 'private.timezone_names must hold every server time-zone name';
  END IF;
  IF private.notification_zone('America/Los_Angeles') IS DISTINCT FROM 'America/Los_Angeles'
     OR private.notification_zone('Not/AZone') IS DISTINCT FROM 'UTC'
     OR private.notification_zone(NULL) IS DISTINCT FROM 'UTC' THEN
    RAISE EXCEPTION 'private.notification_zone changed its answers';
  END IF;
  IF pg_catalog.has_table_privilege('anon','private.timezone_names','SELECT')
     OR pg_catalog.has_table_privilege('authenticated','private.timezone_names','SELECT')
     OR pg_catalog.has_table_privilege('authenticated','private.timezone_names','INSERT')
     OR NOT pg_catalog.has_table_privilege('service_role','private.timezone_names','SELECT') THEN
    RAISE EXCEPTION 'private.timezone_names must be readable by the service role only';
  END IF;
END $$;
