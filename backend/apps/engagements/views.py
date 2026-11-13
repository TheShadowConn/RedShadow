import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.files import services as file_services
from apps.files.models import Attachment
from apps.files.serializers import AttachmentSerializer, UploadSerializer
from apps.rbac.authz import has_engagement_perm
from apps.rbac.viewsets import ScopedModelViewSet

from . import selectors, services
from .models import EngagementAsset, EngagementMembership
from .serializers import (
    AssetLinkCreateSerializer,
    AssetLinkUpdateSerializer,
    EngagementAssetSerializer,
    EngagementCreateSerializer,
    EngagementListSerializer,
    EngagementSerializer,
    EngagementUpdateSerializer,
    HistorySerializer,
    MemberCreateSerializer,
    MemberSerializer,
    MemberUpdateSerializer,
    NoteCreateSerializer,
    NoteSerializer,
    StatusSerializer,
    VersionSerializer,
)

ORDERING = {"ref", "name", "start_date", "end_date", "status"}


def _validated(serializer_class, request, partial=False) -> dict:
    serializer = serializer_class(data=request.data, partial=partial, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _uuid_or_404(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        from django.http import Http404

        raise Http404 from None


class EngagementViewSet(ScopedModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "engagements.view",
        "retrieve": "engagements.view",
        "create": "engagements.create",
        "partial_update": "engagements.update",
        "destroy": "engagements.delete",  # engagements are never hard-deleted: answers 405
        "archive": "engagements.archive",
        "unarchive": "engagements.archive",
        "change_status": "engagements.update_status",
        "members": "engagements.view",
        "add_member": "engagements.manage_members",
        "update_member": "engagements.manage_members",
        "remove_member": "engagements.manage_members",
        "assets": "engagements.view",
        "link_asset": "engagements.update",
        "update_asset_link": "engagements.update",
        "unlink_asset": "engagements.update",
        "notes": "engagement_notes.view_shared",
        "add_note": "engagement_notes.create",
        "history": "audit.view_engagement",
        "documents": "documents.view",
        "upload_document": "documents.upload",
    }

    def get_serializer_class(self):
        return EngagementListSerializer if self.action == "list" else EngagementSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    def get_queryset(self):
        qs = selectors.with_overdue(selectors.scope_engagements(self.request.user)).select_related(
            "organisation", "lead"
        )
        if self.action != "list":
            return qs
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("type"):
            qs = qs.filter(type=p["type"])
        if p.get("organisation"):
            qs = qs.filter(organisation_id=p["organisation"]) if _is_uuid(p["organisation"]) else qs.none()
        if p.get("overdue") == "true":
            qs = qs.filter(overdue=True)
        if p.get("archived") != "all":
            qs = qs.filter(archived_at__isnull=(p.get("archived") != "true"))
        term = p.get("search", "").strip()
        if term:
            qs = qs.filter(Q(name__icontains=term) | Q(ref__icontains=term) | Q(organisation__name__icontains=term))
        ordering = p.get("ordering", "-start_date")
        field = ordering.lstrip("-")
        return qs.order_by(ordering, "ref") if field in ORDERING else qs.order_by("-start_date", "ref")

    # core

    def create(self, request, *args, **kwargs):
        eng = services.create_engagement(request, request.user, _validated(EngagementCreateSerializer, request))
        return Response(self._detail(eng), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = _validated(EngagementUpdateSerializer, request, partial=True)
        version = data.pop("version")
        eng = services.update_engagement(request, request.user, self.get_object(), data, version)
        return Response(self._detail(eng))

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE", detail="Engagements are archived, never deleted.")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        data = _validated(VersionSerializer, request)
        return Response(
            self._detail(services.archive_engagement(request, request.user, self.get_object(), data["version"]))
        )

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        data = _validated(VersionSerializer, request)
        return Response(
            self._detail(services.unarchive_engagement(request, request.user, self.get_object(), data["version"]))
        )

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        data = _validated(StatusSerializer, request)
        eng = services.change_status(request, request.user, self.get_object(), data["status"], data["version"])
        return Response(self._detail(eng))

    # members

    @action(detail=True, methods=["get"], url_path="members", pagination_class=None)
    def members(self, request, pk=None):
        eng = self.get_object()
        qs = (
            EngagementMembership.objects.filter(engagement=eng)
            .select_related("user__role", "role_override")
            .order_by("user__display_name")
        )
        return Response(MemberSerializer(qs, many=True).data)

    @members.mapping.post
    def add_member(self, request, pk=None):
        eng = self.get_object()
        data = _validated(MemberCreateSerializer, request)
        member = services.add_member(
            request, request.user, eng, data["user"], data.get("role_override"), data.get("finding_scope", "")
        )
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path=r"members/(?P<user_id>[^/.]+)")
    def update_member(self, request, pk=None, user_id=None):
        eng = self.get_object()
        member = get_object_or_404(
            EngagementMembership.objects.select_related("user__role", "role_override"),
            engagement=eng,
            user_id=_uuid_or_404(user_id),
        )
        data = _validated(MemberUpdateSerializer, request, partial=True)
        return Response(MemberSerializer(services.update_member(request, request.user, eng, member, data)).data)

    @update_member.mapping.delete
    def remove_member(self, request, pk=None, user_id=None):
        eng = self.get_object()
        member = get_object_or_404(
            EngagementMembership.objects.select_related("user__role", "role_override"),
            engagement=eng,
            user_id=_uuid_or_404(user_id),
        )
        services.remove_member(request, request.user, eng, member)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # scope assets

    @action(detail=True, methods=["get"], url_path="assets", pagination_class=None)
    def assets(self, request, pk=None):
        eng = self.get_object()
        if not has_engagement_perm(request.user, eng.pk, "assets.view"):
            raise PermissionDenied("You do not have permission to view assets.")
        qs = EngagementAsset.objects.filter(engagement=eng).select_related("asset").order_by("asset__name")
        return Response(EngagementAssetSerializer(qs, many=True).data)

    @assets.mapping.post
    def link_asset(self, request, pk=None):
        eng = self.get_object()
        data = _validated(AssetLinkCreateSerializer, request)
        link = services.link_asset(request, request.user, eng, data["asset"], data["in_scope"], data.get("notes", ""))
        return Response(EngagementAssetSerializer(link).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path=r"assets/(?P<link_id>[^/.]+)")
    def update_asset_link(self, request, pk=None, link_id=None):
        eng = self.get_object()
        link = get_object_or_404(
            EngagementAsset.objects.select_related("asset"), engagement=eng, pk=_uuid_or_404(link_id)
        )
        data = _validated(AssetLinkUpdateSerializer, request, partial=True)
        return Response(
            EngagementAssetSerializer(services.update_asset_link(request, request.user, eng, link, data)).data
        )

    @update_asset_link.mapping.delete
    def unlink_asset(self, request, pk=None, link_id=None):
        eng = self.get_object()
        link = get_object_or_404(
            EngagementAsset.objects.select_related("asset"), engagement=eng, pk=_uuid_or_404(link_id)
        )
        services.unlink_asset(request, request.user, eng, link)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # notes

    @action(detail=True, methods=["get"], url_path="notes")
    def notes(self, request, pk=None):
        eng = self.get_object()
        page = self.paginate_queryset(selectors.visible_notes(request.user, eng))
        return self.get_paginated_response(NoteSerializer(page, many=True).data)

    @notes.mapping.post
    def add_note(self, request, pk=None):
        eng = self.get_object()
        data = _validated(NoteCreateSerializer, request)
        return Response(
            NoteSerializer(services.add_note(request, request.user, eng, data["body"], data["visibility"])).data,
            status=status.HTTP_201_CREATED,
        )

    # documents

    @action(detail=True, methods=["get"], url_path="documents", parser_classes=[MultiPartParser])
    def documents(self, request, pk=None):
        eng = self.get_object()
        if not has_engagement_perm(request.user, eng.pk, "documents.view"):
            raise PermissionDenied("You do not have permission to view documents.")
        qs = Attachment.objects.filter(engagement=eng, kind="document", deleted_at__isnull=True).select_related(
            "uploaded_by"
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(AttachmentSerializer(page, many=True).data)

    @documents.mapping.post
    def upload_document(self, request, pk=None):
        eng = self.get_object()
        upload = _validated(UploadSerializer, request)["file"]
        att = file_services.upload_document(request, request.user, eng, upload)
        return Response(AttachmentSerializer(att).data, status=status.HTTP_201_CREATED)

    # history (audit events tied to this engagement)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        eng = self.get_object()
        if not has_engagement_perm(request.user, eng.pk, "audit.view_engagement"):
            raise PermissionDenied("You do not have permission to view history.")
        qs = AuditEvent.objects.filter(engagement_id=eng.pk).order_by("-id")
        if not has_engagement_perm(request.user, eng.pk, "findings.view_draft"):
            # draft content, titles and evidence names stay with the testing team
            qs = qs.exclude(entity_type="finding").exclude(metadata__kind="evidence")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(HistorySerializer(page, many=True).data)

    def _detail(self, eng):
        eng = (
            selectors.with_overdue(selectors.scope_engagements(self.request.user))
            .select_related("organisation", "lead")
            .get(pk=eng.pk)
        )
        return EngagementSerializer(eng, context={"request": self.request}).data


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
