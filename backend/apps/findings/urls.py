from rest_framework.routers import SimpleRouter

from .views import CWEViewSet, FindingTemplateViewSet, FindingViewSet, QueueViewSet, RetestRoundViewSet

router = SimpleRouter(trailing_slash=False)
router.register("findings", FindingViewSet, basename="finding")
router.register("finding-templates", FindingTemplateViewSet, basename="finding-template")
router.register("cwes", CWEViewSet, basename="cwe")
router.register("retest-rounds", RetestRoundViewSet, basename="retest-round")
router.register("queues", QueueViewSet, basename="queue")

urlpatterns = router.urls
