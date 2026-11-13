from rest_framework import serializers

from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer
from apps.engagements.models import Engagement
from apps.engagements.selectors import scope_engagements
from apps.findings.selectors import scope_findings

from .mapping import suggest
from .models import ImportJob, ImportMapping, ImportRow


class ImportJobSerializer(serializers.ModelSerializer):
    engagement = serializers.SerializerMethodField()
    uploaded_by = serializers.SerializerMethodField()
    suggested_mapping = serializers.SerializerMethodField()
    file_available = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "engagement",
            "original_name",
            "file_size",
            "file_sha256",
            "encoding",
            "delimiter",
            "headers",
            "sample",
            "status",
            "mapping",
            "mode",
            "duplicates",
            "counts",
            "error",
            "uploaded_by",
            "suggested_mapping",
            "file_available",
            "started_at",
            "finished_at",
            "created_at",
            "version",
        ]
        read_only_fields = fields

    def get_engagement(self, obj):
        e = obj.engagement
        return {"id": e.pk, "ref": e.ref, "name": e.name}

    def get_uploaded_by(self, obj):
        u = obj.uploaded_by
        return {"id": u.pk, "display_name": u.display_name}

    def get_suggested_mapping(self, obj):
        return suggest(obj.headers) if obj.status == "parsed" else {}

    def get_file_available(self, obj):
        return bool(obj.storage_key)


class ImportRowSerializer(serializers.ModelSerializer):
    cells = serializers.SerializerMethodField()
    finding = serializers.SerializerMethodField()
    duplicate_of = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()

    class Meta:
        model = ImportRow
        fields = ["id", "row_number", "status", "title", "severity", "cells", "errors", "duplicate_of", "finding"]
        read_only_fields = fields

    def _visible(self, finding_ids):
        cache = self.context.setdefault("_visible", {})
        missing = [f for f in finding_ids if f and f not in cache]
        if missing:
            found = {f.pk: f for f in scope_findings(self.context["request"].user).filter(pk__in=missing)}
            for f in missing:
                cache[f] = found.get(f)
        return cache

    def get_cells(self, obj):
        headers = self.context["headers"]
        return dict(zip(headers, obj.raw, strict=False))

    def get_title(self, obj):
        return obj.mapped.get("title", "")

    def get_severity(self, obj):
        return obj.mapped.get("severity", "")

    def get_finding(self, obj):
        if not obj.finding_id:
            return None
        f = self._visible([obj.finding_id])[obj.finding_id]
        return {"id": f.pk, "ref": f.ref} if f else None

    def get_duplicate_of(self, obj):
        if obj.duplicate_of_line:
            return {"line": obj.duplicate_of_line}
        if obj.duplicate_of_finding:
            f = self._visible([obj.duplicate_of_finding])[obj.duplicate_of_finding]
            return {"finding": {"id": f.pk, "ref": f.ref, "title": f.title}} if f else {"hidden": True}
        return None


class UploadSerializer(StrictSerializer):
    engagement = ScopedPrimaryKeyField(scope=lambda user: scope_engagements(user, "imports.create"), model=Engagement)
    file = serializers.FileField(allow_empty_file=False)


class MappingSerializer(StrictSerializer):
    column_map = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=200))
    value_map = serializers.DictField(
        child=serializers.DictField(child=serializers.CharField(max_length=40)), required=False, default=dict
    )
    save_as = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")


class CommitSerializer(StrictSerializer):
    mode = serializers.ChoiceField(choices=[k for k, _ in ImportJob.MODES])
    duplicates = serializers.ChoiceField(choices=[k for k, _ in ImportJob.DUPLICATES], default="skip")


class SavedMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportMapping
        fields = ["id", "name", "column_map", "value_map", "created_at"]
        read_only_fields = fields
