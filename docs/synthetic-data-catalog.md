# Synthetic data catalog

The canonical source is
[synthetic_ca_portal_demo_2026_08.json](../backend/src/app/db/seed/fixtures/synthetic_ca_portal_demo_2026_08.json).
It contains synthetic test data only. The adapter must load it directly and must not
generate clinical facts, names, or timelines outside that source.

## Persisted mapping

| Source record | Existing production tables |
| --- | --- |
| Two synthetic clinics | clinics |
| Eight source staff accounts | clinicians and their Supabase Auth users |
| Eight patient scenarios | patients and their Supabase Auth users |
| Source staff assignments with record access | care_teams; the proxy assignment is not persisted |
| Conditions, allergies, and medication records | conditions, allergies, medications |
| Metadata-only documents | documents with synthetic storage paths and no binary upload |
| Five reviewed portal-message concerns | chat_messages |
| Scheduled appointments | appointments |
| notification_sent events whose source channel is portal_message | notifications only |

The source contains 5 en-US and 3 es-MX patient scenarios. The adapter verifies
that exact split when loading the file.

## Intentionally unpersisted product gaps

The canonical source remains authoritative for these values, but the adapter does not
write them because the production schema and access model cannot represent them safely:

- Notification-channel preferences, delivery/suppression state, quiet hours, and any
  external delivery (sms, email, voice call, or printed mail).
- Authorized proxies, consent, proxy scope, expiration, and proxy access decisions.
- Accessibility and alternate-format metadata, including captioning, interpreter,
  tagged-PDF, large-print, contrast, screen-reader, and reduced-motion requests.
- Fine-grained care-team scope, effective-end windows, break-glass state, and
  source access-audit requirements.
- Exact age-band semantics. The current patients table requires a full date of birth,
  so the adapter uses documented non-clinical compatibility placeholders.
- Declared gender identity, recorded sex, and pronoun detail. The nullable legacy
  `patients.gender` enum cannot represent the source faithfully, so the adapter
  explicitly persists `NULL`; the declared value remains only in the canonical JSON.
- Telephone, unspecified-transport, and front-desk patient concerns. The current
  chat table represents a portal exchange, so only the five reviewed source events
  explicitly identified as portal messages are persisted; their text is not copied
  into any unrelated table.
- Condition onset dates, document page/view state, and adherence events: existing
  tables cannot preserve their source semantics without adding unsupported metadata
  or inventing an adherence target/severity.

These fields are never hidden in free-text notes, user metadata, or synthetic
instructions. No obligations are seeded because the canonical source declares none.

## Operational boundary

The seed command performs a migration-checksum preflight before reset or seed. Reset
requires explicit confirmation, is limited to development/demo/staging, and deletes
only the exact Auth emails derived from canonical synthetic source IDs. Never run it
against production.
