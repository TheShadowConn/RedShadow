from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.rbac.views import PermissionViewSet, RoleViewSet

from . import views
from .user_views import UserViewSet

router = SimpleRouter(trailing_slash=False)
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")

auth_patterns = [
    path("csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("login", views.LoginView.as_view(), name="auth-login"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("me", views.MeView.as_view(), name="auth-me"),
    path("sessions/revoke", views.SessionsRevokeView.as_view(), name="auth-sessions-revoke"),
    path("password/change", views.PasswordChangeView.as_view(), name="auth-password-change"),
    path("mfa/setup", views.MfaSetupView.as_view(), name="auth-mfa-setup"),
    path("mfa/confirm", views.MfaConfirmView.as_view(), name="auth-mfa-confirm"),
    path("mfa/verify", views.MfaVerifyView.as_view(), name="auth-mfa-verify"),
]

urlpatterns = [path("auth/", include(auth_patterns)), path("", include(router.urls))]
