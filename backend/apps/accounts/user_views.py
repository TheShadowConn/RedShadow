from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.rbac.viewsets import ScopedModelViewSet

from . import user_services
from .models import User
from .serializers import UserCreateSerializer, UserDeleteSerializer, UserSerializer, UserUpdateSerializer


class UserViewSet(ScopedModelViewSet):
    serializer_class = UserSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "users.view",
        "retrieve": "users.view",
        "create": "users.create",
        "partial_update": "users.update",
        "deactivate": "users.deactivate",
        "reactivate": "users.deactivate",
        "reset_password": "users.update",
        "reset_mfa": "users.update",
        "revoke_sessions": "users.update",
        "destroy": "users.delete",
        "deletion_impact": "users.delete",
    }

    def get_queryset(self):
        qs = User.objects.select_related("role").filter(deleted_at__isnull=True).order_by("email")
        term = self.request.query_params.get("search", "").strip()
        if term:
            qs = qs.filter(email__icontains=term) | qs.filter(display_name__icontains=term)
        return qs

    def create(self, request, *args, **kwargs):
        data = self._validated(UserCreateSerializer, request)
        user, temp = user_services.create_user(request, request.user, data["email"], data["display_name"], data["role"])
        payload = {**UserSerializer(user).data, "temporary_password": temp}
        return Response(payload, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = self._validated(UserUpdateSerializer, request, partial=True)
        user = user_services.update_user(
            request, request.user, self.get_object(), data.get("display_name"), data.get("role")
        )
        return Response(UserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        data = self._validated(UserDeleteSerializer, request)
        result = user_services.delete_user(request, request.user, self.get_object(), data["confirm_email"])
        return Response(result)

    @action(detail=True, methods=["get"], url_path="deletion-impact")
    def deletion_impact(self, request, pk=None):
        return Response(user_services.deletion_impact(self.get_object()))

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return Response(UserSerializer(user_services.deactivate_user(request, request.user, self.get_object())).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        return Response(UserSerializer(user_services.reactivate_user(request, request.user, self.get_object())).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        temp = user_services.reset_password(request, request.user, self.get_object())
        return Response({"temporary_password": temp})

    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request, pk=None):
        return Response(UserSerializer(user_services.reset_mfa(request, request.user, self.get_object())).data)

    @action(detail=True, methods=["post"], url_path="sessions/revoke")
    def revoke_sessions(self, request, pk=None):
        user_services.revoke_sessions(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _validated(serializer_class, request, partial=False) -> dict:
        serializer = serializer_class(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
