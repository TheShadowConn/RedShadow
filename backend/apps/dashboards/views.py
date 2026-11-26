from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession
from apps.rbac.viewsets import ActionPermission

from . import selectors


class CostReportViewSet(viewsets.ViewSet):
    """All cost lines across engagements with filters (year, month, engagement, category, currency)."""

    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {"list": "engagement_costs.view"}

    def list(self, request):
        return Response(selectors.cost_report(request.user, request.query_params))


class DashboardViewSet(viewsets.ViewSet):
    """Read-only aggregates. One dashboard per role family; each needs its own platform permission."""

    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {
        "admin": "dashboards.admin",
        "pentester": "dashboards.pentester",
        "remediation": "dashboards.remediation",
        "vendor": "dashboards.vendor",
    }

    @action(detail=False, methods=["get"])
    def admin(self, request):
        return Response(selectors.build("admin", request.user))

    @action(detail=False, methods=["get"])
    def pentester(self, request):
        return Response(selectors.build("pentester", request.user))

    @action(detail=False, methods=["get"])
    def remediation(self, request):
        return Response(selectors.build("remediation", request.user))

    @action(detail=False, methods=["get"])
    def vendor(self, request):
        return Response(selectors.build("vendor", request.user))
