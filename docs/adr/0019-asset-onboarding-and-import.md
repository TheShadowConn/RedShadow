# ADR-0019 Imported assets are not onboarded; imports match by identifier

Status: accepted (2026-11-18)

**Decision:** `Asset.onboarding_status` is `onboarded` or `pending`. Assets created by hand, and every asset that existed before this change, are onboarded. Assets created by an asset CSV import are `pending` (origin `import`). A pending asset is visible only to people who hold platform permissions (`assets.*`), cannot be linked to an engagement and is not matched by the findings import (which only sees in-scope assets). Onboarding (`POST /assets/{id}/onboard`, or in bulk) needs `assets.update`, checks that the asset has an identifier, can complete type, environment, criticality and tags in the same step, and stamps `onboarded_at` and `onboarded_by`.

The asset import (`ImportJob.kind = "assets"`, one organisation, permission `assets.import`) matches every row to existing assets by identifier through one `Matcher` used by the check and by the commit:

- no identifier known: create a pending asset;
- all known identifiers belong to one asset: add the identifiers it lacks (an existing asset's fields are never overwritten) or, when nothing is new, mark the row a duplicate and skip it;
- identifiers of two different assets, or of an archived asset: the row is an error and nothing is guessed;
- rows of the same file that share an identifier fold into one asset (the matcher keeps an in-file overlay).

The commit runs under the organisation lock and re-matches against live data, so anything changed after the check is caught. `all_or_nothing` rolls everything back on the first problem; `valid_rows_only` records the row as invalid and continues. Re-running the same file creates nothing.

**Why:** Teams receive asset lists from clients before anyone has checked them. Importing them as-is would put unverified systems in scope; keeping them pending gives a review step without blocking the import. Matching by identifier is what stops the same machine appearing twice under an IP address and a hostname.

**Consequences:** `ImportJob.engagement` became nullable and `organisation` was added, with a check constraint that exactly one target fits the kind. Asset jobs are visible only to holders of `assets.import`. Asset imports need `imports.view/create` (coarse gate of the existing import endpoints) and `assets.import`.
