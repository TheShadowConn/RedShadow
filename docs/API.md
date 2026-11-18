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
| `GET /imports/asset-template.csv` | `imports.view` | Example file for asset imports. |

## Users

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /users/{id}/deletion-impact` | `users.delete` | `{blockers[], removes, clears, history, mode: remove\|anonymise}` |
| `DELETE /users/{id}` | `users.delete` | Body `{confirm_email}`. Account must be deactivated. 403 for yourself, a user with more access, the last active Super Admin. 409 for blockers. Returns `{mode, cleared, history}`. |

## Audit actions added

`asset.created` (now with identifiers), `asset.identifier_added`, `asset.identifier_updated`, `asset.identifier_removed`, `asset.onboarded`, `asset.deleted`, `asset.merged`, `import.reuploaded`, `import.retried`, `import.deleted`, `import.delete_denied`, `import.reupload_denied`, `import.retry_denied`, `user.deleted`, `user.delete_denied`. Asset imports record `import.committed` with `created_not_onboarded`, `merged_into_existing`, `skipped`, `invalid`.
