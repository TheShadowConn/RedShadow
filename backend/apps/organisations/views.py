from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.files import services as file_services
from apps.files.serializers import UploadSerializer
from apps.rbac.viewsets import ScopedModelViewSet

from . import assets, selectors, services
from .models import AssetIdentifier
from .serializers import (
    AssetBulkArchiveSerializer,
    AssetBulkOnboardSerializer,
    AssetCreateSerializer,
    AssetIdentifierSerializer,
    AssetMergeSerializer,
    AssetOnboardSerializer,
    AssetSerializer,
    AssetWriteSerializer,
    ContactCreateSerializer,
    ContactSerializer,
    ContactWriteSerializer,
    IdentifierCheckSerializer,
    IdentifierInputSerializer,
    IdentifierPatchSerializer,
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
        qs = selectors.scope_assets(request.user).filter(organisation=org).prefetch_related("identifiers")
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
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "assets.view",
        "retrieve": "assets.view",
        "summary": "assets.view",
        "usage": "assets.view",
        "create": "assets.create",
        "check_identifiers": "assets.create",
        "partial_update": "assets.update",
        "identifiers": "assets.update",
        "identifier_detail": "assets.update",
        "onboard": "assets.update",
        "onboard_many": "assets.update",
        "archive_many": "assets.archive",
        "archive": "assets.archive",
        "unarchive": "assets.archive",
        "destroy": "assets.delete",
        "merge": "assets.delete",
    }
    ORDERING = {"name": "name", "type": "type", "criticality": "-criticality", "created": "-created_at"}

    def _base(self):
        return selectors.scope_assets(self.request.user).prefetch_related("identifiers")

    def _filtered(self, qs, p):
        if p.get("organisation"):
            qs = qs.filter(organisation_id=p["organisation"]) if _is_uuid(p["organisation"]) else qs.none()
        for field in ("type", "environment", "onboarding_status", "origin"):
            if p.get(field):
                qs = qs.filter(**{field: p[field]})
        if p.get("criticality", "").isdigit():
            qs = qs.filter(criticality=int(p["criticality"]))
        term = p.get("search", "").strip()
        if term:
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(identifier__icontains=term)
                | Q(identifiers__value__icontains=term)
                | Q(identifiers__normalized__icontains=term.lower())
                | Q(tags__icontains=term)
            ).distinct()
        return qs

    def get_queryset(self):
        qs = self._base().annotate(engagement_count=Count("engagement_assets", distinct=True))
        p = self.request.query_params
        qs = self._filtered(qs, p)
        if self.action == "list":
            if p.get("archived") == "true":
                qs = qs.filter(archived_at__isnull=False)
            elif p.get("archived") != "all":
                qs = qs.filter(archived_at__isnull=True)
        return qs.order_by(self.ORDERING.get(p.get("ordering", ""), "name"), "name")

    def _fresh(self, asset):
        return self.get_queryset().get(pk=asset.pk)

    def create(self, request, *args, **kwargs):
        data = _validated(AssetCreateSerializer, request)
        org = data.pop("organisation")
        asset = services.create_asset(request, request.user, org, data)
        return Response(AssetSerializer(self._fresh(asset)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = _validated(AssetWriteSerializer, request, partial=True)
        asset = services.update_asset(request, request.user, self.get_object(), data)
        return Response(AssetSerializer(self._fresh(asset)).data)

    def destroy(self, request, *args, **kwargs):
        assets.delete_asset(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        asset = services.set_asset_archived(request, request.user, self.get_object(), True)
        return Response(AssetSerializer(self._fresh(asset)).data)

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        asset = services.set_asset_archived(request, request.user, self.get_object(), False)
        return Response(AssetSerializer(self._fresh(asset)).data)

    @action(detail=True, methods=["get"])
    def usage(self, request, pk=None):
        return Response(assets.usage(self.get_object()))

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Counts for the filter tabs, within the organisation filter but ignoring the other filters."""
        p = self.request.query_params
        qs = self._base()
        if p.get("organisation"):
            qs = qs.filter(organisation_id=p["organisation"]) if _is_uuid(p["organisation"]) else qs.none()
        live = qs.filter(archived_at__isnull=True)
        by_status = assets.counts_for(live)
        return Response(
            {
                "total": live.count(),
                "onboarded": by_status.get("onboarded", 0),
                "pending": by_status.get("pending", 0),
                "archived": qs.filter(archived_at__isnull=False).count(),
            }
        )

    @action(detail=True, methods=["post"])
    def identifiers(self, request, pk=None):
        asset = self.get_object()
        row = assets.add_identifier(request, request.user, asset, _validated(IdentifierInputSerializer, request))
        return Response(AssetIdentifierSerializer(row).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"identifiers/(?P<identifier_id>[0-9a-f-]{36})",
        url_name="identifier-detail",
    )
    def identifier_detail(self, request, pk=None, identifier_id=None):
        asset = self.get_object()
        row = get_object_or_404(AssetIdentifier, pk=identifier_id, asset=asset)
        if request.method == "DELETE":
            assets.remove_identifier(request, request.user, row)
            return Response(status=status.HTTP_204_NO_CONTENT)
        row = assets.update_identifier(
            request, request.user, row, _validated(IdentifierPatchSerializer, request, partial=True)
        )
        return Response(AssetIdentifierSerializer(row).data)

    @action(detail=False, methods=["post"], url_path="identifiers/check")
    def check_identifiers(self, request):
        data = _validated(IdentifierCheckSerializer, request)
        exclude = None
        if data.get("asset"):
            exclude = get_object_or_404(selectors.scope_assets(request.user), pk=data["asset"])
        return Response(assets.check(data["organisation"], data["identifiers"], exclude))

    @action(detail=True, methods=["post"])
    def onboard(self, request, pk=None):
        data = _validated(AssetOnboardSerializer, request)
        asset = assets.onboard(request, request.user, self.get_object(), data)
        return Response(AssetSerializer(self._fresh(asset)).data)

    @action(detail=False, methods=["post"], url_path="onboard")
    def onboard_many(self, request):
        ids = _validated(AssetBulkOnboardSerializer, request)["ids"]
        found = list(selectors.scope_assets(request.user).filter(pk__in=ids, archived_at__isnull=True))
        result = assets.onboard_many(request, request.user, found)
        result["not_found"] = len(set(ids)) - len(found)
        return Response(result)

    @action(detail=False, methods=["post"], url_path="archive")
    def archive_many(self, request):
        data = _validated(AssetBulkArchiveSerializer, request)
        found = list(selectors.scope_assets(request.user).filter(pk__in=data["ids"]))
        result = assets.set_archived_many(request, request.user, found, data["archived"])
        result["not_found"] = len(set(data["ids"])) - len(found)
        return Response(result)

    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        target = self.get_object()
        source_id = _validated(AssetMergeSerializer, request)["source"]
        source = get_object_or_404(selectors.scope_assets(request.user), pk=source_id)
        merged = assets.merge_assets(request, request.user, target, source)
        return Response(AssetSerializer(self._fresh(merged)).data)


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
