# API additions (2026-11-18)

Base path `/api/v1`. Session cookie plus CSRF header, error envelope `{"error": {code, message, fields, request_id}}`, as everywhere else. Each action needs the permission named in the table (platform scope unless noted); object access still goes through the scoped selectors.

## Assets

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /assets` | `assets.view` (engagement scope) | Paged list. Query: `untagged=true` (assets without any tag), `search` (name, identifier, any identifier, tag), `organisation`, `type`, `environment`, `criticality` (1 to 5), `onboarding_status` (`onboarded`, `pending`), `origin`, `archived` (`true` or `all`), `ordering` (`name`, `type`, `criticality`, `created`), `tag` (exact tag, any case), `page`, `page_size`. |
| `GET /assets/summary` | `assets.view` | `{total, onboarded, pending, archived}` for the filter tabs. Optional `organisation`, `tag`, `untagged`. |
| `GET /assets/tags` | `assets.view` (engagement scope) | Tags in use: `[{tag, assets, onboarded, archived}]`, only from assets the caller can see. `assets` and `onboarded` count live assets. Optional `organisation`. |
| `POST /assets/tags/assign` | `assets.update` | `{ids, add?: [...], remove?: [...]}` returns `{updated, skipped: [{id, name, reason}], not_found}`. An added tag takes the spelling already in use. No commas or semicolons, 40 characters, 20 tags per asset. |
| `POST /assets/tags/rename` | `assets.update` | `{tag, new_name, organisation?}` returns `{updated, skipped}`. Renaming onto an existing tag merges them. 404 for an unknown tag. |
| `POST /assets/tags/delete` | `assets.update` | `{tag, organisation?}` returns `{updated, skipped}`. Takes the tag off assets; assets stay. 404 for an unknown tag. |
| `POST /assets` | `assets.create` | Body `{organisation, name, type, environment?, criticality?, tags?, identifiers?: [{kind?, value, is_primary?}], identifier?}`. `kind` is detected when omitted. The older single `identifier` text still works and becomes the primary identifier. 400 with `fields.identifiers` when a value is invalid or belongs to another asset (the message names it). Created assets are onboarded. |
| `GET /assets/{id}` | `assets.view` | Includes `identifiers[]`, `onboarding_status`, `origin`, `engagement_count`. |
| `PATCH /assets/{id}` | `assets.update` | `name, type, environment, criticality, tags`, and the older `identifier` (adds or promotes a primary, never drops identifiers). Identifiers are changed through the endpoints below. |
| `DELETE /assets/{id}` | `assets.delete` | 204. 409 while an engagement or a finding uses the asset (archive or merge instead). Deletes its identifiers. |
| `POST /assets/{id}/archive`, `/unarchive` | `assets.archive` | unchanged |
| `GET /assets/{id}/usage` | `assets.view` | `{engagements, findings, identifiers}` |
| `POST /assets/{id}/identifiers` | `assets.update` | Add `{kind?, value, is_primary?}`. 400 when owned by another asset, 409 when already on this asset. |
| `PATCH /assets/{id}/identifiers/{identifier_id}` | `assets.update` | `{kind?, value?, is_primary?: true}`. Re-normalises and re-checks conflicts. |
| `DELETE /assets/{id}/identifiers/{identifier_id}` | `assets.update` | 409 for the last identifier of an onboarded asset. Another identifier becomes primary. |
| `POST /assets/identifiers/check` | `assets.create` | Dry run `{organisation, asset?, identifiers: [...]}` returns per item `{status: free\|owned\|invalid, normalized, asset?, message?}`. Used by the editor while typing. |
| `POST /assets/{id}/onboard` | `assets.update` | Optional `{name?, type?, environment?, criticality?, tags?}`. 409 without an identifier. Idempotent. |
| `POST /assets/onboard` | `assets.update` | `{ids: [...]}` returns `{onboarded, skipped: [{id, name, reason}], not_found}`. |
| `POST /assets/archive` | `assets.archive` | `{ids, archived}` archives or unarchives several assets: `{changed, skipped: [{id, name, reason}], not_found}`. |
| `POST /assets/{id}/merge` | `assets.delete` | `{source}` (same organisation) folds the source asset into this one: identifiers, engagement links, findings. Deletes the source. |

`GET /engagements/{id}/assets` returns `asset.identifiers[]` (every identifier value). `POST /engagements/{id}/assets` now answers 400 for an asset that is not onboarded.

## Imports

`ImportJob` responses gain `kind`, `organisation`, `engagement` (null for assets), `attempt`, `can_delete`, `can_reupload`, `can_retry`.

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /imports` | `imports.create` | Multipart. Findings: `{engagement, file}`. Assets: `{kind: "assets", organisation, file}` and `assets.import`. |
| `GET /imports` | `imports.view` | New filters `kind`, `organisation`, `search` (file name). Asset jobs are listed only for holders of `assets.import`. |
| `POST /imports/{id}/mapping` | `imports.create` | Asset jobs map asset fields (`name, type, environment, criticality, tags, ip, hostname, domain, url, mac, cloud_id, repo, identifiers`) and need at least one identifier column. |
| `POST /imports/{id}/commit` | `imports.create` | `{mode, duplicates}`. For asset jobs `duplicates` is ignored (known rows are always skipped). |
| `GET /imports/{id}/rows` | `imports.view` | Current attempt; `?attempt=N` for an earlier one; `?status=` filter. Asset rows carry `asset: {action, identifiers[], new_identifiers, type, asset, target_line}`. |
| `GET /imports/{id}/errors.csv` | `imports.view` | Rows left out, with reasons, for the current attempt. |
| `POST /imports/{id}/reupload` | `imports.create` | Multipart `{file}`. Corrected file into the same job as a new attempt. 409 unless the job failed, is waiting, or completed with rows left out. 400 for identical content. |
| `POST /imports/{id}/retry` | `imports.create` | Re-run a failed job with the same file and mapping. 409 when not failed or the file was purged. |
| `DELETE /imports/{id}` | `imports.create` | 204 for a failed or cancelled job. 409 otherwise, and always when it created records. |
| `GET /imports/{id}/history` | `imports.view` | Attempts, newest first: file, checksum, counts, outcome, error. |
| `GET /imports/asset-template.csv` | `imports.view` | Five-column example file: Name, Asset type, Environment, Criticality, Identifiers (several per cell, separated by semicolons; the kind of each is detected). |

## Users

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /users/{id}/deletion-impact` | `users.delete` | `{blockers[], removes, clears, history, mode: remove\|anonymise}` |
| `DELETE /users/{id}` | `users.delete` | Body `{confirm_email}`. Account must be deactivated. 403 for yourself, a user with more access, the last active Super Admin. 409 for blockers. Returns `{mode, cleared, history}`. |

## Audit actions added

`asset.created` (now with identifiers), `asset.identifier_added`, `asset.identifier_updated`, `asset.identifier_removed`, `asset.onboarded`, `asset.deleted`, `asset.merged`, `import.reuploaded`, `import.retried`, `import.deleted`, `import.delete_denied`, `import.reupload_denied`, `import.retry_denied`, `user.deleted`, `user.delete_denied`. Asset imports record `import.committed` with `created_not_onboarded`, `merged_into_existing`, `skipped`, `invalid`.

## Engagement lifecycle (Section A, 2026-11-19)

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /engagements` | `engagements.create` | `lead` is now required (active user). |
| `PATCH /engagements/{id}` | `engagements.update` | `lead` may change but never be null. |
| `POST /engagements/{id}/lead` | `engagements.update` | `{lead, version}`. Super Admin changes the lead at any time while not archived. The new lead joins the team. 409 when already the lead. Audit `engagement.lead_changed`. |
| `POST /engagements/{id}/delete` | `engagements.delete` | `{version, confirm_ref, reason?}`. Soft delete, separate from archive: the engagement and its findings disappear from every scoped read, rows stay in the database. 204. 400 when `confirm_ref` is not the engagement reference. Audit `engagement.deleted` (ref, name, organisation, status, finding count, reason); denial audits `engagement.delete_denied`. `DELETE /engagements/{id}` still answers 405. |
| `POST /engagements/{id}/join` | `engagements.manage_members` | The signed-in user adds themself to the team with their own role. 409 if already a member. Audit `engagement.member_added` with `via: self`. |

New audit actions: `engagement.lead_changed`, `engagement.lead_denied`, `engagement.deleted`, `engagement.delete_denied`.

## Notifications (Section E, 2026-11-19)

Every signed-in user, own rows only (no role permission; queries are filtered to the caller; another user's id answers 404).

| Method and path | Purpose |
|---|---|
| `GET /notifications` | Paginated, newest first. `?unread=true`. Fields `id, kind, title, body, link, actor, read, created_at`. |
| `GET /notifications/unread-count` | `{count}` |
| `POST /notifications/{id}/read` | Mark one read. |
| `POST /notifications/read-all` | `{marked}` |

Created in the same transaction as the change, never for the actor. Kinds: `engagement.added`, `engagement.removed`, `engagement.lead`, `engagement.lead_removed`, `engagement.updated`, `engagement.status`, `engagement.archived`, `engagement.deleted`, `finding.assigned`, `finding.status` (reporter and assignees), `finding.activity`, `retest.assigned`. Team-only technical notes never notify. Notifications carry only a reference and title, and are deleted with their user.

## Release 1.3.0 additions (2026-11-19)

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /engagements?deleted=true` | `engagements.delete` | Deleted engagements (others get an empty list). Rows carry `deleted_at`. |
| `POST /engagements/{id}/restore` | `engagements.delete` | Undo a delete. Findings, team and history return. 409 when the organisation is archived or the engagement is not deleted. Audit `engagement.restored`. |
| `POST /engagements/{id}/clone` | `engagements.create` | `{name, start_date, end_date, lead}`. New Planned engagement with the same organisation, type, text, team and live in-scope assets. Findings, notes, documents and costs are not copied. Audit `engagement.cloned`. |
| `GET` and `PUT /notifications/settings` | any signed-in user | `{muted: [group], email_enabled}`. Groups: `engagement`, `assignments`, `findings`, `deadlines`, `retests`. Response adds `email_available` and `groups[]`. Email is sent only for assignments, deadlines and retests, only when the server has `EMAIL_HOST` set and the user opted in. |
| `POST /auth/sessions/revoke` | any signed-in user | Sign out everywhere: ends every session of the caller, this one included. 204. Audit `user.sessions_revoked`. |
| `GET /users?mfa=missing` or `enabled` | `users.view` | Filter by two-step verification. `missing` lists active users without it. |

`GET /auth/me` adds `session_idle_seconds`. New notification kinds: `finding.due_soon` (finding due within 3 days, once per due date), `finding.overdue` (first breach), `engagement.restored`. A deleted engagement now also hides its findings, evidence, retests and reports from every scoped read.

The OpenAPI schema is generated with `make schema` into `docs/openapi.json` (drf-spectacular, dev-only settings `config.settings.schema`; not part of the runtime image).

## Engagement scenarios (1.4.0, ADR-0023)

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /engagements/{id}/scenarios` | `engagement_scenarios.view` | All scenarios in order, each with `images` and `overdue`. Not paginated. |
| `POST /engagements/{id}/scenarios` | `engagement_scenarios.manage` | `{name, description?, planned_start?, planned_end?}`. 201. Name unique per engagement, ignoring case. Audit `engagement.scenario_added`. |
| `PATCH /engagements/{id}/scenarios/{sid}` | `engagement_scenarios.manage` | `{name?, description?}` only. |
| `POST /engagements/{id}/scenarios/{sid}/reschedule` | `engagement_scenarios.manage` | `{planned_start, planned_end, reason?}` (null clears). A deferred scenario with dates becomes planned. 409 for tested or cancelled. |
| `POST /engagements/{id}/scenarios/{sid}/status` | `engagement_scenarios.manage` | `{status, reason?, completed_on?, planned_start?, planned_end?}`. Reason required for `deferred` and `cancelled`. 409 for a move the rules forbid. |
| `POST /engagements/{id}/scenario-order` | `engagement_scenarios.manage` | `{ids: [every scenario id once]}`. Returns the new order. |
| `POST /engagements/{id}/scenarios/{sid}/images` | `engagement_scenarios.manage` | Multipart `file`. Images only (png, jpeg, gif, webp), at most 10 per scenario. 201. |
| `DELETE /engagements/{id}/scenarios/{sid}/images/{image_id}` | `engagement_scenarios.manage` | 204. Pictures are served by `GET /attachments/{id}/download` for holders of `engagement_scenarios.view`. |

There is no owner field and no scenario link on findings. Archived engagements refuse every write (409).

Added with the scenario extras (1.4.0):

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /engagements/{id}/scenarios-bulk` | `engagement_scenarios.manage` | `{names: [..]}` (1 to 50). One scenario per name, all planned, in order. All or nothing: a name that exists or repeats rejects the batch (400). |
| `GET /engagements/{id}/scenarios/{sid}/history` | `engagement_scenarios.view` and `audit.view_engagement` | Paginated audit events of that scenario (added, edited, rescheduled, status changes, pictures). |
| `GET /calendar/scenarios?start&end` | `calendar.view` and `engagement_scenarios.view` | Dated, non-cancelled scenarios in the window, for engagements the caller sees in the calendar. At most 400 days. |
| `POST /engagements/{id}/status` | `engagements.update_status` | New optional `acknowledge_open_scenarios` (bool). Moving to `reporting` or `completed` while scenarios are planned, in progress or deferred answers 409 unless it is true. The acknowledgement is audited. |

`scenarios` on every engagement (list and detail): counts only, `{total, planned, in_progress, tested, deferred, cancelled, overdue, next_date}`; `total` leaves out cancelled. Cloning an engagement copies its scenarios (name, description, planned, no dates, no pictures, cancelled skipped). Dashboards add a `scenarios` block (`total, tested, in_progress, deferred, overdue, starting_soon`). Reports add a "Test scenarios" section (also inserted into older templates when scenarios exist) that marks the report as interim while scenarios are untested, and embeds up to 3 pictures per scenario. An hourly task `engagements.scenario_reminders` notifies the engagement team (kinds `scenario.due_soon`, `scenario.overdue`, group "Due dates and overdue") once per scenario and date.

Dashboards (Section D, 1.4.0): the `scenarios` block now carries `items`, up to 6 scenarios worth acting on, most urgent first: planned or in-progress ones past their planned end, and planned or deferred ones starting within 7 days. The admin dashboard also lists every deferred scenario. Each item has `id, name, status, planned_start, planned_end, overdue, engagement{id, ref, name}`.

Workflow additions (1.4.0):

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /engagements/{id}/scenario-templates` | `engagement_scenarios.manage` | The starter library: OWASP Top 10 (2021), OWASP API Security Top 10 (2023), OWASP Mobile Top 10 (2024), internal network and cloud starters. Each template lists `items[{index, name, description}]`. The library is code, not database rows. |
| `POST /engagements/{id}/scenario-templates/apply` | `engagement_scenarios.manage` | `{template, items?: [index]}`. Creates the chosen items (all when `items` is omitted) as planned scenarios. Names already present are skipped and returned in `skipped`. 201 `{created, skipped}`. Audit `engagement.scenarios_added` with the template key. |

The hourly reminder task also sends `scenario.deferred_due` (group "Due dates and overdue") to the lead and the members who hold `engagement_scenarios.manage` when a deferred scenario's new start date has arrived; once per scenario and date. The scenario stays deferred until someone plans it again. The Pentester dashboard's `scenarios` block adds `this_week: {from, to, items}` (Monday to Sunday, planned, in-progress and deferred scenarios with dates); it is `null` on the other dashboards.

## Asset tags elsewhere

Tags keep one spelling per organisation: create, edit and import reuse the spelling already in use. `GET /engagements/{id}/assets` returns each asset's `tags`, asset import rows return `asset.tags`, and the asset CSV template has a `Tags` column (semicolon separated).

## Release 1.5.0 additions (2026-11-27)

| Endpoint | Permission | Notes |
|---|---|---|
| `GET /assets/departments` | `assets.view` | `{rows, total, open_statuses}` per tag (`tag: null` is untagged). Optional `organisation`. |
| `GET /findings`, `/findings/export.csv` | as before | New filters `tag` and `untagged=true` (by the asset's tags). |
| `POST /reports` | as before | `filters.tags` limits the report to assets with any of those tags. The CSV has an `asset_tags` column. |
| `POST /imports` | `imports.create` | Also accepts `.nessus` and `.xml` (Nessus, Burp, Nmap), 50 MB. `include_info` keeps informational results. |
| `GET /assets/export.csv` | `exports.csv` | CSV of visible assets with the list's filters. Without access to all engagements, only assets of engagements where the caller may export. Audited as `asset.exported`. |
