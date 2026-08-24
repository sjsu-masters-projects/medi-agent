-- The server-side demo seed validates the committed migration ledger before it
-- changes fixture data. Browser-facing roles receive no access to this table.
GRANT SELECT (filename, checksum) ON TABLE public.schema_migrations TO service_role;
