# ADR-0022: engagement delete, restore, clone and notifications

Status: accepted (release 1.3.0, 2026-11-19)

## Decisions

1. **Delete is a soft delete.** `Engagement.deleted_at` and `deleted_by` hide the engagement through the default manager `Engagement.objects`; `all_objects` is used only by restore and audit. Findings are hidden by `scope_findings` (`engagement__deleted_at__isnull=True`); every other module reads through `scope_engagements`. Rows are never removed, so evidence, history and the append-only audit log stay intact. A hard delete was rejected: findings, evidence files and reports reference the engagement with PROTECT and the audit chain must not lose its subject. Reference numbers are never reused. Restore is Super Admin only and audited.
2. **Archive and delete are separate actions** with separate permissions (`engagements.archive`, `engagements.delete`). Delete needs the typed reference and an optional reason.
3. **Lead is required** at creation and never null afterwards. A Super Admin changes it with `POST /engagements/{id}/lead`.
4. **Notifications are rows, not events.** `notify()` is called inside the transaction of the change, never for the actor, never for inactive users, and carries only a reference and a short title. Team-only technical notes never notify. Recipients are always people already involved (team, assignees, reporter). Own-rows API, no role permission. Polling (60 s, visible tab only) was chosen over websockets to avoid a new service.
5. **Email is opt-in twice**: the server needs `EMAIL_HOST`, and the user must tick it. Only assignments, deadlines and retests are mailed. The SMTP password comes from a file, never from `.env`. Failures are swallowed.
6. **Schema generation is a dev tool.** drf-spectacular lives in `requirements-dev.txt` and `config.settings.schema`; the production image does not contain it and exposes no schema endpoint.

## Consequences

Deleted engagements are invisible everywhere except the Deleted view and the audit log. Any new module that joins engagements must use the scoped selectors. Notification rows grow until the daily prune removes read rows older than 90 days.
