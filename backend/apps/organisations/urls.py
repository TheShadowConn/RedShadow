from rest_framework.routers import SimpleRouter

from .views import AssetViewSet, ContactViewSet, OrganisationViewSet

router = SimpleRouter(trailing_slash=False)
router.register("organisations", OrganisationViewSet, basename="organisation")
router.register("contacts", ContactViewSet, basename="contact")
router.register("assets", AssetViewSet, basename="asset")

urlpatterns = router.urls
