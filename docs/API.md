# API additions (2026-11-18)

Base path `/api/v1`. Session cookie plus CSRF header, error envelope `{"error": {code, message, fields, request_id}}`, as everywhere else. Each action needs the permission named in the table (platform scope unless noted); object access still goes through the scoped selectors.

## Assets

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /assets` | `assets.view` (engagement scope) | Paged list. Query: `search` (name, identifier, any identifier, tag), `organisation`, `type`, `environment`, `criticality` (1 to 5), `onboarding_status` (`onboarded`, `pending`), `origin`, `archived` (`true` or `all`), `ordering` (`name`, `type`, `criticality`, `created`), `page`, `page_size`. |
| `GET /assets/summary` | `assets.view` | `{total, onboarded, pending, archived}` for the filter tabs. Optional `organisation`. |
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
