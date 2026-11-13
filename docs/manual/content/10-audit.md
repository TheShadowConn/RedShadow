# Audit and integrity

RedShadow records who did what and when. The audit log is **append-only**: the database refuses updates, deletes and truncation even for the application itself, and every entry is chained to the one before it with a SHA-256 hash.

## What is recorded

- Sign-ins, sign-outs, password and two-step changes.
- Every create, update, archive and status change of users, roles, organisations, assets, engagements and findings.
- Publishing, verification, retests, closing, reopening and risk acceptance.
- Evidence uploads and downloads, imports and report downloads.
- **Refusals**: an attempt that was denied is recorded with the outcome **Denied**.

Note text and passwords are never written to the log. Long text changes are shortened to 500 characters per side to keep the chain small.

## The audit explorer

{SA} Open **Audit**. Platform events such as sign-ins, user changes and role changes are visible to Super Admins only. Other roles with the engagement history right see only events tied to engagements and findings they can see.

![The Audit page with the chain verified](09-audit.png)

### Filters

- **Engagement**, **Anyone** (the person who acted), **All actions**, **All records** (entity type) and **Any outcome** (succeeded, denied, failed).
- **From** and **To** dates.

### Read an entry

Each row shows the time, the person (or "System" for scheduled jobs), the action, the record and the engagement. Select a row to open its detail: the field changes (before and after) and the recorded details such as severity or the reference.

## Verify the chain

Select **Verify now** at the top of the page.

- **Chain intact** with the number of events and the time means no entry was altered or removed.
- A **broken chain** shows a red warning banner at the top of the application for administrators, stays visible until a later run passes, and is recorded once as `audit.integrity_failed`. Each run is stored, so a restart or a missed nightly job cannot hide a failure.
- A nightly job runs the same check by itself.

You can also verify from the command line:

```
docker compose exec backend python manage.py verify_audit
```

> **Important:** If the chain is broken, stop and follow the recovery steps in the runbook (`docs/RUNBOOKS.md`). Compare the database with a backup taken before the incident.

## Export the log

{SA} Select **Export CSV** to download the events that match your filters, up to 50,000 events. Narrow the filters for more. Only Super Admins can export.

## History on engagements and findings

You do not need the Audit page to see history in context.

![The History tab of an engagement](06-history.png)

- **Engagement > History** lists engagement changes, members, notes, status, imports and finding events you may see.
- **Finding > History** lists the changes of one finding. Drafts and technical events stay hidden from people who may not see them.
- The **Timeline** on a finding is the friendly version for the remediation story. The audit log remains the tamper-evident record.

## Who can see what

| Role | Audit access |
|---|---|
| {SA} | The full log, verification and export. |
| {PT} | History of the engagements and findings they can see. |
| {RO} | History of the findings they can see. |
| {EV} | None by default. |
