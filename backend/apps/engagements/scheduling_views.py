import uuid

from django.http import Http404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession
from apps.core.serializers import StrictSerializer
from apps.rbac.viewsets import ActionPermission

from . import scheduling
from .models import Engagement
from .selectors import scope_engagements


class RescheduleSerializer(StrictSerializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    version = serializers.IntegerField(min_value=1)
    dry_run = serializers.BooleanField(required=False, default=False)


def _uuid(value, name):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationError({name: ["Not a valid id."]}) from None


class CalendarViewSet(viewsets.ViewSet):
    """Calendar feed and rescheduling. Both go through the scoped engagement selector."""

    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {"events": "calendar.view", "scenarios": "calendar.view", "reschedule": "engagements.schedule"}

    @action(detail=False, methods=["get"], url_path="scenarios")
    def scenarios(self, request):
        p = request.query_params
        start, end = scheduling.parse_window(p.get("start", ""), p.get("end", ""))
        return Response({"results": scheduling.scenario_feed(request.user, start, end)})

    @action(detail=False, methods=["get"], url_path="events")
    def events(self, request):
        p = request.query_params
        start, end = scheduling.parse_window(p.get("start", ""), p.get("end", ""))
        valid = {s for s, _ in Engagement.STATUSES}
        filters = {
            "status": [s for s in p.get("status", "").split(",") if s in valid],
            "engagement": [_uuid(x, "engagement") for x in p.get("engagement", "").split(",") if x],
            "client": _uuid(p["client"], "client") if p.get("client") else None,
            "pentester": _uuid(p["pentester"], "pentester") if p.get("pentester") else None,
            "mine": p.get("mine") == "true",
        }
        return Response({"results": scheduling.feed(request.user, start, end, filters)})

    @action(detail=False, methods=["post"], url_path=r"events/(?P<event_id>[^/.]+)/reschedule")
    def reschedule(self, request, event_id=None):
        eng = scope_engagements(request.user, "calendar.view").filter(pk=_uuid(event_id, "id")).first()
        if eng is None:
            raise Http404
        s = RescheduleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        eng, conflicts = scheduling.reschedule(
            request, request.user, eng, d["start_date"], d["end_date"], d["version"], d["dry_run"]
        )
        return Response({
            "id": eng.pk, "start_date": eng.start_date, "end_date": eng.end_date, "version": eng.version,
            "saved": not d["dry_run"], "conflicts": conflicts,
        })  # fmt: skip
