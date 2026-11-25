import uuid

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.audit import service as audit
from apps.rbac.authz import has_engagement_perm
from apps.rbac.viewsets import ScopedModelViewSet

from . import selectors, services
from .serializers import AttachmentSerializer


def download_filename(name: str) -> str:
    from urllib.parse import quote

    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


class AttachmentViewSet(ScopedModelViewSet):
    serializer_class = AttachmentSerializer
    http_method_names = ["get", "delete", "head", "options"]
    permission_map = {
        "list": "documents.view",
        "retrieve": "organisations.view",
        "download": "organisations.view",
        "destroy": "documents.delete",
    }

    def get_queryset(self):
        qs = selectors.scope_attachments(self.request.user)
        if self.action == "list":
            qs = qs.exclude(kind__in=("evidence", "scenario_image"))  # listed through their finding or scenario
            eng = self.request.query_params.get("engagement")
            try:
                qs = qs.filter(engagement_id=uuid.UUID(eng)) if eng else qs
            except ValueError:
                qs = qs.none()
        return qs

    def _check_document_access(self, att):
        if att.kind == "document" and not has_engagement_perm(self.request.user, att.engagement_id, "documents.view"):
            raise PermissionDenied("You do not have permission to view documents.")
        if att.kind == "evidence" and not has_engagement_perm(self.request.user, att.engagement_id, "evidence.view"):
            raise PermissionDenied("You do not have permission to view evidence.")
        if att.kind == "scenario_image" and not has_engagement_perm(
            self.request.user, att.engagement_id, "engagement_scenarios.view"
        ):
            raise PermissionDenied("You do not have permission to view scenarios.")

    def retrieve(self, request, *args, **kwargs):
        att = self.get_object()
        self._check_document_access(att)
        return Response(AttachmentSerializer(att).data)

    def destroy(self, request, *args, **kwargs):
        att = self.get_object()
        if att.kind == "evidence":
            raise PermissionDenied("Delete evidence from its finding.")
        if att.kind == "scenario_image":
            raise PermissionDenied("Delete pictures from their scenario.")
        services.delete_document(request, request.user, att)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Authorise, then hand the transfer to nginx (internal /protected/ location)."""
        att = self.get_object()
        self._check_document_access(att)
        if att.kind in ("document", "evidence", "scenario_image"):
            audit.record(
                "attachment.downloaded",
                request=request,
                entity=att,
                engagement=att.engagement,
                metadata={"sha256": att.sha256},
            )
        response = HttpResponse(status=200)
        response["X-Accel-Redirect"] = f"/protected/{att.storage_key}"
        response["Content-Type"] = att.mime
        response["Content-Disposition"] = download_filename(att.original_name)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-store"
        return response
