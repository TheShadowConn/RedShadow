from rest_framework.routers import SimpleRouter

from .views import AttachmentViewSet

router = SimpleRouter(trailing_slash=False)
router.register("attachments", AttachmentViewSet, basename="attachment")

urlpatterns = router.urls
