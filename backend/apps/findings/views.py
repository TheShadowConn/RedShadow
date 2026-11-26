import datetime
import uuid

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAuthenticatedSession
from apps.audit import service as audit
from apps.audit.models import AuditEvent
from apps.core.csvout import write_csv
from apps.core.errors import Conflict
from apps.core.pagination import StandardPagination
from apps.engagements.selectors import scope_engagements
from apps.files import services as file_services
from apps.files.models import Attachment
from apps.files.serializers import AttachmentSerializer, UploadSerializer
from apps.rbac.authz import engagement_permissions, has_engagement_perm
from apps.rbac.viewsets import ActionPermission, ScopedModelViewSet

from . import cvss, exports, lifecycle, retests, selectors, services, template_services
from .models import CWE, SEVERITIES, STATUSES, Finding, FindingTemplate, RetestItem, RetestRound
from .serializers import (
    ActivityCreateSerializer,
    ActivitySerializer,
    BulkSerializer,
    CvssSerializer,
    CWESerializer,
    DuplicateSerializer,
    FalsePositiveSerializer,
    FindingCreateSerializer,
    FindingHistorySerializer,
    FindingListSerializer,
    FindingSerializer,
    FindingUpdateSerializer,
    NoteCreateSerializer,
    NoteSerializer,
    QueueFindingSerializer,
    RestoreSerializer,
    RetestAssignSerializer,
    RetestResultSerializer,
    RetestRoundCreateSerializer,
    RetestRoundSerializer,
    TemplateSerializer,
    TemplateUpdateSerializer,
    TemplateWriteSerializer,
    TransitionSerializer,
    VersionSerializer,
)

EXPORT_FILTERS = ("engagement", "status", "severity", "asset", "cwe", "assigned", "from", "to", "search")
ORDERING = {"ref", "title", "status", "discovered_at", "created_at", "updated_at", "cvss_score", "severity"}


def _validated(serializer_class, request, partial=False) -> dict:
    serializer = serializer_class(data=request.data, partial=partial, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _uuids(value: str):
    out = []
    for part in value.split(","):
        try:
            out.append(uuid.UUID(part.strip()))
        except ValueError:
            continue
    return out


class FindingViewSet(ScopedModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "findings.view",
        "retrieve": "findings.view",
        "create": "findings.create",
        "partial_update": "findings.update",
        "destroy": "findings.delete",
        "publish": "findings.publish",
        "import_reviewed": "findings.update",
        "restore": "findings.delete",
        "similar": "findings.view",
        "mark_false_positive": "findings.update",
        "mark_duplicate": "findings.duplicate",
        "transition": "findings.view",  # the rule's own permissions are checked in the service
        "activity": "findings.view",
        "add_activity": "findings.view",  # the action-specific permission is checked in the service
        "history": "audit.view_engagement",
        "bulk": "findings.bulk_update",
        "export": "exports.csv",
        "cvss": "findings.view",
        "notes": "findings.view",
        "add_note": "findings.view",  # the kind-specific permission is checked in the service
        "evidence": "evidence.view",
        "upload_evidence": "evidence.upload",
        "remove_evidence": "evidence.delete_own",
    }

    def get_serializer_class(self):
        return FindingListSerializer if self.action == "list" else FindingSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    def get_queryset(self):
        qs = selectors.scope_findings(self.request.user).select_related(
            "engagement",
            "asset",
            "assigned_pentester",
            "remediation_owner",
            "reported_by",
            "cwe",
            "duplicate_of",
            "import_job",
        )
        if self.action not in ("list", "export"):
            return qs
        p = self.request.query_params
        if p.get("engagement"):
            qs = qs.filter(engagement_id__in=_uuids(p["engagement"]))
        if p.get("status"):
            qs = qs.filter(status__in=[s for s in p["status"].split(",") if s in dict(STATUSES)])
        if p.get("severity"):
            qs = qs.filter(severity__in=[s for s in p["severity"].split(",") if s in dict(SEVERITIES)])
        if p.get("asset"):
            qs = qs.filter(asset_id__in=_uuids(p["asset"]))
        if p.get("cwe", "").isdigit():
            qs = qs.filter(cwe_id=int(p["cwe"]))
        if p.get("assigned") == "me":
            qs = qs.filter(Q(assigned_pentester=self.request.user) | Q(remediation_owner=self.request.user))
        if p.get("needs_review") == "true":
            qs = qs.exclude(import_issues=[])
        if p.get("from"):
            qs = qs.filter(discovered_at__gte=p["from"]) if _is_date(p["from"]) else qs.none()
        if p.get("to"):
            qs = qs.filter(discovered_at__lte=p["to"]) if _is_date(p["to"]) else qs.none()
        term = p.get("search", "").strip()
        if term:
            vector = SearchVector("title", "description", config="english")
            qs = qs.annotate(_fts=vector).filter(
                Q(_fts=SearchQuery(term, config="english", search_type="websearch")) | Q(ref__icontains=term)
            )
        return self._ordered(qs, p.get("ordering", "-severity"))

    @staticmethod
    def _ordered(qs, ordering: str):
        fields = [o for o in ordering.split(",") if o.lstrip("-") in ORDERING] or ["-severity"]
        order = []
        for o in fields:
            key = o.lstrip("-")
            if key == "severity":
                qs = selectors.with_severity_rank(qs)
                order.append(("-" if o.startswith("-") else "") + "severity_rank")
            else:
                order.append(o)
        return qs.order_by(*order, "-created_at", "ref")

    # core

    def create(self, request, *args, **kwargs):
        data = _validated(FindingCreateSerializer, request)
        eng = data["engagement"]
        f = services.create_finding(request, request.user, eng, data)
        return Response(self._detail(f), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = _validated(FindingUpdateSerializer, request, partial=True)
        version = data.pop("version", None)
        if version is None:
            raise ValidationError({"version": ["This field is required."]})
        f = services.update_finding(request, request.user, self.get_object(), data, version)
        return Response(self._detail(f))

    def destroy(self, request, *args, **kwargs):
        services.delete_finding(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="import-reviewed")
    def import_reviewed(self, request, pk=None):
        version = _validated(VersionSerializer, request)["version"]
        return Response(self._detail(services.review_import_issues(request, request.user, self.get_object(), version)))

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        version = _validated(VersionSerializer, request)["version"]
        return Response(self._detail(services.publish_finding(request, request.user, self.get_object(), version)))

    @action(detail=True, methods=["post"], url_path="false-positive")
    def mark_false_positive(self, request, pk=None):
        data = _validated(FalsePositiveSerializer, request)
        f = services.mark_false_positive(request, request.user, self.get_object(), data["reason"], data["version"])
        return Response(self._detail(f))

    @action(detail=True, methods=["post"], url_path="duplicate")
    def mark_duplicate(self, request, pk=None):
        data = _validated(DuplicateSerializer, request)
        f = services.mark_duplicate(request, request.user, self.get_object(), data["duplicate_of"], data["version"])
        return Response(self._detail(f))

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        data = _validated(TransitionSerializer, request)
        f = services.transition(
            request, request.user, self.get_object(), data["to"], data["version"], note=data.get("note", ""),
            expiry=data.get("risk_accepted_until"), duplicate_of=data.get("duplicate_of"),
        )  # fmt: skip
        return Response(self._detail(f))

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        f = self.get_object()
        page = self.paginate_queryset(f.activities.select_related("actor"))
        return self.get_paginated_response(ActivitySerializer(page, many=True).data)

    @activity.mapping.post
    def add_activity(self, request, pk=None):
        f = self.get_object()
        data = _validated(ActivityCreateSerializer, request)
        entry = services.add_activity(
            request, request.user, f, data["action"], data["note"], data.get("evidence_ids", [])
        )
        return Response(ActivitySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        f = self.get_object()
        if not has_engagement_perm(request.user, f.engagement_id, "audit.view_engagement"):
            raise PermissionDenied("You do not have permission to view history.")
        qs = AuditEvent.objects.filter(
            Q(entity_type="finding", entity_id=str(f.pk))
            | Q(entity_type="attachment", metadata__finding_id=str(f.pk), engagement_id=f.engagement_id)
        )
        held = lambda code: has_engagement_perm(request.user, f.engagement_id, code)  # noqa: E731
        if not held("findings.view_draft"):
            published = qs.filter(action="finding.published").order_by("id").values_list("id", flat=True).first()
            qs = qs.filter(id__gte=published) if published else qs.none()
        if not held("finding_notes.technical"):
            qs = qs.exclude(action="finding.technical_note_added")
        page = self.paginate_queryset(qs.order_by("-id"))
        return self.get_paginated_response(FindingHistorySerializer(page, many=True).data)

    # notes

    @action(detail=True, methods=["get"], url_path="notes")
    def notes(self, request, pk=None):
        f = self.get_object()
        page = self.paginate_queryset(selectors.visible_notes(request.user, f))
        return self.get_paginated_response(NoteSerializer(page, many=True).data)

    @notes.mapping.post
    def add_note(self, request, pk=None):
        f = self.get_object()
        data = _validated(NoteCreateSerializer, request)
        note = services.add_note(request, request.user, f, data["kind"], data["body"])
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)

    # evidence

    @action(detail=True, methods=["get"], url_path="evidence", parser_classes=[MultiPartParser])
    def evidence(self, request, pk=None):
        f = self.get_object()
        if not has_engagement_perm(request.user, f.engagement_id, "evidence.view"):
            raise PermissionDenied("You do not have permission to view evidence.")
        qs = Attachment.objects.filter(finding=f, kind="evidence", deleted_at__isnull=True).select_related(
            "uploaded_by"
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(AttachmentSerializer(page, many=True).data)

    @evidence.mapping.post
    def upload_evidence(self, request, pk=None):
        f = self.get_object()
        upload = _validated(UploadSerializer, request)["file"]
        att = file_services.upload_evidence(request, request.user, f, upload)
        return Response(AttachmentSerializer(att).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"evidence/(?P<att_id>[^/.]+)")
    def remove_evidence(self, request, pk=None, att_id=None):
        f = self.get_object()
        att = Attachment.objects.filter(
            finding=f, kind="evidence", deleted_at__isnull=True, pk=att_id if _is_uuid(att_id) else None
        ).first()
        if att is None or not has_engagement_perm(request.user, f.engagement_id, "evidence.view"):
            raise Http404
        file_services.delete_evidence(request, request.user, att)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        data = _validated(BulkSerializer, request)
        params = {k: data[k] for k in ("assigned_pentester", "remediation_owner") if k in data}
        results = services.bulk_apply(request, request.user, data["ids"], data["action"], params)
        ok = sum(1 for r in results if r["ok"])
        return Response({"results": results, "succeeded": ok, "failed": len(results) - ok})

    @action(detail=False, methods=["post"])
    def restore(self, request):
        """Undo a delete (the Undo button): brings deleted findings back. Needs findings.delete on each engagement."""
        data = _validated(RestoreSerializer, request)
        results = services.restore_findings(request, request.user, data["ids"])
        ok = sum(1 for r in results if r["ok"])
        return Response({"results": results, "succeeded": ok, "failed": len(results) - ok})

    @action(detail=False, methods=["get"])
    def similar(self, request):
        """Existing findings that look like the one being written, to warn before a duplicate is created."""
        p = request.query_params
        engagement = _uuids(p.get("engagement", ""))
        if len(engagement) != 1:
            raise ValidationError({"engagement": ["Choose an engagement."]})
        asset = _uuids(p["asset"]) if p.get("asset") else []
        exclude = _uuids(p["exclude"]) if p.get("exclude") else []
        found = services.similar_findings(request.user, engagement[0], p.get("title", ""), asset[0] if asset else None,
                                          p.get("endpoint", ""), exclude[0] if exclude else None)
        return Response({"results": found})

    @action(detail=False, methods=["get"], url_path="export.csv", url_name="export")
    def export(self, request):
        """CSV of the findings the caller can see, with the list's filters. Needs exports.csv on each engagement."""
        qs = self.get_queryset().filter(engagement__in=scope_engagements(request.user, "exports.csv"))
        total = qs.count()
        if total > exports.MAX_ROWS:
            raise Conflict(f"{total} findings match. Narrow the filters to {exports.MAX_ROWS} or fewer.")
        handle, digest, count = write_csv(exports.COLUMNS, (exports.row(f) for f in qs.iterator(chunk_size=1000)))
        p = request.query_params
        audit.record(
            "finding.exported",
            request=request,
            entity_type="findingexport",
            entity_label="Findings CSV",
            metadata={"rows": count, "sha256": digest, "filters": {k: p[k] for k in EXPORT_FILTERS if p.get(k)}},
        )
        response = FileResponse(handle, content_type="text/csv; charset=utf-8", as_attachment=True,
                                filename=f"redshadow-findings-{timezone.now():%Y%m%d-%H%M%S}.csv")  # fmt: skip
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["post"])
    def cvss(self, request):
        vector = _validated(CvssSerializer, request)["vector"]
        try:
            version, score, severity = cvss.score_vector(vector)
        except cvss.InvalidVector as e:
            raise ValidationError({"vector": [str(e)]}) from None
        return Response({"version": version, "score": str(score), "severity": severity})

    def _detail(self, f: Finding):
        f = self.get_queryset().get(pk=f.pk)
        return FindingSerializer(f, context=self.get_serializer_context()).data


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


class CWEViewSet(ScopedModelViewSet):
    serializer_class = CWESerializer
    http_method_names = ["get", "head", "options"]
    permission_map = {"list": "findings.view", "retrieve": "findings.view"}

    def get_queryset(self):
        qs = CWE.objects.all()
        term = self.request.query_params.get("search", "").strip()
        if term:
            digits = term.lower().removeprefix("cwe-")
            qs = qs.filter(Q(name__icontains=term) | (Q(pk=int(digits)) if digits.isdigit() else Q(pk__in=[])))
        return qs.order_by("id")

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:50], many=True).data)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")


class FindingTemplateViewSet(ScopedModelViewSet):
    """Platform-level library: access is decided by templates.view and templates.manage alone."""

    serializer_class = TemplateSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_map = {
        "list": "templates.view",
        "retrieve": "templates.view",
        "create": "templates.manage",
        "partial_update": "templates.manage",
        "destroy": "templates.manage",
    }

    def get_queryset(self):
        qs = FindingTemplate.objects.select_related("cwe")
        term = self.request.query_params.get("search", "").strip()
        if term:
            qs = qs.filter(Q(name__icontains=term) | Q(title__icontains=term))
        return qs.order_by("name")

    def create(self, request, *args, **kwargs):
        t = template_services.create_template(request, request.user, _validated(TemplateWriteSerializer, request))
        return Response(TemplateSerializer(t).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        data = _validated(TemplateUpdateSerializer, request, partial=True)
        version = data.pop("version", None)
        if version is None:
            raise ValidationError({"version": ["This field is required."]})
        t = template_services.update_template(request, request.user, self.get_object(), data, version)
        return Response(TemplateSerializer(t).data)

    def destroy(self, request, *args, **kwargs):
        template_services.delete_template(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class RetestRoundViewSet(ScopedModelViewSet):
    """Retest rounds. Visible on engagements where the caller holds retests.view, and only when the
    round holds at least one finding the caller may see."""

    serializer_class = RetestRoundSerializer
    http_method_names = ["get", "post", "head", "options"]
    permission_map = {
        "list": "retests.view",
        "retrieve": "retests.view",
        "create": "retests.create",
        "assessors": "retests.create",
        "assign": "retests.view",  # requester or retests.manage is checked in the service
        "cancel": "retests.view",  # requester or retests.manage is checked in the service
        "record_result": "retests.view",  # only the assigned assessor is checked in the service
    }

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    def get_queryset(self):
        user = self.request.user
        qs = (
            RetestRound.objects.filter(
                engagement__in=scope_engagements(user, "retests.view"),
                items__finding__in=selectors.scope_findings(user),
            )
            .select_related("engagement", "requested_by", "assessor")
            .distinct()
        )
        if self.action != "list":
            return qs
        p = self.request.query_params
        if p.get("engagement"):
            qs = qs.filter(engagement_id__in=_uuids(p["engagement"]))
        if p.get("status"):
            qs = qs.filter(status__in=[s for s in p["status"].split(",") if s in dict(RetestRound.STATUSES)])
        if p.get("assessor") == "me":
            qs = qs.filter(assessor=user)
        if p.get("finding") and _is_uuid(p["finding"]):
            qs = qs.filter(items__finding_id=p["finding"])
        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        data = _validated(RetestRoundCreateSerializer, request)
        rnd = retests.create_round(
            request, request.user, data["engagement"], data["assessor"], data["findings"], data.get("note", "")
        )
        return Response(self._detail(rnd), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def assessors(self, request):
        """People who could be the assessor for an engagement: active, on the team, able to record and verify."""
        raw = request.query_params.get("engagement")
        eng = scope_engagements(request.user, "retests.create").filter(pk=raw).first() if _is_uuid(raw) else None
        if eng is None:
            raise Http404
        team = (
            User.objects.filter(is_active=True)
            .filter(Q(role__all_engagements=True) | Q(engagement_memberships__engagement=eng))
            .distinct()
        )
        needed = {"retests.record", "findings.verify"}
        people = [u for u in team if needed <= engagement_permissions(u, eng.pk)]
        return Response([{"id": u.pk, "display_name": u.display_name, "email": u.email} for u in people])

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        rnd = self.get_object()
        data = _validated(RetestAssignSerializer, request)
        rnd = retests.assign_round(request, request.user, rnd, data["assessor"], data["version"])
        return Response(self._detail(rnd))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rnd = self.get_object()
        version = _validated(VersionSerializer, request)["version"]
        return Response(self._detail(retests.cancel_round(request, request.user, rnd, version)))

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_id>[^/.]+)/result")
    def record_result(self, request, pk=None, item_id=None):
        rnd = self.get_object()
        item = RetestItem.objects.filter(pk=item_id if _is_uuid(item_id) else None, round=rnd).first()
        if item is None:
            raise Http404
        data = _validated(RetestResultSerializer, request)
        retests.record_result(
            request, request.user, rnd, item, data["result"], data["note"], data.get("evidence_ids", []),
            data.get("version"),
        )  # fmt: skip
        return Response(self._detail(rnd))

    def _detail(self, rnd):
        return RetestRoundSerializer(self.get_queryset().get(pk=rnd.pk), context=self.get_serializer_context()).data


class QueueViewSet(viewsets.ViewSet):
    """Work queues built on the scoped finding selector, so they never show more than the findings list."""

    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {"remediation": "remediation.update_status", "verification": "findings.verify"}

    def _scoped(self, request, code: str):
        return selectors.scope_findings(request.user).filter(engagement__in=scope_engagements(request.user, code))

    def _respond(self, request, qs, statuses, ordering, with_retests=False):
        p = request.query_params
        qs = qs.select_related("engagement", "asset", "assigned_pentester", "remediation_owner").filter(
            status__in=statuses
        )
        if p.get("engagement"):
            qs = qs.filter(engagement_id__in=_uuids(p["engagement"]))
        if p.get("severity"):
            qs = qs.filter(severity__in=[s for s in p["severity"].split(",") if s in dict(SEVERITIES)])
        if p.get("assigned") == "me":
            qs = qs.filter(Q(assigned_pentester=request.user) | Q(remediation_owner=request.user))
        today = timezone.localdate()
        counts = {s: qs.filter(status=s).count() for s in statuses}
        counts["overdue"] = qs.filter(due_date__lt=today, status__in=lifecycle_overdue()).count()
        if p.get("status"):
            qs = qs.filter(status__in=[s for s in p["status"].split(",") if s in statuses])
        if p.get("overdue") == "true":
            qs = qs.filter(due_date__lt=today, status__in=lifecycle_overdue())
        qs = ordering(selectors.with_severity_rank(qs.annotate(
            overdue_rank=Case(When(due_date__lt=today, status__in=lifecycle_overdue(), then=Value(0)),
                              default=Value(1), output_field=IntegerField())
        )))  # fmt: skip
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        context = {"request": request}
        if with_retests:
            items = RetestItem.objects.filter(
                finding_id__in=[f.pk for f in page], result="pending", round__status__in=RetestRound.ACTIVE
            ).select_related("round__engagement", "round__assessor")
            context["retests"] = {i.finding_id: i for i in items}
        response = paginator.get_paginated_response(QueueFindingSerializer(page, many=True, context=context).data)
        response.data["counts"] = counts
        return response

    @action(detail=False, methods=["get"])
    def remediation(self, request):
        """Findings to fix: overdue first, then nearest due date, then severity."""
        return self._respond(
            request, self._scoped(request, "remediation.update_status"), ["open", "in_progress", "reopened"],
            lambda qs: qs.order_by("overdue_rank", F("due_date").asc(nulls_last=True), "-severity_rank", "ref"),
        )  # fmt: skip

    @action(detail=False, methods=["get"])
    def verification(self, request):
        """Findings waiting for a retest: longest waiting first."""
        return self._respond(
            request, self._scoped(request, "findings.verify"), ["pending_verification"],
            lambda qs: qs.order_by(F("resolved_at").asc(nulls_last=True), "-severity_rank", "ref"),
            with_retests=True,
        )  # fmt: skip


def lifecycle_overdue():
    return lifecycle.OVERDUE_STATUSES
