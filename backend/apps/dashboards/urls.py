from rest_framework.routers import SimpleRouter

from .views import CostReportViewSet, DashboardViewSet

router = SimpleRouter(trailing_slash=False)
router.register("dashboards", DashboardViewSet, basename="dashboard")
router.register("costs", CostReportViewSet, basename="cost-report")

urlpatterns = router.urls
