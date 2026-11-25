# ADR-0023: engagement scenarios

Status: accepted, 2026-11-25. Section A (backend), Section B (screens and calendar) and the extras (progress, interim report, reminders, clone, bulk add, scenario history, picture viewer, completion guard) are built.

## Context

An engagement often lists several use cases or test scenarios. Some are tested now and others later, sometimes in the next year, all under the same engagement, lead, team and findings.

## Decisions

1. **A scenario is a record inside one engagement** (`EngagementScenario`). It states what is tested and when. It is not a second engagement.
2. **No owner.** The engagement lead owns all the work. A scenario has no lead, tester or assignee field.
3. **Findings belong to the engagement.** There is no link from a finding to a scenario, and findings are imported into the whole engagement.
4. **The name is exactly what the user typed** (trimmed). No generated names or numbers. It is unique per engagement, ignoring case, enforced in the service and by a database constraint on `lower(name)`.
5. **Fields:** `name`, `description`, `status`, `status_reason`, `planned_start`, `planned_end`, `completed_on`, `position`. Dates are optional and a database check keeps the end on or after the start.
6. **Statuses:** `planned`, `in_progress`, `tested`, `deferred`, `cancelled`. Deferring or cancelling needs a reason. Marking `tested` records `completed_on` (default today). Leaving `tested` clears it. A tested or cancelled scenario cannot be rescheduled. A deferred scenario that gets new dates becomes `planned`.
7. **Reschedule, cancel and reorder are separate actions.** Reorder takes the full list of ids of the engagement, so it cannot touch another engagement.
8. **Pictures** are attachments of kind `scenario_image` (new nullable `Attachment.scenario`), images only, at most 10 per scenario, validated and re-encoded by the existing upload pipeline, deleted only through the scenario. They are not listed with engagement documents.
9. **Permissions** are engagement scoped: `engagement_scenarios.view` (Super Admin, Pentester, Remediation, External vendor) and `engagement_scenarios.manage` (Super Admin, Pentester). Existing installs get them through `rbac` migration 0004. Custom roles get nothing until an admin grants it.
10. **Audit:** `engagement.scenario_added`, `scenario_updated`, `scenario_rescheduled`, `scenario_status_changed`, `scenarios_reordered`, plus the existing `attachment.uploaded` and `attachment.deleted` for pictures. All writes lock the engagement row and refuse an archived engagement.
11. **The engagement dates are not changed automatically.** Scenario dates may lie outside the engagement window.
12. **Completion guard.** Moving an engagement to Reporting or Completed while scenarios are planned, in progress or deferred needs `acknowledge_open_scenarios` (the screen asks "Continue anyway"). It is audited. Nothing else blocks the move.
13. **Interim report.** The report has a Test scenarios section. If any scenario is untested it says so and lists each as not yet tested with its planned date. Older templates get the section automatically.
14. **Reminders.** An hourly task notifies the team 3 days before a planned or deferred scenario starts and when a planned or in-progress one is past its planned end, once per scenario and date.
15. **Clone** copies scenarios as planned, without dates or pictures. **Bulk add** takes up to 50 names and is all or nothing.

## Consequences

Calendar and dashboards read scenario dates. Removing a scenario is not offered: cancel it, so the history stays.
