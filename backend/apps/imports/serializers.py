from rest_framework import serializers

from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer
from apps.engagements.models import Engagement
from apps.engagements.selectors import scope_engagements
from apps.findings.selectors import scope_findings
from apps.organisations.models import Organisation
from apps.organisations.selectors import scope_organisations

from . import services
from .mapping import suggest, suggest_assets
from .models import ImportAttempt, ImportJob, ImportMapping, ImportRow


class ImportJobSerializer(serializers.ModelSerializer):
    engagement = serializers.SerializerMethodField()
    organisation = serializers.SerializerMethodField()
    uploaded_by = serializers.SerializerMethodField()
    suggested_mapping = serializers.SerializerMethodField()
    file_available = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_reupload = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "kind",
            "engagement",
            "organisation",
            "attempt",
            "can_delete",
            "can_reupload",
            "can_retry",
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
        return {"id": e.pk, "ref": e.ref, "name": e.name} if e else None

    def get_organisation(self, obj):
        o = obj.organisation
        return {"id": o.pk, "name": o.name} if o else None

    def get_can_delete(self, obj):
        return obj.status in services.FAILED_OR_STUCK

    def get_can_reupload(self, obj):
        return services.can_reupload(obj)

    def get_can_retry(self, obj):
        return obj.status == "failed" and bool(obj.storage_key)

    def get_uploaded_by(self, obj):
        u = obj.uploaded_by
        return {"id": u.pk, "display_name": u.display_name}

    def get_suggested_mapping(self, obj):
        if obj.status != "parsed":
            return {}
        return suggest_assets(obj.headers) if obj.kind == "assets" else suggest(obj.headers)

    def get_file_available(self, obj):
        return bool(obj.storage_key)


class ImportRowSerializer(serializers.ModelSerializer):
    cells = serializers.SerializerMethodField()
    finding = serializers.SerializerMethodField()
    duplicate_of = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    severity = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()

    class Meta:
        model = ImportRow
        fields = [
            "id", "row_number", "status", "title", "severity", "cells", "errors", "duplicate_of", "finding", "asset",
        ]  # fmt: skip
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
        return obj.mapped.get("title") or obj.mapped.get("name", "")

    def get_asset(self, obj):
        """For an asset row: what the import does with it, and the asset it created or joined."""
        m = obj.mapped
        if "identifiers" not in m:
            return None
        asset_id = obj.asset_id or m.get("asset_id")
        return {
            "action": m.get("action", ""),
            "identifiers": [{"kind": i["kind"], "value": i["value"]} for i in m["identifiers"]],
            "new_identifiers": m.get("new_identifiers", 0),
            "type": m.get("type"),
            "asset": {"id": asset_id, "name": m.get("asset_name") or m.get("name", "")} if asset_id else None,
            "target_line": m.get("target_line"),
        }

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
    kind = serializers.ChoiceField(choices=["findings"], required=False)
    engagement = ScopedPrimaryKeyField(scope=lambda user: scope_engagements(user, "imports.create"), model=Engagement)
    file = serializers.FileField(allow_empty_file=False)


class AssetUploadSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=["assets"])
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)
    file = serializers.FileField(allow_empty_file=False)


class ReuploadSerializer(StrictSerializer):
    file = serializers.FileField(allow_empty_file=False)


class AttemptSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = ImportAttempt
        fields = [
            "number", "original_name", "file_sha256", "file_size", "counts", "outcome", "error", "uploaded_by",
            "created_at", "finished_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_uploaded_by(self, obj):
        return {"id": obj.uploaded_by_id, "display_name": obj.uploaded_by.display_name}


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
