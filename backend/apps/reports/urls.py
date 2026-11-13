from rest_framework.routers import SimpleRouter

from .views import ReportJobViewSet, ReportTemplateViewSet

router = SimpleRouter(trailing_slash=False)
router.register("reports", ReportJobViewSet, basename="report")
router.register("report-templates", ReportTemplateViewSet, basename="report-template")

urlpatterns = router.urls
