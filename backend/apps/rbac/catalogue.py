"""Single source of truth for the permission catalogue and the default role grants.

Seeded idempotently after every migrate (apps.rbac.seed). docs/RBAC_PERMISSION_MATRIX.md is
generated from this file (`manage.py rbac_matrix`) and checked by a test.
"""

PLATFORM = "platform"
ENGAGEMENT = "engagement"

SUPER_ADMIN = "super_admin"
PENTESTER = "pentester"
REMEDIATION = "remediation"
VENDOR = "external_vendor"

# code -> (scope, description)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "users.view": (PLATFORM, "View users"),
    "users.create": (PLATFORM, "Create users"),
    "users.update": (PLATFORM, "Edit users, reset passwords and MFA, revoke sessions"),
    "users.deactivate": (PLATFORM, "Deactivate and reactivate users"),
    "users.delete": (PLATFORM, "Delete deactivated users (removed, or anonymised when history refers to them)"),
    "roles.view": (PLATFORM, "View roles and the permission catalogue"),
    "roles.manage": (PLATFORM, "Create, edit and delete roles"),
    "roles.assign": (PLATFORM, "Assign roles to users"),
    "settings.view": (PLATFORM, "View application settings"),
    "settings.manage": (PLATFORM, "Change application settings"),
    "organisations.view": (ENGAGEMENT, "View organisations of visible engagements"),
    "organisations.create": (PLATFORM, "Create organisations"),
    "organisations.update": (PLATFORM, "Edit organisations"),
    "organisations.archive": (PLATFORM, "Archive organisations"),
    "assets.view": (ENGAGEMENT, "View assets"),
    "assets.create": (PLATFORM, "Create assets"),
    "assets.update": (PLATFORM, "Edit assets"),
    "assets.archive": (PLATFORM, "Archive assets"),
    "assets.delete": (PLATFORM, "Delete assets that no engagement or finding uses, and merge duplicate assets"),
    "assets.import": (PLATFORM, "Import assets from CSV and onboard imported assets"),
    "engagements.view": (ENGAGEMENT, "View engagements"),
    "engagements.create": (PLATFORM, "Create engagements"),
    "engagements.update": (PLATFORM, "Edit engagement details, scope and dates"),
    "engagements.delete": (PLATFORM, "Delete engagements"),
    "engagements.archive": (PLATFORM, "Archive engagements"),
    "engagements.update_status": (ENGAGEMENT, "Change engagement status"),
    "engagements.manage_members": (ENGAGEMENT, "Manage engagement members"),
    "engagements.schedule": (PLATFORM, "Reschedule engagements on the calendar"),
    "engagement_notes.view_team": (ENGAGEMENT, "View team-only engagement notes"),
    "engagement_notes.view_shared": (ENGAGEMENT, "View shared engagement notes"),
    "engagement_notes.create": (ENGAGEMENT, "Create engagement notes"),
    "engagement_costs.view": (PLATFORM, "View engagement costs and the cost totals on the admin dashboard"),
    "engagement_costs.manage": (PLATFORM, "Add, edit and delete engagement cost lines"),
    "documents.view": (ENGAGEMENT, "View engagement documents"),
    "documents.upload": (ENGAGEMENT, "Upload engagement documents"),
    "documents.delete": (ENGAGEMENT, "Delete engagement documents"),
    "findings.view": (ENGAGEMENT, "View findings"),
    "findings.view_draft": (ENGAGEMENT, "View draft findings"),
    "findings.create": (ENGAGEMENT, "Create findings"),
    "findings.update": (ENGAGEMENT, "Edit findings"),
    "findings.duplicate": (ENGAGEMENT, "Mark findings as duplicate"),
    "findings.delete": (ENGAGEMENT, "Delete findings"),
    "findings.assign": (ENGAGEMENT, "Assign pentester and remediation owner"),
    "findings.bulk_update": (ENGAGEMENT, "Bulk update findings"),
    "findings.publish": (ENGAGEMENT, "Publish draft findings"),
    "findings.verify": (ENGAGEMENT, "Verify remediation (pass or fail)"),
    "findings.close": (ENGAGEMENT, "Close findings"),
    "findings.reopen": (ENGAGEMENT, "Reopen findings"),
    "findings.risk_accept": (ENGAGEMENT, "Accept risk on findings"),
    "evidence.view": (ENGAGEMENT, "View evidence"),
    "evidence.upload": (ENGAGEMENT, "Upload evidence"),
    "evidence.delete_own": (ENGAGEMENT, "Delete own evidence"),
    "finding_notes.technical": (ENGAGEMENT, "Write technical (team-only) finding notes"),
    "finding_notes.remediation": (ENGAGEMENT, "Write remediation notes"),
    "remediation.update_status": (ENGAGEMENT, "Move findings between open and in progress"),
    "remediation.submit_verification": (ENGAGEMENT, "Submit findings for verification"),
    "retests.view": (ENGAGEMENT, "View retest rounds"),
    "retests.create": (ENGAGEMENT, "Request retest rounds and choose the assessor"),
    "retests.record": (ENGAGEMENT, "Record retest results (only the assigned assessor can)"),
    "retests.manage": (ENGAGEMENT, "Reassign or cancel any retest round"),
    "templates.view": (PLATFORM, "View finding templates"),
    "templates.manage": (PLATFORM, "Manage finding templates"),
    "imports.view": (ENGAGEMENT, "View CSV imports"),
    "imports.create": (ENGAGEMENT, "Run CSV imports"),
    "exports.csv": (ENGAGEMENT, "Export CSV"),
    "reports.view": (ENGAGEMENT, "View generated reports"),
    "reports.generate_pdf": (ENGAGEMENT, "Generate PDF reports"),
    "reports.manage_templates": (PLATFORM, "Manage report templates"),
    "audit.view_all": (PLATFORM, "View the full audit log"),
    "audit.view_engagement": (ENGAGEMENT, "View history of visible engagements and findings"),
    "audit.verify_integrity": (PLATFORM, "Verify audit chain integrity"),
    "audit.export": (PLATFORM, "Export the audit log"),
    "calendar.view": (ENGAGEMENT, "View the engagement calendar"),
    "dashboards.admin": (PLATFORM, "Admin dashboard"),
    "dashboards.pentester": (PLATFORM, "Pentester dashboard"),
    "dashboards.remediation": (PLATFORM, "Remediation dashboard"),
    "dashboards.vendor": (PLATFORM, "External vendor dashboard"),
}

_PENTESTER_GRANTS = [
    "organisations.view", "assets.view", "engagements.view", "engagements.update_status",
    "engagement_notes.view_team", "engagement_notes.view_shared", "engagement_notes.create",
    "documents.view", "documents.upload",
    "findings.view", "findings.view_draft", "findings.create", "findings.update",
    "findings.duplicate", "findings.assign", "findings.bulk_update", "findings.publish",
    "findings.verify", "findings.close", "findings.reopen",
    "evidence.view", "evidence.upload", "evidence.delete_own",
    "finding_notes.technical", "finding_notes.remediation",
    "remediation.update_status", "remediation.submit_verification",
    "retests.view", "retests.create", "retests.record",
    "templates.view", "imports.view", "imports.create", "exports.csv",
    "reports.view", "reports.generate_pdf", "audit.view_engagement", "calendar.view",
    "dashboards.pentester",
]  # fmt: skip

_REMEDIATION_GRANTS = [
    "organisations.view", "assets.view", "engagements.view",
    "engagement_notes.view_shared", "documents.view", "findings.view",
    "evidence.view", "evidence.upload", "evidence.delete_own",
    "finding_notes.remediation", "remediation.update_status",
    "remediation.submit_verification", "retests.view", "exports.csv", "audit.view_engagement",
    "calendar.view", "dashboards.remediation",
]  # fmt: skip

# External pentesters. Scope "own": they see only findings they reported or are assigned, and only their
# own import jobs. They publish their own findings but cannot verify, close, reopen, assign or delete.
_VENDOR_GRANTS = [
    "organisations.view", "assets.view", "engagements.view", "engagement_notes.view_shared",
    "documents.view", "documents.upload",
    "findings.view", "findings.view_draft", "findings.create", "findings.update", "findings.duplicate",
    "findings.publish", "evidence.view", "evidence.upload", "evidence.delete_own",
    "finding_notes.technical", "retests.view", "templates.view",
    "imports.view", "imports.create", "exports.csv", "calendar.view", "dashboards.vendor",
]  # fmt: skip

# system_key -> definition. Super Admin permissions are always synced to the full catalogue.
SYSTEM_ROLES = {
    SUPER_ADMIN: {
        "name": "Super Admin",
        "description": "Full administrative access to every engagement.",
        "all_engagements": True,
        "finding_scope": "all",
        "mfa_required": True,
        "grants": list(PERMISSIONS),
    },
    PENTESTER: {
        "name": "Pentester",
        "description": "Works on assigned engagements.",
        "all_engagements": False,
        "finding_scope": "all",
        "mfa_required": False,
        "grants": _PENTESTER_GRANTS,
    },
    REMEDIATION: {
        "name": "Remediation",
        "description": "Fixes findings on authorised engagements.",
        "all_engagements": False,
        "finding_scope": "assigned",
        "mfa_required": False,
        "grants": _REMEDIATION_GRANTS,
    },
    VENDOR: {
        "name": "External Vendor",
        "description": "External pentester: uploads and manages their own findings on assigned engagements.",
        "all_engagements": False,
        "finding_scope": "own",
        "mfa_required": False,
        "grants": _VENDOR_GRANTS,
    },
}

assert all(code in PERMISSIONS for r in SYSTEM_ROLES.values() for code in r["grants"])


def split(code: str) -> tuple[str, str]:
    module, _, action = code.partition(".")
    return module, action


def matrix_markdown() -> str:
    """Markdown table of the catalogue and default grants (docs/RBAC_PERMISSION_MATRIX.md)."""
    lines = [
        "# RBAC permission matrix",
        "",
        "Generated from `backend/apps/rbac/catalogue.py` by `manage.py rbac_matrix`. Do not edit by hand.",
        "Scope `platform` = granted by the user's role everywhere. Scope `engagement` = applies on an",
        "engagement the user can reach (all-engagement roles, or membership from Phase 3).",
        "",
        "| Permission | Scope | Super Admin | Pentester | Remediation | External Vendor | Description |",
        "|---|---|---|---|---|---|---|",
    ]
    for code, (scope, desc) in PERMISSIONS.items():
        cells = ["yes" if code in SYSTEM_ROLES[k]["grants"] else "-" for k in
                 (SUPER_ADMIN, PENTESTER, REMEDIATION, VENDOR)]  # fmt: skip
        lines.append(f"| `{code}` | {scope} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {desc} |")
    lines += [
        "",
        "Role flags: Super Admin `all_engagements`, MFA required. Pentester, Remediation and External Vendor",
        "are editable but not deletable. Remediation `finding_scope` defaults to `assigned`",
        "(findings assigned to them).",
        "External Vendor `finding_scope` is `own` (findings they reported or are assigned; own import jobs only).",
        "",
    ]
    return "\n".join(lines)
