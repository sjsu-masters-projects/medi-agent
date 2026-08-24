# Deferred Database Performance Work

Migration `020_harden_database_security.sql` intentionally addresses only
security. The following Supabase advisor findings require workload and query
profile validation before they are changed:

- RLS auth-init-plan warnings: review each policy predicate and replace only
  safe repeated `auth.*` calls with the documented scalar-subquery pattern.
- Unindexed foreign keys: add covering indexes after confirming write volume,
  delete/update paths, and existing composite-index coverage.
- Multiple permissive policies: consolidate only after validating the patient,
  clinician, service-role, and storage access matrices for each table.
- Unused indexes: staging currently has no application data or query history;
  do not drop indexes based on this initial advisor snapshot.

The `vector` extension remains in `public` pending a separate compatibility
review of existing vector types, operators, indexes, functions, and clients.
