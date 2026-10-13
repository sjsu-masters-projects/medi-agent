# Symptom question review package

`candidate-1.json` is proposed wording only. No reviewer or approval is claimed.
Use [the paired-locale worksheet](candidate-1-review.md) to read the questions,
record the real decisions and see the subsequent activation steps. It is pending,
not an approval record.
It cannot be selected by the runtime manifest. The safety owner must review the
paired wording, question order, applicability, required fields, budget and any
symptom-specific branches/positive red-flag mappings before activation. The
current proposal has no symptom-specific branch or structured positive mapping;
these remain review decisions, not generated medical rules.

After genuine review, retain the actual reference, reviewer identity/role/date,
immutable bundle version and canonical SHA-256 in `manifest.json`. Rejected or
revoked bundles cannot progress or confirm. A changed bundle requires a new
version; never alter a pinned approved resource. Database eligibility must be
installed/revoked through an explicitly authorized rollout; files alone do not
activate confirmation. Test fixtures bypass runtime loading only through test
injection and do not create an approval manifest.
