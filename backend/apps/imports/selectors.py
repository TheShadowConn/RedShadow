from django.db.models import Q

from apps.engagements.selectors import scope_engagements
from apps.findings.selectors import own_scope_restriction

from .models import ImportJob, ImportMapping


def scope_imports(user):
    """Jobs of engagements where the user holds imports.view. Where the user's finding scope is
    "own" (External Vendor) only their own jobs: rows are finding data of other people."""
    qs = ImportJob.objects.filter(engagement__in=scope_engagements(user, "imports.view")).select_related(
        "engagement", "uploaded_by"
    )
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
