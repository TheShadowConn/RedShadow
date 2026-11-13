from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.files import services as file_services
from apps.files.serializers import UploadSerializer
from apps.rbac.viewsets import ScopedModelViewSet

from . import selectors, services
from .serializers import (
    AssetCreateSerializer,
    AssetSerializer,
    AssetWriteSerializer,
    ContactCreateSerializer,
    ContactSerializer,
    ContactWriteSerializer,
    OrganisationSerializer,
    OrganisationWriteSerializer,
)


def _validated(serializer_class, request, partial=False) -> dict:
    serializer = serializer_class(data=request.data, partial=partial, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class OrganisationViewSet(ScopedModelViewSet):
    serializer_class = OrganisationSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "organisations.view",
        "retrieve": "organisations.view",
        "create": "organisations.create",
        "partial_update": "organisations.update",
        "archive": "organisations.archive",
        "unarchive": "organisations.archive",
        "assets": "assets.view",
        "contacts": "organisations.view",
        "logo": "organisations.update",
        "remove_logo": "organisations.update",
        "destroy": "organisations.archive",  # never hard-deleted: answers 405
    }

    def get_queryset(self):
        qs = selectors.scope_organisations(self.request.user)
        p = self.request.query_params
        term = p.get("search", "").strip()
        if term:
            qs = qs.filter(Q(name__icontains=term) | Q(industry__icontains=term))
        if self.action == "list":
            if p.get("archived") == "true":
                qs = qs.filter(archived_at__isnull=False)
            elif p.get("archived") != "all":
                qs = qs.filter(archived_at__isnull=True)
        return qs.order_by("name")

    def create(self, request, *args, **kwargs):
        org = services.create_organisation(request, request.user, _validated(OrganisationWriteSerializer, request))
        return Response(OrganisationSerializer(org).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = _validated(OrganisationWriteSerializer, request, partial=True)
        return Response(
            OrganisationSerializer(services.update_organisation(request, request.user, self.get_object(), data)).data
        )

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE", detail="Organisations are archived, never deleted.")

    @action(detail=True, methods=["post"], url_path="logo", parser_classes=[MultiPartParser])
    def logo(self, request, pk=None):
        org = self.get_object()
        upload = _validated(UploadSerializer, request)["file"]
        file_services.set_logo(request, request.user, org, upload)
        return Response(OrganisationSerializer(self.get_queryset().get(pk=org.pk)).data)

    @logo.mapping.delete
    def remove_logo(self, request, pk=None):
        file_services.remove_logo(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return Response(
            OrganisationSerializer(services.archive_organisation(request, request.user, self.get_object())).data
        )

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        return Response(
            OrganisationSerializer(services.unarchive_organisation(request, request.user, self.get_object())).data
        )

    @action(detail=True, methods=["get"], pagination_class=None)
    def assets(self, request, pk=None):
        org = self.get_object()
        qs = selectors.scope_assets(request.user).filter(organisation=org)
        if request.query_params.get("archived") != "all":
            qs = qs.filter(archived_at__isnull=True)
        return Response(AssetSerializer(qs.order_by("name"), many=True).data)

    @action(detail=True, methods=["get"], pagination_class=None)
    def contacts(self, request, pk=None):
        org = self.get_object()
        return Response(ContactSerializer(org.contacts.all(), many=True).data)


class ContactViewSet(ScopedModelViewSet):
    serializer_class = ContactSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "organisations.view",
        "retrieve": "organisations.view",
        "create": "organisations.update",
        "partial_update": "organisations.update",
        "destroy": "organisations.update",
    }

    def get_queryset(self):
        qs = selectors.scope_contacts(self.request.user)
        org = self.request.query_params.get("organisation")
        if org:
            qs = qs.filter(organisation_id=org) if _is_uuid(org) else qs.none()
        return qs.order_by("-is_primary", "name")

    def create(self, request, *args, **kwargs):
        data = _validated(ContactCreateSerializer, request)
        org = data.pop("organisation")
        return Response(
            ContactSerializer(services.create_contact(request, request.user, org, data)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        data = _validated(ContactWriteSerializer, request, partial=True)
        return Response(ContactSerializer(services.update_contact(request, request.user, self.get_object(), data)).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_contact(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssetViewSet(ScopedModelViewSet):
    serializer_class = AssetSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_map = {
        "list": "assets.view",
        "retrieve": "assets.view",
        "create": "assets.create",
        "partial_update": "assets.update",
        "archive": "assets.archive",
        "unarchive": "assets.archive",
    }

    def get_queryset(self):
        qs = selectors.scope_assets(self.request.user)
        p = self.request.query_params
        if p.get("organisation"):
            qs = qs.filter(organisation_id=p["organisation"]) if _is_uuid(p["organisation"]) else qs.none()
        if p.get("type"):
            qs = qs.filter(type=p["type"])
        term = p.get("search", "").strip()
        if term:
            qs = qs.filter(Q(name__icontains=term) | Q(identifier__icontains=term))
        if self.action == "list":
            if p.get("archived") == "true":
                qs = qs.filter(archived_at__isnull=False)
            elif p.get("archived") != "all":
                qs = qs.filter(archived_at__isnull=True)
        return qs.order_by("name")

    def create(self, request, *args, **kwargs):
        data = _validated(AssetCreateSerializer, request)
        org = data.pop("organisation")
        return Response(
            AssetSerializer(services.create_asset(request, request.user, org, data)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        data = _validated(AssetWriteSerializer, request, partial=True)
        return Response(AssetSerializer(services.update_asset(request, request.user, self.get_object(), data)).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return Response(
            AssetSerializer(services.set_asset_archived(request, request.user, self.get_object(), True)).data
        )

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        return Response(
            AssetSerializer(services.set_asset_archived(request, request.user, self.get_object(), False)).data
        )


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
