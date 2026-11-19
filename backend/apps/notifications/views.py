import uuid

from django.http import Http404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession

from . import services
from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "actor", "read", "created_at"]
        read_only_fields = fields

    def get_actor(self, obj):
        return obj.actor.display_name if obj.actor_id else None

    def get_read(self, obj):
        return obj.read_at is not None


class SettingsSerializer(serializers.Serializer):
    muted = serializers.ListField(child=serializers.ChoiceField(choices=list(services.GROUPS)), max_length=10)
    email_enabled = serializers.BooleanField()


def _settings_payload(user) -> dict:
    from django.conf import settings

    pref = NotificationPreference.objects.filter(user=user).first()
    return {
        "muted": pref.muted if pref else [],
        "email_enabled": bool(pref and pref.email_enabled),
        "email_available": settings.EMAIL_ENABLED,
        "groups": [{"key": k, "label": v, "email": k in services.EMAIL_GROUPS} for k, v in services.GROUPS.items()],
    }


class NotificationViewSet(viewsets.GenericViewSet):
    """A user's own notifications. No role permission is needed: every query is filtered to ``request.user``."""

    permission_classes = [IsAuthenticatedSession]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related("actor")

    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(NotificationSerializer(page, many=True).data)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        try:
            nid = uuid.UUID(str(pk))
        except ValueError:
            raise Http404 from None
        if not self.get_queryset().filter(pk=nid).exists():
            raise Http404
        services.mark_read(request.user, [nid])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        return Response({"marked": services.mark_read(request.user)})

    @action(detail=False, methods=["get", "put"], url_path="settings", url_name="settings")
    def preferences(self, request):
        if request.method == "PUT":
            ser = SettingsSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            NotificationPreference.objects.update_or_create(
                user=request.user,
                defaults={
                    "muted": sorted(set(ser.validated_data["muted"])),
                    "email_enabled": ser.validated_data["email_enabled"],
                },
            )
        return Response(_settings_payload(request.user))
