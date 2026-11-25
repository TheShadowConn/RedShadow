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
from apps.rbac.authz import has_engagement_perm, user_permissions
from apps.rbac.viewsets import ScopedModelViewSet

from . import scenarios, selectors, services
from .models import Engagement, EngagementAsset, EngagementCost, EngagementMembership, EngagementScenario
from .serializers import (
    AssetLinkCreateSerializer,
    AssetLinkUpdateSerializer,
    CloneSerializer,
    CostCreateSerializer,
    CostSerializer,
    CostUpdateSerializer,
    DeleteSerializer,
    EngagementAssetSerializer,
    EngagementCreateSerializer,
    EngagementListSerializer,
    EngagementSerializer,
    EngagementUpdateSerializer,
    HistorySerializer,
    LeadSerializer,
    MemberCreateSerializer,
    MemberSerializer,
    MemberUpdateSerializer,
    NoteCreateSerializer,
    NoteSerializer,
    ScenarioBulkSerializer,
    ScenarioCreateSerializer,
    ScenarioOrderSerializer,
    ScenarioRescheduleSerializer,
    ScenarioSerializer,
    ScenarioStatusSerializer,
    ScenarioUpdateSerializer,
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
        "change_lead": "engagements.update",
        "delete_engagement": "engagements.delete",
        "restore": "engagements.delete",
        "clone": "engagements.create",
        "join": "engagements.manage_members",
        "change_status": "engagements.update_status",
        "members": "engagements.view",
        "add_member": "engagements.manage_members",
        "update_member": "engagements.manage_members",
        "remove_member": "engagements.manage_members",
        "assets": "engagements.view",
        "link_asset": "engagements.update",
        "update_asset_link": "engagements.update",
        "unlink_asset": "engagements.update",
        "costs": "engagement_costs.view",
        "add_cost": "engagement_costs.manage",
        "update_cost": "engagement_costs.manage",
        "delete_cost": "engagement_costs.manage",
        "scenarios": "engagement_scenarios.view",
        "add_scenario": "engagement_scenarios.manage",
        "add_scenarios_bulk": "engagement_scenarios.manage",
        "scenario_history": "engagement_scenarios.view",
        "update_scenario": "engagement_scenarios.manage",
        "reschedule_scenario": "engagement_scenarios.manage",
        "scenario_status": "engagement_scenarios.manage",
        "reorder_scenarios": "engagement_scenarios.manage",
        "add_scenario_image": "engagement_scenarios.manage",
        "delete_scenario_image": "engagement_scenarios.manage",
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
        deleted_view = self.action == "restore" or (
            self.action == "list" and self.request.query_params.get("deleted") == "true"
        )
        if deleted_view:
            if "engagements.delete" not in user_permissions(self.request.user):
                return Engagement.all_objects.none()
            deleted = Engagement.all_objects.filter(deleted_at__isnull=False)
            return selectors.with_overdue(deleted).select_related("organisation", "lead").order_by("-deleted_at")
        qs = (
            selectors.with_overdue(selectors.scope_engagements(self.request.user))
            .select_related("organisation", "lead")
            .prefetch_related("scenarios")
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

    @action(detail=True, methods=["post"], url_path="lead")
    def change_lead(self, request, pk=None):
        data = _validated(LeadSerializer, request)
        eng = services.change_lead(request, request.user, self.get_object(), data["lead"], data["version"])
        return Response(self._detail(eng))

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_engagement(self, request, pk=None):
        data = _validated(DeleteSerializer, request)
        services.delete_engagement(
            request, request.user, self.get_object(), data["version"], data["confirm_ref"], data.get("reason", "")
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        data = _validated(CloneSerializer, request)
        eng = services.clone_engagement(request, request.user, self.get_object(), data)
        return Response(self._detail(eng), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        eng = services.restore_engagement(request, request.user, self.get_object())
        return Response(self._detail(eng))

    @action(detail=True, methods=["post"], url_path="join")
    def join(self, request, pk=None):
        member = services.join_engagement(request, request.user, self.get_object())
        return Response(MemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        data = _validated(StatusSerializer, request)
        eng = services.change_status(
            request, request.user, self.get_object(), data["status"], data["version"],
            data["acknowledge_open_scenarios"],
        )
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
        qs = (
            EngagementAsset.objects.filter(engagement=eng)
            .select_related("asset")
            .prefetch_related("asset__identifiers")
            .order_by("asset__name")
        )
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

    # costs

    @action(detail=True, methods=["get"], url_path="costs", pagination_class=None)
    def costs(self, request, pk=None):
        eng = self.get_object()
        lines = EngagementCost.objects.filter(engagement=eng).select_related("created_by")
        totals = selectors.cost_totals(engagement=eng)
        return Response({"totals": totals, "items": CostSerializer(lines, many=True).data})

    @costs.mapping.post
    def add_cost(self, request, pk=None):
        eng = self.get_object()
        data = _validated(CostCreateSerializer, request)
        return Response(CostSerializer(services.add_cost(request, request.user, eng, data)).data,
                        status=status.HTTP_201_CREATED)  # fmt: skip

    @action(detail=True, methods=["patch"], url_path=r"costs/(?P<cost_id>[^/.]+)")
    def update_cost(self, request, pk=None, cost_id=None):
        eng = self.get_object()
        cost = get_object_or_404(EngagementCost, engagement=eng, pk=_uuid_or_404(cost_id))
        data = _validated(CostUpdateSerializer, request, partial=True)
        return Response(CostSerializer(services.update_cost(request, request.user, eng, cost, data)).data)

    @update_cost.mapping.delete
    def delete_cost(self, request, pk=None, cost_id=None):
        eng = self.get_object()
        cost = get_object_or_404(EngagementCost, engagement=eng, pk=_uuid_or_404(cost_id))
        services.delete_cost(request, request.user, eng, cost)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # scenarios

    def _scenario(self, eng, scenario_id):
        return get_object_or_404(EngagementScenario, engagement=eng, pk=_uuid_or_404(scenario_id))

    @action(detail=True, methods=["get"], url_path="scenarios", pagination_class=None)
    def scenarios(self, request, pk=None):
        eng = self.get_object()
        rows = EngagementScenario.objects.filter(engagement=eng).prefetch_related("images")
        return Response(ScenarioSerializer(rows, many=True).data)

    @scenarios.mapping.post
    def add_scenario(self, request, pk=None):
        eng = self.get_object()
        data = _validated(ScenarioCreateSerializer, request)
        sc = scenarios.add_scenario(request, request.user, eng, data)
        return Response(ScenarioSerializer(sc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="scenarios-bulk")
    def add_scenarios_bulk(self, request, pk=None):
        eng = self.get_object()
        names = _validated(ScenarioBulkSerializer, request)["names"]
        made = scenarios.add_scenarios_bulk(request, request.user, eng, names)
        return Response(ScenarioSerializer(made, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)/history")
    def scenario_history(self, request, pk=None, scenario_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        if not has_engagement_perm(request.user, eng.pk, "audit.view_engagement"):
            raise PermissionDenied("You do not have permission to view history.")
        qs = AuditEvent.objects.filter(engagement_id=eng.pk, metadata__scenario_id=str(sc.pk)).order_by("-id")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(HistorySerializer(page, many=True).data)

    @action(detail=True, methods=["post"], url_path="scenario-order")
    def reorder_scenarios(self, request, pk=None):
        eng = self.get_object()
        ids = _validated(ScenarioOrderSerializer, request)["ids"]
        rows = scenarios.reorder_scenarios(request, request.user, eng, ids)
        return Response(ScenarioSerializer(rows, many=True).data)

    @action(detail=True, methods=["patch"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)")
    def update_scenario(self, request, pk=None, scenario_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        data = _validated(ScenarioUpdateSerializer, request, partial=True)
        return Response(ScenarioSerializer(scenarios.update_scenario(request, request.user, eng, sc, data)).data)

    @action(detail=True, methods=["post"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)/reschedule")
    def reschedule_scenario(self, request, pk=None, scenario_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        data = _validated(ScenarioRescheduleSerializer, request)
        return Response(ScenarioSerializer(scenarios.reschedule_scenario(request, request.user, eng, sc, data)).data)

    @action(detail=True, methods=["post"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)/status")
    def scenario_status(self, request, pk=None, scenario_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        data = _validated(ScenarioStatusSerializer, request)
        return Response(ScenarioSerializer(scenarios.change_scenario_status(request, request.user, eng, sc, data)).data)

    @action(detail=True, methods=["post"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)/images",
            parser_classes=[MultiPartParser])
    def add_scenario_image(self, request, pk=None, scenario_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        upload = _validated(UploadSerializer, request)["file"]
        att = file_services.upload_scenario_image(request, request.user, sc, upload)
        return Response(AttachmentSerializer(att).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"scenarios/(?P<scenario_id>[^/.]+)/images/(?P<image_id>[^/.]+)")
    def delete_scenario_image(self, request, pk=None, scenario_id=None, image_id=None):
        eng = self.get_object()
        sc = self._scenario(eng, scenario_id)
        att = get_object_or_404(
            Attachment, scenario=sc, kind="scenario_image", deleted_at__isnull=True, pk=_uuid_or_404(image_id)
        )
        file_services.delete_scenario_image(request, request.user, att)
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
            .prefetch_related("scenarios")
            .get(pk=eng.pk)
        )
        return EngagementSerializer(eng, context={"request": self.request}).data


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
