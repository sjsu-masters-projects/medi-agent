# Symptom question review package

The requester reports that Ganesh Thampi reviewed and approved `candidate-1.json`
on October 12, 2026. The [paired-locale worksheet](candidate-1-review.md)
records that report and its unchanged canonical hash. The runtime manifest pins
that approval record and selects the bundle. No independently observed reviewer
signature, itemized findings or formal PR approval is asserted. The package has
no symptom-specific branch or structured positive red-flag mapping; those fields
are recorded as reviewed package contents, not generated medical rules.

Retain the actual reference, reviewer identity/role/date,
immutable bundle version and canonical SHA-256 in `manifest.json`. Rejected or
revoked bundles cannot progress or confirm. A changed bundle requires a new
version; never alter a pinned approved resource. Database eligibility must be
installed/revoked through an explicitly authorized rollout; files alone do not
activate confirmation. Test fixtures bypass runtime loading only through test
injection and do not create an approval manifest.
