# ADR-0012: Engagement scoping and membership

Status: accepted (Phase 3A)

## Decision
- Visibility of engagements, organisations, assets and contacts is decided only by selectors (`apps/engagements/selectors.py`, `apps/organisations/selectors.py`). No view reads `Model.objects` directly.
- A user sees every row when their role has `all_engagements` and the matching view code, or holds any platform write code for that module (a platform code "applies everywhere", so the holder must be able to reach the rows). Everyone else sees only rows reachable through an `EngagementMembership` whose effective role (`role_override` or the user's role) holds the code.
- Organisations, assets and contacts of non-admin users are visible only through engagements they can reach. Assets are visible only when linked to such an engagement.
- `ActionPermission` passes engagement-scoped codes only as a coarse gate (`authz.has_perm_somewhere`). Object access still needs the scoped queryset and, for writes, `has_engagement_perm` on that engagement. Out-of-scope objects are 404; visible but not permitted is 403.
- Foreign keys in request bodies use `ScopedPrimaryKeyField`, so IDs outside the caller's scope are reported as nonexistent.
- Engagements use a `version` column. Every update, status change and archive must send the current version; a stale one is 409.
- Refs `RS-E-YYYY-NNNN` come from a per-year counter row locked with `SELECT ... FOR UPDATE`.
- An engagement asset must belong to the engagement's organisation. Enforced in the service and by a database trigger (migration `engagements/0003`).
- Engagements and organisations are never hard-deleted. Archived records are read-only until unarchived.
- Denials raised inside a service transaction are re-raised after rollback so the `denied` audit event survives (`refusals_audited`).
- Membership changes bump `session_version` of the affected user.

## Consequences
- Adding a module with engagement-bound data means: add a selector, derive from `ScopedModelViewSet`, add the routes to `COVERED_ROUTES`, and add isolation tests.
- A real multi-connection race test is not possible in the test suite: transactional tests flush tables and the database forbids truncating the append-only audit table.
