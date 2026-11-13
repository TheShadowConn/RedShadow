import time

from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, CSRFCheck
from rest_framework.permissions import SAFE_METHODS

from .models import User
from .session import SessionState


class SessionAuthentication(BaseAuthentication):
    """Server-side session auth. CSRF is enforced on every unsafe request, signed in or not.

    A session is rejected (and destroyed) when the user is inactive or locked, the session
    version no longer matches (role change, password reset, revoke) or the absolute lifetime ended.
    """

    def authenticate(self, request):
        self._enforce_csrf(request)
        session = request.session
        uid = session.get("uid")
        if not uid:
            return None
        if time.time() - session.get("login_at", 0) > settings.SESSION_ABSOLUTE_SECONDS:
            session.flush()
            return None
        user = User.objects.select_related("role").filter(pk=uid).first()
        if user is None or not user.is_active or user.is_locked or user.session_version != session.get("sv"):
            session.flush()
            return None
        return user, SessionState(mfa_verified=bool(session.get("mfa_ok")))

    def authenticate_header(self, request):
        return "Session"

    @staticmethod
    def _enforce_csrf(request):
        if request.method in SAFE_METHODS:
            return
        check = CSRFCheck(lambda r: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF check failed: {reason}")
