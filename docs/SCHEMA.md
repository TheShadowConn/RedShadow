# Schema: assets, identifiers, imports and user deletion

Covers the tables added or changed on 2026-11-18. The rest of the data model is in [BLUEPRINT.md](BLUEPRINT.md) section 4 and the Django models.
All tables use UUID primary keys and `created_at` / `updated_at` unless noted. Migrations: `organisations/0003` and `0004`, `imports/0002` and `0003`, `accounts/0002`.

## organisations_asset (changed)

| Column | Type | Notes |
|---|---|---|
| organisation_id | FK, PROTECT | unchanged |
| name, type, environment, criticality, tags, archived_at | | unchanged |
| identifier | varchar(500) | **display copy of the primary identifier.** Written only by the service. Older clients and the findings CSV importer still read it. |
| onboarding_status | `onboarded` \| `pending` | default `onboarded`, indexed. Every asset that existed before the change is `onboarded`. |
| origin | `manual` \| `import` | |
| onboarded_at, onboarded_by_id | nullable, SET_NULL | set when onboarded |

Dropped: unique constraint `uniq_asset_org_type_identifier` (identifier uniqueness moved to `AssetIdentifier`).

## organisations_assetidentifier (new)

| Column | Type | Notes |
|---|---|---|
| asset_id | FK, CASCADE | |
| organisation_id | FK, PROTECT | repeats the asset's organisation so the database can enforce uniqueness |
| kind | ip, cidr, hostname, domain, url, mac, cloud_id, repo, package, other | |
| value | varchar(500) | as entered |
| normalized | varchar(500) | canonical form, see ADR-0018 |
| match_key | varchar(520) | `<family>:<normalized>`; hostname and domain share the family `dns` |
| is_primary | bool | |
| source | manual, import, legacy | |

Constraints: `uniq_asset_identifier_org_key` unique (organisation, match_key); `uniq_asset_primary_identifier` unique (asset) where is_primary. Index `assetident_asset`.
Invariants kept by `apps/organisations/assets.py`: an asset has exactly one primary identifier when it has any; an onboarded asset keeps at least one; `Asset.identifier` equals the primary value.

## imports_importjob (changed)

| Column | Notes |
|---|---|
| kind | `findings` (default) or `assets` |
| engagement_id | **now nullable** (findings jobs) |
| organisation_id | new, nullable, PROTECT (assets jobs) |
| attempt | new, default 1: the current upload. Rows of other attempts are history. |

Check constraint `importjob_target_matches_kind`: findings need an engagement and no organisation, assets need an organisation and no engagement. New index `importjob_org_status`.
Row counts (`counts` JSON): findings jobs `total, valid, invalid, duplicate, imported, skipped`; assets jobs add `to_create, to_merge` (after the check) and `created, merged` (after the commit; `imported = created + merged`).

## imports_importrow (changed)

New columns `attempt` (default 1) and `asset_id` (UUID, no foreign key, like `finding_id`). `mapped` of an asset row holds `name, type, environment, criticality, tags, identifiers[], action, asset_id, asset_name, target_line, new_identifiers`. Index `importrow_job_attempt`.

## imports_importattempt (new)

`job_id` (PROTECT), `number` (unique per job), `uploaded_by_id`, `original_name`, `file_sha256`, `file_size`, `counts` (JSON), `outcome` (in_progress, completed, failed, cancelled, superseded), `error`, `finished_at`. The migration gave every existing job attempt 1.

## accounts_user (changed)

New `deleted_at` (nullable, indexed). Set only on an anonymised tombstone; see ADR-0021. The user list and every user endpoint hide rows with `deleted_at`.

## rbac_permission (catalogue additions)

`users.delete`, `assets.delete`, `assets.import`, all platform scope, granted to Super Admin only. Synced by `seed_rbac` after migrate. See [RBAC_PERMISSION_MATRIX.md](RBAC_PERMISSION_MATRIX.md).

## engagements_engagement (changed, 1.3.0)

New `deleted_at` (nullable, indexed) and `deleted_by_id` (nullable, set null). `Engagement.objects` hides soft-deleted rows; `Engagement.all_objects` shows them. Reference numbers are never reused. Migration `engagements/0006`.

## notifications_notification (new, 1.3.0)

`recipient_id` (cascade), `actor_id` (set null), `kind`, `title`, `body`, `link` (in-app path), `engagement_id` (plain UUID), `dedupe_key`, `read_at`, timestamps. Index `(recipient, read_at, -created_at)`. Read rows older than 90 days are pruned daily (`notifications.prune`). Migrations `notifications/0001` to `0003`.

## notifications_notificationpreference (new, 1.3.0)

One row per user who changed settings: `user_id` (one to one, cascade), `muted` (JSON list of group names), `email_enabled` (default false).

## engagements_engagementscenario (new, 1.4.0)

`engagement_id` (cascade), `name` (unique per engagement on `lower(name)`), `description`, `status` (`planned|in_progress|tested|deferred|cancelled`), `status_reason`, `planned_start`, `planned_end` (check: end on or after start), `completed_on`, `position`, `created_by_id`, timestamps. Index `(engagement, status)`.

## files_attachment (changed, 1.4.0)

New kind `scenario_image` and nullable `scenario_id` (protect). The owner check constraint requires a scenario for this kind and none for the others.
