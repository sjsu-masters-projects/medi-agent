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
- Unused indexes: the original advisor snapshot preceded the populated synthetic
  staging environment. Do not drop indexes based on that stale snapshot; inspect
  current representative query history before proposing a change.

The `vector` extension remains in `public`. Its only user is the retired
`drug_knowledge_chunks` table and `match_drug_knowledge_chunks` function (migrations 015
and 020). Application code no longer reads them. No migration drops them yet, and none is
scheduled: drop the extension together with that table if a cleanup migration is authorized.
