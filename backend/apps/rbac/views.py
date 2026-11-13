from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession

from . import services
from .models import Permission, Role
from .serializers import PermissionSerializer, RoleSerializer, RoleWriteSerializer
from .viewsets import ActionPermission, ScopedModelViewSet


class RoleViewSet(ScopedModelViewSet):
    serializer_class = RoleSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None
    permission_map = {
        "list": "roles.view",
        "retrieve": "roles.view",
        "create": "roles.manage",
        "partial_update": "roles.manage",
        "destroy": "roles.manage",
    }

    def get_queryset(self):
        return Role.objects.prefetch_related("role_permissions").order_by("name")

    def create(self, request, *args, **kwargs):
        data = self._validated(request)
        role = services.create_role(request, request.user, data)
        return Response(self.get_serializer(role).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = self._validated(request, partial=True)
        role = services.update_role(request, request.user, self.get_object(), data)
        return Response(self.get_serializer(self.get_queryset().get(pk=role.pk)).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_role(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _validated(request, partial=False) -> dict:
        serializer = RoleWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class PermissionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only catalogue (seeded by migration)."""

    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {"list": "roles.view"}
    pagination_class = None

    def get_queryset(self):
        return Permission.objects.order_by("module", "code")
