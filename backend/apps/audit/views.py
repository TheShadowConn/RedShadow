import datetime
import uuid

from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession
from apps.core.errors import Conflict
from apps.engagements.selectors import scope_engagements
from apps.rbac.authz import has_perm_somewhere, has_platform_perm
from apps.rbac.viewsets import ActionPermission

from . import export, service, tasks
from .models import AuditEvent, IntegrityCheck
from .selectors import can_view_all, scope_audit
from .serializers import AuditEventSerializer, IntegrityCheckSerializer

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
STALE_RUN = datetime.timedelta(minutes=30)
FILTERS = ("actor", "engagement", "entity_type", "entity_id", "action", "outcome", "from", "to", "request_id")


class AuditRead(BasePermission):
    """Coarse gate for the explorer: audit.view_all, or audit.view_engagement on some engagement.
    What a caller actually sees is decided by ``scope_audit``."""

    def has_permission(self, request, view):
        return has_platform_perm(request.user, "audit.view_all") or has_perm_somewhere(
            request.user, "audit.view_engagement"
        )


def _uuid(value, name):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationError({name: ["Not a valid id."]}) from None


def _moment(value: str, name: str, end: bool):
    """A date (whole day, UTC) or a full ISO timestamp."""
    try:
        if len(value) == 10:
            day = datetime.date.fromisoformat(value)
            start = datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.UTC)
            return start + datetime.timedelta(days=1) if end else start
        stamp = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError({name: ["Use a date (2026-11-13) or an ISO timestamp."]}) from None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=datetime.UTC)


def filtered(request, qs):
    """Apply the explorer filters to an already scoped queryset."""
    p = request.query_params
    if p.get("actor"):
        qs = qs.filter(actor_id=_uuid(p["actor"], "actor"))
    if p.get("engagement"):
        qs = qs.filter(engagement_id=_uuid(p["engagement"], "engagement"))
    if p.get("entity_type"):
        qs = qs.filter(entity_type=p["entity_type"][:60])
    if p.get("entity_id"):
        qs = qs.filter(entity_id=p["entity_id"][:64])
    if p.get("outcome") in dict(AuditEvent.OUTCOMES):
        qs = qs.filter(outcome=p["outcome"])
    if p.get("request_id"):
        qs = qs.filter(request_id=p["request_id"][:64])
    if p.get("action"):
        q = Q()
        for part in p["action"].split(",")[:10]:
            part = part.strip()[:80]
            if part.endswith("*"):
                q |= Q(action__startswith=part[:-1])
            elif part:
                q |= Q(action=part)
        qs = qs.filter(q)
    if p.get("from"):
        qs = qs.filter(occurred_at__gte=_moment(p["from"], "from", end=False))
    if p.get("to"):
        qs = qs.filter(occurred_at__lt=_moment(p["to"], "to", end=True))
    return qs


class AuditViewSet(viewsets.ViewSet):
    """Audit explorer, integrity and export. Reads go through ``scope_audit``; the rest are Super Admin only."""

    permission_map = {"verify": "audit.verify_integrity", "integrity": "audit.verify_integrity",
                      "export": "audit.export"}  # fmt: skip

    def get_permissions(self):
        if getattr(self, "action", None) in ("events", "event", "facets"):
            return [IsAuthenticatedSession(), AuditRead()]
        return [IsAuthenticatedSession(), ActionPermission()]

    # explorer

    @action(detail=False, methods=["get"], url_path="events")
    def events(self, request):
        qs = filtered(request, scope_audit(request.user))
        before = request.query_params.get("before", "")
        if before:
            if not before.isdigit():
                raise ValidationError({"before": ["Not a valid cursor."]})
            qs = qs.filter(id__lt=int(before))
        size = request.query_params.get("page_size", "")
        size = min(int(size), MAX_PAGE_SIZE) if size.isdigit() and int(size) > 0 else PAGE_SIZE
        rows = list(qs.order_by("-id")[: size + 1])
        more = len(rows) > size
        rows = rows[:size]
        data = AuditEventSerializer(rows, many=True, context={"full": can_view_all(request.user)}).data
        return Response({"results": data, "has_more": more, "next_before": rows[-1].id if more else None})

    @action(detail=False, methods=["get"], url_path=r"events/(?P<event_id>[0-9]+)")
    def event(self, request, event_id=None):
        row = scope_audit(request.user).filter(pk=int(event_id)).first()
        if row is None:
            raise Http404
        return Response(AuditEventSerializer(row, context={"full": can_view_all(request.user)}).data)

    @action(detail=False, methods=["get"])
    def facets(self, request):
        """Values for the filter drop-downs, limited to what the caller can see."""
        scoped = scope_audit(request.user)
        actions = list(scoped.order_by().values_list("action", flat=True).distinct()[:300])
        types = list(scoped.exclude(entity_type="").order_by().values_list("entity_type", flat=True).distinct()[:100])
        people = scoped.exclude(actor_id=None).order_by().values_list("actor_id", "actor_label").distinct()[:300]
        actors = [{"id": a, "label": label} for a, label in people]
        engagements = [
            {"id": e.pk, "ref": e.ref, "name": e.name}
            for e in scope_engagements(request.user, "audit.view_engagement").order_by("ref")[:300]
        ]
        return Response({"actions": sorted(actions), "entity_types": sorted(types), "actors": actors,
                         "engagements": engagements, "outcomes": [k for k, _ in AuditEvent.OUTCOMES]})  # fmt: skip

    # integrity

    @action(detail=False, methods=["post"])
    def verify(self, request):
        """Start a chain verification. One run at a time: a recent unfinished run is returned instead."""
        running = IntegrityCheck.objects.filter(status="running", started_at__gte=timezone.now() - STALE_RUN).first()
        if running is not None:
            return Response(IntegrityCheckSerializer(running).data, status=status.HTTP_202_ACCEPTED)
        IntegrityCheck.objects.filter(status="running").update(status="error", reason="Run did not finish.")
        check = IntegrityCheck.objects.create(trigger="manual", requested_by_label=request.user.email)
        service.record("audit.verify_requested", request=request, entity=check, entity_label="Audit chain check")
        tasks.verify_integrity.delay(check.pk, "manual")
        check.refresh_from_db()
        return Response(IntegrityCheckSerializer(check).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["get"])
    def integrity(self, request):
        """Latest runs: the newest, and the newest that finished (the banner follows the latter)."""
        newest = IntegrityCheck.objects.first()
        finished = IntegrityCheck.objects.exclude(status="running").first()
        return Response({
            "latest": IntegrityCheckSerializer(newest).data if newest else None,
            "last_finished": IntegrityCheckSerializer(finished).data if finished else None,
            "broken": bool(finished and finished.status == "failed"),
            "events": AuditEvent.objects.count(),
        })  # fmt: skip

    # export

    @action(detail=False, methods=["get"])
    def export(self, request):
        """CSV of the filtered events. The file's SHA-256 and the filters are written to the audit log first."""
        qs = filtered(request, scope_audit(request.user)).order_by("id")
        total = qs.count()
        if total > export.MAX_ROWS:
            raise Conflict(f"{total} events match. Narrow the filters to {export.MAX_ROWS} or fewer.")
        handle, digest, count = export.build_csv(qs)
        service.record(
            "audit.exported", request=request, entity_type="auditexport", entity_label="Audit CSV",
            metadata={"rows": count, "sha256": digest, "filters": {k: request.query_params[k] for k in FILTERS
                                                                    if request.query_params.get(k)}},
        )  # fmt: skip
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        response = FileResponse(handle, content_type="text/csv; charset=utf-8", as_attachment=True,
                                filename=f"redshadow-audit-{stamp}.csv")  # fmt: skip
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
