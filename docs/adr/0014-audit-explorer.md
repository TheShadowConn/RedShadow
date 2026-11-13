# ADR-0014 Audit explorer, integrity runs and export

Status: accepted (2026-11-13, Phase 6A)

**Decision:** Audit rows are read only through `scope_audit` (Super Admin sees all; others see events of engagements where they hold `audit.view_engagement`, with the same draft, evidence and technical-note hiding as the history tabs). Chain verification runs as a task (nightly and on demand) and each run is stored in `IntegrityCheck`; the banner follows the last finished run. A break is written once per distinct break as `audit.integrity_failed`. Export is Super Admin only, capped at 50,000 events, built in a temporary file, formula-neutralised, and its SHA-256 and filters are written to the audit log.

**Why:** One scoped selector keeps the explorer, facets and export from showing more than the history tabs. Storing runs means a restart or a missed nightly job cannot hide a failure. Returning the CSV directly avoids new file storage; the cap keeps it small.

**Consequences:** Platform events (logins, user and role changes) are visible to Super Admin only. Events are kept forever; retention belongs to Phase 12. A larger export needs narrower filters, or a stored background export if ever required.
