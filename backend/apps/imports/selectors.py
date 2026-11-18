from django.db.models import Q

from apps.engagements.selectors import scope_engagements
from apps.findings.selectors import own_scope_restriction
from apps.rbac.authz import has_platform_perm

from .models import ImportJob, ImportMapping


def scope_imports(user):
    """Jobs of engagements where the user holds imports.view. Where the user's finding scope is
    "own" (External Vendor) only their own jobs: rows are finding data of other people."""
    base = ImportJob.objects.select_related("engagement", "organisation", "uploaded_by")
    qs = base.filter(kind="findings", engagement__in=scope_engagements(user, "imports.view"))
    # Asset imports belong to the organisation, not to an engagement: only holders of assets.import see them.
    if getattr(user, "is_active", False) and has_platform_perm(user, "assets.import"):
        qs = qs | base.filter(kind="assets")
    everywhere, ids = own_scope_restriction(user)
    if everywhere:
        return qs.filter(uploaded_by=user)
    if ids:
        return qs.filter(Q(uploaded_by=user) | ~Q(engagement_id__in=ids))
    return qs


def scope_mappings(user):
    return (
        ImportMapping.objects.filter(owner_id=user.pk)
        if getattr(user, "is_active", False)
        else ImportMapping.objects.none()
    )
