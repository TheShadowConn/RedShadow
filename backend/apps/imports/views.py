from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.csvout import write_csv
from apps.core.pagination import StandardPagination
from apps.rbac.viewsets import ScopedModelViewSet

from . import mapping as mapping_rules
from . import selectors, services
from .models import ImportJob
from .serializers import (
    CommitSerializer,
    ImportJobSerializer,
    ImportRowSerializer,
    MappingSerializer,
    SavedMappingSerializer,
    UploadSerializer,
)

ROW_STATUSES = {"pending", "valid", "invalid", "duplicate", "skipped", "imported"}


def _validated(serializer_class, request):
    serializer = serializer_class(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class ImportJobViewSet(ScopedModelViewSet):
    serializer_class = ImportJobSerializer
    http_method_names = ["get", "post", "head", "options"]
    permission_map = {
        "list": "imports.view",
        "retrieve": "imports.view",
        "create": "imports.create",
        "set_mapping": "imports.create",
        "rows": "imports.view",
        "commit": "imports.create",
        "cancel": "imports.create",
        "errors": "imports.view",
        "template": "imports.view",
    }

    def get_queryset(self):
        qs = selectors.scope_imports(self.request.user)
        if self.action == "list":
            p = self.request.query_params
            if p.get("engagement"):
                qs = qs.filter(engagement_id=p["engagement"]) if _is_uuid(p["engagement"]) else qs.none()
            if p.get("status") in dict(ImportJob.STATUSES):
                qs = qs.filter(status=p["status"])
        return qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    parser_classes = [MultiPartParser, *ScopedModelViewSet.parser_classes]

    def create(self, request, *args, **kwargs):
        data = _validated(UploadSerializer, request)
        job = services.create_upload(request, request.user, data["engagement"], data["file"])
        return Response(self._detail(job), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    @action(detail=True, methods=["post"], url_path="mapping")
    def set_mapping(self, request, pk=None):
        job = self.get_object()
        data = _validated(MappingSerializer, request)
        services.set_mapping(request, request.user, job, data["column_map"], data["value_map"], data["save_as"])
        return Response(self._detail(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        job = self.get_object()
        data = _validated(CommitSerializer, request)
        services.commit(request, request.user, job, data["mode"], data["duplicates"])
        return Response(self._detail(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        services.cancel(request, request.user, job)
        return Response(self._detail(job))

    @action(detail=True, methods=["get"])
    def rows(self, request, pk=None):
        job = self.get_object()
        qs = job.rows.all()
        wanted = [x for x in request.query_params.get("status", "").split(",") if x in ROW_STATUSES]
        if wanted:
            qs = qs.filter(status__in=wanted)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        ctx = {**self.get_serializer_context(), "headers": job.headers}
        return paginator.get_paginated_response(ImportRowSerializer(page, many=True, context=ctx).data)

    @action(detail=True, methods=["get"], url_path="errors.csv", url_name="errors")
    def errors(self, request, pk=None):
        """Rows that were not imported, with the reason, in the shape of the original file."""
        job = self.get_object()
        rows = job.rows.exclude(status__in=["valid", "imported", "pending"]).order_by("row_number", "id")

        def lines():
            for r in rows.iterator(chunk_size=1000):
                reasons = "; ".join(f"{e['field']}: {e['message']}" for e in r.errors)
                if r.status == "duplicate" or r.status == "skipped":
                    reasons = reasons or (
                        f"Duplicate of line {r.duplicate_of_line}"
                        if r.duplicate_of_line
                        else "Duplicate of an existing finding"
                    )
                yield [r.row_number, r.status, reasons, *r.raw[: len(job.headers)]]

        handle, _, _ = write_csv(["line", "status", "problems", *job.headers], lines())
        response = FileResponse(
            handle,
            content_type="text/csv; charset=utf-8",
            as_attachment=True,
            filename=f"import-{str(job.pk)[:8]}-errors.csv",
        )
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["get"], url_path="template.csv", url_name="template")
    def template(self, request):
        header = [label for _, label, _ in mapping_rules.FIELDS]
        # The Asset column takes an asset's name, IP address or URL, exactly as recorded on the asset.
        examples = [
            [
                "SQL injection in search",
                "high",
                "",
                "The search parameter is concatenated into a query.",
                "Use parameterised queries.",
                "",
                "",
                "/search",
                "Acme shop",
                "89",
                "2026-11-13",
                "OWASP|https://owasp.org/",
            ],
            [
                "Outdated SSH service",
                "medium",
                "",
                "The host runs an SSH version with known flaws.",
                "Upgrade OpenSSH.",
                "",
                "",
                "",
                "10.0.0.5",
                "",
                "2026-11-13",
                "",
            ],
            [
                "Missing security headers",
                "low",
                "",
                "The response lacks common hardening headers.",
                "Add the headers at the proxy.",
                "",
                "",
                "/",
                "https://shop.acme.test",
                "693",
                "2026-11-13",
                "",
            ],
        ]
        handle, _, _ = write_csv(header, examples)
        response = FileResponse(
            handle, content_type="text/csv; charset=utf-8", as_attachment=True, filename="redshadow-import-template.csv"
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def _detail(self, job):
        return ImportJobSerializer(self.get_queryset().get(pk=job.pk), context=self.get_serializer_context()).data


class ImportMappingViewSet(ScopedModelViewSet):
    """The caller's own saved mappings."""

    serializer_class = SavedMappingSerializer
    http_method_names = ["get", "delete", "head", "options"]
    permission_map = {"list": "imports.view", "retrieve": "imports.view", "destroy": "imports.create"}
    pagination_class = None

    def get_queryset(self):
        return selectors.scope_mappings(self.request.user)


def _is_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True
