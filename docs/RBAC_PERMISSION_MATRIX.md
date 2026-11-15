# RBAC permission matrix

Generated from `backend/apps/rbac/catalogue.py` by `manage.py rbac_matrix`. Do not edit by hand.
Scope `platform` = granted by the user's role everywhere. Scope `engagement` = applies on an
engagement the user can reach (all-engagement roles, or membership from Phase 3).

| Permission | Scope | Super Admin | Pentester | Remediation | External Vendor | Description |
|---|---|---|---|---|---|---|
| `users.view` | platform | yes | - | - | - | View users |
| `users.create` | platform | yes | - | - | - | Create users |
| `users.update` | platform | yes | - | - | - | Edit users, reset passwords and MFA, revoke sessions |
| `users.deactivate` | platform | yes | - | - | - | Deactivate and reactivate users |
| `roles.view` | platform | yes | - | - | - | View roles and the permission catalogue |
| `roles.manage` | platform | yes | - | - | - | Create, edit and delete roles |
| `roles.assign` | platform | yes | - | - | - | Assign roles to users |
| `settings.view` | platform | yes | - | - | - | View application settings |
| `settings.manage` | platform | yes | - | - | - | Change application settings |
| `organisations.view` | engagement | yes | yes | yes | yes | View organisations of visible engagements |
| `organisations.create` | platform | yes | - | - | - | Create organisations |
| `organisations.update` | platform | yes | - | - | - | Edit organisations |
| `organisations.archive` | platform | yes | - | - | - | Archive organisations |
| `assets.view` | engagement | yes | yes | yes | yes | View assets |
| `assets.create` | platform | yes | - | - | - | Create assets |
| `assets.update` | platform | yes | - | - | - | Edit assets |
| `assets.archive` | platform | yes | - | - | - | Archive assets |
| `engagements.view` | engagement | yes | yes | yes | yes | View engagements |
| `engagements.create` | platform | yes | - | - | - | Create engagements |
| `engagements.update` | platform | yes | - | - | - | Edit engagement details, scope and dates |
| `engagements.delete` | platform | yes | - | - | - | Delete engagements |
| `engagements.archive` | platform | yes | - | - | - | Archive engagements |
| `engagements.update_status` | engagement | yes | yes | - | - | Change engagement status |
| `engagements.manage_members` | engagement | yes | - | - | - | Manage engagement members |
| `engagements.schedule` | platform | yes | - | - | - | Reschedule engagements on the calendar |
| `engagement_notes.view_team` | engagement | yes | yes | - | - | View team-only engagement notes |
| `engagement_notes.view_shared` | engagement | yes | yes | yes | yes | View shared engagement notes |
| `engagement_notes.create` | engagement | yes | yes | - | - | Create engagement notes |
| `engagement_costs.view` | platform | yes | - | - | - | View engagement costs and the cost totals on the admin dashboard |
| `engagement_costs.manage` | platform | yes | - | - | - | Add, edit and delete engagement cost lines |
| `documents.view` | engagement | yes | yes | yes | yes | View engagement documents |
| `documents.upload` | engagement | yes | yes | - | yes | Upload engagement documents |
| `documents.delete` | engagement | yes | - | - | - | Delete engagement documents |
| `findings.view` | engagement | yes | yes | yes | yes | View findings |
| `findings.view_draft` | engagement | yes | yes | - | yes | View draft findings |
| `findings.create` | engagement | yes | yes | - | yes | Create findings |
| `findings.update` | engagement | yes | yes | - | yes | Edit findings |
| `findings.duplicate` | engagement | yes | yes | - | yes | Mark findings as duplicate |
| `findings.delete` | engagement | yes | - | - | - | Delete findings |
| `findings.assign` | engagement | yes | yes | - | - | Assign pentester and remediation owner |
| `findings.bulk_update` | engagement | yes | yes | - | - | Bulk update findings |
| `findings.publish` | engagement | yes | yes | - | yes | Publish draft findings |
| `findings.verify` | engagement | yes | yes | - | - | Verify remediation (pass or fail) |
| `findings.close` | engagement | yes | yes | - | - | Close findings |
| `findings.reopen` | engagement | yes | yes | - | - | Reopen findings |
| `findings.risk_accept` | engagement | yes | - | - | - | Accept risk on findings |
| `evidence.view` | engagement | yes | yes | yes | yes | View evidence |
| `evidence.upload` | engagement | yes | yes | yes | yes | Upload evidence |
| `evidence.delete_own` | engagement | yes | yes | yes | yes | Delete own evidence |
| `finding_notes.technical` | engagement | yes | yes | - | yes | Write technical (team-only) finding notes |
| `finding_notes.remediation` | engagement | yes | yes | yes | - | Write remediation notes |
| `remediation.update_status` | engagement | yes | yes | yes | - | Move findings between open and in progress |
| `remediation.submit_verification` | engagement | yes | yes | yes | - | Submit findings for verification |
| `retests.view` | engagement | yes | yes | yes | yes | View retest rounds |
| `retests.create` | engagement | yes | yes | - | - | Request retest rounds and choose the assessor |
| `retests.record` | engagement | yes | yes | - | - | Record retest results (only the assigned assessor can) |
| `retests.manage` | engagement | yes | - | - | - | Reassign or cancel any retest round |
| `templates.view` | platform | yes | yes | - | yes | View finding templates |
| `templates.manage` | platform | yes | - | - | - | Manage finding templates |
| `imports.view` | engagement | yes | yes | - | yes | View CSV imports |
| `imports.create` | engagement | yes | yes | - | yes | Run CSV imports |
| `exports.csv` | engagement | yes | yes | yes | yes | Export CSV |
| `reports.view` | engagement | yes | yes | - | - | View generated reports |
| `reports.generate_pdf` | engagement | yes | yes | - | - | Generate PDF reports |
| `reports.manage_templates` | platform | yes | - | - | - | Manage report templates |
| `audit.view_all` | platform | yes | - | - | - | View the full audit log |
| `audit.view_engagement` | engagement | yes | yes | yes | - | View history of visible engagements and findings |
| `audit.verify_integrity` | platform | yes | - | - | - | Verify audit chain integrity |
| `audit.export` | platform | yes | - | - | - | Export the audit log |
| `calendar.view` | engagement | yes | yes | yes | yes | View the engagement calendar |
| `dashboards.admin` | platform | yes | - | - | - | Admin dashboard |
| `dashboards.pentester` | platform | yes | yes | - | - | Pentester dashboard |
| `dashboards.remediation` | platform | yes | - | yes | - | Remediation dashboard |
| `dashboards.vendor` | platform | yes | - | - | yes | External vendor dashboard |

Role flags: Super Admin `all_engagements`, MFA required. Pentester, Remediation and External Vendor
are editable but not deletable. Remediation `finding_scope` defaults to `assigned`
(findings assigned to them).
External Vendor `finding_scope` is `own` (findings they reported or are assigned; own import jobs only).
