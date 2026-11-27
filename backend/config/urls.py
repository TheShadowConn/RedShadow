from django.urls import include, path

from apps.core.system_views import SystemViewSet
from apps.core.views import AboutView

urlpatterns = [
    path("api/v1/about", AboutView.as_view(), name="about"),
    path("api/v1/system/overview", SystemViewSet.as_view({"get": "overview"}), name="system-overview"),
    path("api/v1/system/backup", SystemViewSet.as_view({"post": "backup"}), name="system-backup"),
    path("api/v1/system/restore", SystemViewSet.as_view({"post": "restore"}), name="system-restore"),
    path("api/v1/health/", include("apps.core.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.organisations.urls")),
    path("api/v1/", include("apps.engagements.urls")),
    path("api/v1/", include("apps.files.urls")),
    path("api/v1/", include("apps.findings.urls")),
    path("api/v1/", include("apps.audit.urls")),
    path("api/v1/", include("apps.imports.urls")),
    path("api/v1/", include("apps.reports.urls")),
    path("api/v1/", include("apps.dashboards.urls")),
    path("api/v1/", include("apps.notifications.urls")),
]

handler404 = "apps.core.errors.not_found"
handler500 = "apps.core.errors.server_error"
