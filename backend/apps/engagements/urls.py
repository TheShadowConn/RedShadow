from rest_framework.routers import SimpleRouter

from .scheduling_views import CalendarViewSet
from .views import EngagementViewSet

router = SimpleRouter(trailing_slash=False)
router.register("engagements", EngagementViewSet, basename="engagement")
router.register("calendar", CalendarViewSet, basename="calendar")

urlpatterns = router.urls
