# ADR-0020 Corrected files go into the same import as a new attempt

Status: accepted (2026-11-18)

**Decision:** An import job can take a corrected file (`POST /imports/{id}/reupload`) while it is failed, parsed, waiting to import, or completed with rows left out. This opens a new attempt on the same job: `ImportJob.attempt` increases, a new `ImportAttempt` record stores the file name, checksum, size, counts and outcome, the new rows carry the attempt number, and rows of earlier attempts stay readable (`GET /imports/{id}/rows?attempt=N`). The previous column mapping is reused when the new file still has those columns, so the file goes straight to the check. Uploading byte-identical content is refused. `POST /imports/{id}/retry` re-runs a failed job from where it stopped with the same file (re-read, re-check, or back to the preview). `DELETE /imports/{id}` removes a failed or cancelled job with its rows, attempts and file; a job that created findings or assets is never deleted.

Duplicate safety comes from matching, not from remembering what was imported: findings are matched by their dedupe hash inside the engagement, assets by identifier inside the organisation. A corrected file that contains rows that already went in recognises them as duplicates and skips them, so a partial failure is repaired by fixing the file and uploading it again.

**Why:** Users fix a spreadsheet and upload again. Opening a second job loses the connection with the first one's errors and mapping. Matching makes re-running safe even when a user uploads overlapping files by mistake.

**Consequences:** Every query that reads rows of a job uses `ImportJob.rows_now` (current attempt). Existing jobs were given attempt 1 and one history record by the migration. Failed commits already rolled back, so deletion never needs to undo records.
