import io
import uuid

from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.storage import get_storage
from apps.rbac.viewsets import ScopedModelViewSet

from . import selectors, services
from .models import ReportJob, ReportTemplate
from .serializers import CreateReportSerializer, ReportJobSerializer, TemplateSerializer, TemplateWriteSerializer

CONTENT_TYPES = {"pdf": "application/pdf", "csv": "text/csv; charset=utf-8"}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class ReportJobViewSet(ScopedModelViewSet):
    serializer_class = ReportJobSerializer
    http_method_names = ["get", "post", "head", "options"]
    permission_map = {
        "list": "reports.view",
        "retrieve": "reports.view",
        "create": "reports.view",  # coarse gate; the service checks the format's own codes on the engagement
        "download": "reports.view",
    }

    def get_queryset(self):
        qs = selectors.scope_reports(self.request.user)
        if self.action == "list":
            p = self.request.query_params
            if p.get("engagement"):
                qs = qs.filter(engagement_id=p["engagement"]) if _is_uuid(p["engagement"]) else qs.none()
            if p.get("format") in dict(ReportJob.FORMATS):
                qs = qs.filter(format=p["format"])
            if p.get("status") in dict(ReportJob.STATUSES):
                qs = qs.filter(status=p["status"])
        return qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    def create(self, request, *args, **kwargs):
        serializer = CreateReportSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        job = services.create_job(
            request, request.user, serializer.validated_data["engagement"], serializer.validated_data
        )
        job = self.get_queryset().get(pk=job.pk)
        return Response(
            ReportJobSerializer(job, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        job = self.get_object()
        data = services.read_file(request, request.user, job)
        response = FileResponse(
            io.BytesIO(data),
            content_type=CONTENT_TYPES[job.format],
            as_attachment=True,
            filename=job.file_name or "report",
        )
        response["Content-Length"] = str(len(data))
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ReportTemplateViewSet(ScopedModelViewSet):
    """Reading is open to anyone who can create reports (the dialog needs the names); writing is admin only."""

    serializer_class = TemplateSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = [MultiPartParser, *ScopedModelViewSet.parser_classes]
    permission_map = {
        "list": "reports.view",
        "retrieve": "reports.view",
        "create": "reports.manage_templates",
        "partial_update": "reports.manage_templates",
        "destroy": "reports.manage_templates",
        "logo": "reports.manage_templates",
        "set_logo": "reports.manage_templates",
        "clear_logo": "reports.manage_templates",
    }

    def get_queryset(self):
        return ReportTemplate.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = TemplateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "name" not in data:
            raise ValidationError({"name": ["This field is required."]})
        template = services.save_template(request, request.user, None, data)
        return Response(TemplateSerializer(template).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial"):
            raise MethodNotAllowed(request.method)
        template = self.get_object()
        serializer = TemplateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = services.save_template(request, request.user, template, serializer.validated_data)
        return Response(TemplateSerializer(template).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_template(request, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="logo", url_name="logo")
    def logo(self, request, pk=None):
        template = self.get_object()
        if not template.logo_key:
            raise Http404
        response = FileResponse(io.BytesIO(get_storage().read(template.logo_key)), content_type="image/png")
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @logo.mapping.post
    def set_logo(self, request, pk=None):
        template = self.get_object()
        uploaded = request.FILES.get("logo")
        if uploaded is None:
            raise ValidationError({"logo": ["Choose a logo file."]})
        return Response(TemplateSerializer(services.set_logo(request, template, uploaded)).data)

    @logo.mapping.delete
    def clear_logo(self, request, pk=None):
        return Response(TemplateSerializer(services.clear_logo(request, self.get_object())).data)
