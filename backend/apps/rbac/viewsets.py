from django.core.exceptions import ImproperlyConfigured
from rest_framework import viewsets
from rest_framework.permissions import BasePermission

from apps.accounts.permissions import IsAuthenticatedSession

from .authz import has_perm_somewhere, has_platform_perm
from .catalogue import ENGAGEMENT, PERMISSIONS


class ActionPermission(BasePermission):
    """Default deny: an action with no entry in ``view.permission_map`` is refused.

    Platform codes are decided here. Engagement codes only pass the coarse gate here
    (held through role or any membership); the view must then scope the queryset and check
    the code on the specific engagement.
    """

    def has_permission(self, request, view):
        action = getattr(view, "action", None)
        if action is None:
            return True  # HTTP method not served by this viewset: DRF answers 405, nothing is exposed
        code = view.permission_map.get(action)
        if not code:
            return False
        if PERMISSIONS[code][0] == ENGAGEMENT:
            return has_perm_somewhere(request.user, code)
        return has_platform_perm(request.user, code)


class ScopedModelViewSet(viewsets.ModelViewSet):
    """Base for every model viewset. Forces scoped querysets and per-action permissions.

    Subclasses MUST override ``get_queryset`` (starting from a scoped selector) and declare
    ``permission_map = {action: permission_code}``. A meta-test asserts every ModelViewSet
    in the project derives from this class.
    """

    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map: dict[str, str] = {}

    def get_queryset(self):
        raise ImproperlyConfigured(f"{type(self).__name__} must override get_queryset().")
