from rest_framework.routers import SimpleRouter

from .views import ImportJobViewSet, ImportMappingViewSet

router = SimpleRouter(trailing_slash=False)
router.register("imports", ImportJobViewSet, basename="import")
router.register("import-mappings", ImportMappingViewSet, basename="import-mapping")

urlpatterns = router.urls
