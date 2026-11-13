# ADR-0016 CSV import: worker states, drafts only, one summary audit event

Status: accepted (2026-11-13, Phase 8)

**Decision:** Imports run as a job with explicit states (uploaded, parsing, parsed, validating, previewed, importing, completed, failed, cancelled), every step in the worker on the `imports` queue. Every row is kept with its mapped values, errors and result. Imported findings are always drafts, created in one transaction in chunks with refs reserved as a block, so any failure rolls back to zero findings. The audit log gets one `import.committed` event per import (counts, first and last ref, file hash), not one per finding.

**Why:** A pentester must review imported text before anyone else sees it, so drafts are the safe default and publishing stays a separate, audited step. Writing tens of thousands of hash-chained audit events inside one transaction would exceed the task time limit; the summary event plus `Finding.import_job` keeps the trail (everything an import created can be listed). Keeping rows makes the error report and the preview possible and nothing silently disappears.

**Consequences:** An imported finding has no per-finding "created" history line until someone edits it; its detail shows where it came from. Uploaded files are deleted after 30 days, rows stay. `ImportRow` references findings by id without a foreign key so the findings and imports apps do not depend on each other cyclically.
