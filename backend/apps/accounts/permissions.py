from rest_framework.permissions import BasePermission

from .session import restriction


class IsAuthenticatedSession(BasePermission):
    """Default permission: signed in AND no pending restriction.

    Views that must work during a restriction (change password, MFA) list the restrictions
    they accept in ``allowed_restrictions``.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        pending = restriction(user, request.auth)
        if pending is None:
            return not getattr(view, "requires_restriction", False)
        return pending in getattr(view, "allowed_restrictions", ())
