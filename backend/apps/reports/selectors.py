from apps.engagements.selectors import scope_engagements

from .models import ReportJob


def scope_reports(user):
    """Report jobs of engagements where the user holds reports.view."""
    return ReportJob.objects.filter(engagement__in=scope_engagements(user, "reports.view")).select_related(
        "engagement", "requested_by", "template"
    )
