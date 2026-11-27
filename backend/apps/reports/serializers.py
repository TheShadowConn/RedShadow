from rest_framework import serializers

from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer
from apps.engagements.models import Engagement
from apps.engagements.selectors import scope_engagements
from apps.findings.models import SEVERITIES

from .builder import REPORTABLE_STATUSES
from .models import FONTS, SECTIONS, ReportJob, ReportTemplate


class ReportJobSerializer(serializers.ModelSerializer):
    engagement = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    template = serializers.SerializerMethodField()
    file_available = serializers.SerializerMethodField()

    class Meta:
        model = ReportJob
        fields = [
            "id", "engagement", "requested_by", "template", "format", "audience", "title", "version_label",
            "classification", "filters", "status", "error", "finding_count", "page_count", "file_name", "size",
            "sha256", "started_at", "finished_at", "expires_at", "file_available", "created_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_engagement(self, obj):
        e = obj.engagement
        return {"id": e.pk, "ref": e.ref, "name": e.name}

    def get_requested_by(self, obj):
        return {"id": obj.requested_by_id, "name": obj.requested_by.display_name}

    def get_template(self, obj):
        return {"id": obj.template_id, "name": obj.template_name} if obj.template_name else None

    def get_file_available(self, obj):
        return obj.file_available


class FiltersSerializer(StrictSerializer):
    tags = serializers.ListField(child=serializers.CharField(max_length=40), required=False, max_length=20)
    severities = serializers.ListField(child=serializers.ChoiceField(choices=SEVERITIES), required=False, max_length=5)
    statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=[(s, s) for s in REPORTABLE_STATUSES]), required=False, max_length=10
    )


class CreateReportSerializer(StrictSerializer):
    engagement = ScopedPrimaryKeyField(scope=lambda user: scope_engagements(user), model=Engagement)
    format = serializers.ChoiceField(choices=ReportJob.FORMATS)
    audience = serializers.ChoiceField(choices=ReportJob.AUDIENCES, default="client")
    template = ScopedPrimaryKeyField(
        scope=lambda user: ReportTemplate.objects.all(), model=ReportTemplate, required=False, allow_null=True
    )
    title = serializers.CharField(required=False, allow_blank=True, max_length=160)
    version_label = serializers.CharField(required=False, allow_blank=True, max_length=20)
    classification = serializers.CharField(required=False, allow_blank=True, max_length=40)
    filters = FiltersSerializer(required=False)


class TemplateSerializer(serializers.ModelSerializer):
    has_logo = serializers.SerializerMethodField()

    class Meta:
        model = ReportTemplate
        fields = [
            "id",
            "name",
            "sections",
            "accent",
            "font",
            "footer_text",
            "is_default",
            "has_logo",
            "version",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_logo(self, obj):
        return bool(obj.logo_key)


class TemplateWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120, required=False)
    sections = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=len(SECTIONS)
    )
    accent = serializers.CharField(max_length=7, required=False)
    font = serializers.ChoiceField(choices=FONTS, required=False)
    footer_text = serializers.CharField(max_length=160, required=False, allow_blank=True)
    is_default = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False, min_value=1)
