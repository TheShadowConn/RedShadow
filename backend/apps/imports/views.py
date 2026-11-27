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
    AssetUploadSerializer,
    AttemptSerializer,
    CommitSerializer,
    ImportJobSerializer,
    ImportRowSerializer,
    MappingSerializer,
    ReuploadSerializer,
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
    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_map = {
        "list": "imports.view",
        "retrieve": "imports.view",
        "create": "imports.create",
        "destroy": "imports.create",
        "clear_history": "imports.delete_history",
        "reupload": "imports.create",
        "retry": "imports.create",
        "history": "imports.view",
        "asset_template": "imports.view",
        "set_mapping": "imports.create",
        "rows": "imports.view",
        "commit": "imports.create",
        "cancel": "imports.create",
        "errors": "imports.view",
        "template": "imports.view",
        "cvss_guide": "imports.view",
        "cwe_list": "imports.view",
    }

    def get_queryset(self):
        qs = selectors.scope_imports(self.request.user)
        if self.action == "list":
            p = self.request.query_params
            if p.get("engagement"):
                qs = qs.filter(engagement_id=p["engagement"]) if _is_uuid(p["engagement"]) else qs.none()
            if p.get("organisation"):
                qs = qs.filter(organisation_id=p["organisation"]) if _is_uuid(p["organisation"]) else qs.none()
            if p.get("status") in dict(ImportJob.STATUSES):
                qs = qs.filter(status=p["status"])
            if p.get("kind") in dict(ImportJob.KINDS):
                qs = qs.filter(kind=p["kind"])
            term = p.get("search", "").strip()
            if term:
                qs = qs.filter(original_name__icontains=term)
        return qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    parser_classes = [MultiPartParser, *ScopedModelViewSet.parser_classes]

    def create(self, request, *args, **kwargs):
        if request.data.get("kind") == "assets":
            data = _validated(AssetUploadSerializer, request)
            job = services.create_asset_upload(request, request.user, data["organisation"], data["file"])
        else:
            data = _validated(UploadSerializer, request)
            job = services.create_upload(
                request, request.user, data["engagement"], data["file"], data["include_info"]
            )
        return Response(self._detail(job), status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        services.delete_job(request, request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="clear-history")
    def clear_history(self, request):
        """Super Admin: remove every finished import from the history. Findings and assets they created stay."""
        return Response({"deleted": services.clear_history(request, request.user)})

    @action(detail=True, methods=["post"])
    def reupload(self, request, pk=None):
        """A corrected file for the same import: starts a new attempt and re-checks with the same columns."""
        job = self.get_object()
        data = _validated(ReuploadSerializer, request)
        services.reupload(request, request.user, job, data["file"])
        return Response(self._detail(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        job = self.get_object()
        services.retry(request, request.user, job)
        return Response(self._detail(job), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"], pagination_class=None)
    def history(self, request, pk=None):
        job = self.get_object()
        return Response(AttemptSerializer(job.attempts.select_related("uploaded_by"), many=True).data)

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
        attempt = request.query_params.get("attempt", "")
        qs = job.rows.filter(attempt=int(attempt)) if attempt.isdigit() else job.rows_now
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
        rows = job.rows_now.exclude(status__in=["valid", "imported", "pending"]).order_by("row_number", "id")

        def lines():
            for r in rows.iterator(chunk_size=1000):
                reasons = "; ".join(f"{e['field']}: {e['message']}" for e in r.errors)
                if r.status == "duplicate" or r.status == "skipped":
                    known = (
                        "Already known: nothing new to add"
                        if job.kind == "assets"
                        else "Duplicate of an existing finding"
                    )
                    reasons = reasons or (f"Duplicate of line {r.duplicate_of_line}" if r.duplicate_of_line else known)
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

    @staticmethod
    def _csv_response(header, rows, filename):
        handle, _, _ = write_csv(header, rows)
        response = FileResponse(handle, content_type="text/csv; charset=utf-8", as_attachment=True, filename=filename)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["get"], url_path="cvss-guide.csv", url_name="cvss-guide")
    def cvss_guide(self, request):
        """CVSS score ranges and the severity each one gives. A CVSS vector sets the severity; if you also give a
        severity it must match the range."""
        from decimal import Decimal

        from apps.findings.cvss import BANDS

        ceilings = [Decimal("10.0")] + [floor - Decimal("0.1") for floor, _ in BANDS[:-1]]
        rows = [
            [f"{floor} to {ceiling}", name.capitalize(), name]
            for (floor, name), ceiling in zip(BANDS, ceilings, strict=True)
        ]
        rows.append(["0.0", "Info", "info"])
        rows.append(["", "", ""])
        rows.append(["Note", "Put a CVSS vector in the CVSS vector column and the severity is worked out for you.", ""])
        rows.append(["Note", "If you give both, the severity must match the range above or the row is flagged.", ""])
        header = ["CVSS base score", "Severity", "Value to type in the Severity column"]
        return self._csv_response(header, rows, "redshadow-cvss-guide.csv")

    @action(detail=False, methods=["get"], url_path="cwe-list.csv", url_name="cwe-list")
    def cwe_list(self, request):
        """Every CWE the import accepts. Type either the number or the CWE-79 form in the CWE column."""
        from apps.findings.models import CWE

        rows = [[f"CWE-{pk}", pk, name] for pk, name in CWE.objects.order_by("pk").values_list("pk", "name")]
        return self._csv_response(["Value for the CWE column", "Number", "Name"], rows, "redshadow-cwe-list.csv")

    @action(detail=False, methods=["get"], url_path="asset-template.csv", url_name="asset-template")
    def asset_template(self, request):
        # Six plain columns. Identifiers holds IPs, hostnames, URLs and so on, several per cell separated by
        # semicolons; the kind of each is detected. Tags (for example the owning department) are also
        # separated by semicolons and may be left empty. Other asset columns exist but the template does not need them.
        header = ["Name", "Asset type", "Environment", "Criticality", "Identifiers", "Tags"]
        examples = [
            ["Acme shop", "Web application", "prod", "high", "https://shop.acme.test", "IT Help Desk; Security"],
            ["Web 01", "Host", "prod", "medium", "10.0.0.5; web01.acme.test", "Network Engineering"],
            ["Acme API", "Web application", "staging", "", "https://api.staging.acme.test", ""],
        ]
        handle, _, _ = write_csv(header, examples)
        response = FileResponse(
            handle,
            content_type="text/csv; charset=utf-8",
            as_attachment=True,
            filename="redshadow-asset-import-template.csv",
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
