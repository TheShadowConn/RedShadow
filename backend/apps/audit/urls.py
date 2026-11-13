from rest_framework.routers import SimpleRouter

from .views import AuditViewSet

router = SimpleRouter(trailing_slash=False)
router.register("audit", AuditViewSet, basename="audit")

urlpatterns = router.urls
