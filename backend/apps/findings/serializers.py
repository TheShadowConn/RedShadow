from urllib.parse import urlsplit

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer
from apps.engagements.models import Engagement
from apps.engagements.selectors import scope_engagements
from apps.organisations.models import Asset
from apps.organisations.selectors import scope_assets
from apps.rbac.authz import engagement_permissions
from apps.rbac.catalogue import ENGAGEMENT, PERMISSIONS

from . import lifecycle
from .models import (
    CWE,
    SEVERITIES,
    Finding,
    FindingNote,
    FindingTemplate,
    RemediationActivity,
    RetestItem,
    RetestRound,
)
from .selectors import scope_findings

_ENGAGEMENT_CODES = {c for c, (scope, _) in PERMISSIONS.items() if scope == ENGAGEMENT}


def _user_ref(u):
    return {"id": u.pk, "display_name": u.display_name, "email": u.email} if u else None


class FindingListSerializer(serializers.ModelSerializer):
    engagement = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()
    assigned_pentester = serializers.SerializerMethodField()
    remediation_owner = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Finding
        fields = [
            "id", "ref", "engagement", "title", "severity", "cvss_score", "status", "asset", "cwe_id",
            "endpoint", "assigned_pentester", "remediation_owner", "discovered_at", "due_date", "is_overdue",
            "version", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_engagement(self, obj):
        e = obj.engagement
        return {"id": e.pk, "ref": e.ref, "name": e.name}

    def get_is_overdue(self, obj):
        return bool(obj.due_date and obj.status in lifecycle.OVERDUE_STATUSES and obj.due_date < timezone.localdate())

    def get_asset(self, obj):
        return {"id": obj.asset_id, "name": obj.asset.name} if obj.asset_id else None

    def get_assigned_pentester(self, obj):
        return _user_ref(obj.assigned_pentester)

    def get_remediation_owner(self, obj):
        return _user_ref(obj.remediation_owner)


class FindingSerializer(FindingListSerializer):
    cwe = serializers.SerializerMethodField()
    reported_by = serializers.SerializerMethodField()
    duplicate_of = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    possible_duplicates = serializers.SerializerMethodField()
    verified_by = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()
    imported_from = serializers.SerializerMethodField()

    class Meta(FindingListSerializer.Meta):
        fields = FindingListSerializer.Meta.fields + [
            "description", "technical_details", "poc", "recommendation", "references", "cvss_version",
            "cvss_vector", "cwe", "reported_by", "duplicate_of", "permissions", "possible_duplicates",
            "resolved_at", "verified_at", "verified_by", "closed_at", "risk_accepted_until",
            "risk_acceptance_reason", "allowed_transitions", "imported_from",
        ]  # fmt: skip
        read_only_fields = fields

    def _held(self, obj):
        cache = self.context.setdefault("_held", {})
        if obj.engagement_id not in cache:
            cache[obj.engagement_id] = engagement_permissions(self.context["request"].user, obj.engagement_id)
        return cache[obj.engagement_id]

    def get_cwe(self, obj):
        return {"id": obj.cwe_id, "name": obj.cwe.name} if obj.cwe_id else None

    def get_imported_from(self, obj):
        j = obj.import_job
        return {"file": j.original_name, "at": j.created_at} if j else None

    def get_verified_by(self, obj):
        return _user_ref(obj.verified_by)

    def get_allowed_transitions(self, obj):
        """Moves the caller may make now, with the inputs each one needs. Advisory: the API re-checks."""
        return [
            {"to": r.target, "name": r.name, "note_required": bool(r.note), "needs": list(r.needs)}
            for r in lifecycle.allowed(obj.status, self._held(obj))
        ]

    def get_reported_by(self, obj):
        return _user_ref(obj.reported_by)

    def get_duplicate_of(self, obj):
        t = obj.duplicate_of
        if t is None:
            return None
        visible = scope_findings(self.context["request"].user).filter(pk=t.pk).exists()
        return {"id": t.pk, "ref": t.ref, "title": t.title} if visible else {"id": None, "ref": t.ref, "title": ""}

    def get_permissions(self, obj):
        return sorted(self._held(obj) & _ENGAGEMENT_CODES)

    def get_possible_duplicates(self, obj):
        if obj.status not in lifecycle.EDITABLE_STATUSES:
            return []
        qs = (
            scope_findings(self.context["request"].user)
            .filter(engagement_id=obj.engagement_id, dedupe_hash=obj.dedupe_hash)
            .exclude(pk=obj.pk)
            .exclude(status="duplicate")[:5]
        )
        return [{"id": f.pk, "ref": f.ref, "title": f.title, "status": f.status} for f in qs]


class ReferenceSerializer(StrictSerializer):
    label = serializers.CharField(max_length=120)
    url = serializers.CharField(max_length=500)

    def validate_url(self, value):
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise serializers.ValidationError("Use a full http or https link.")
        return value.strip()


_ACTIVE_USERS = lambda user: User.objects.filter(is_active=True)  # noqa: E731
_ASSETS = lambda user: scope_assets(user).filter(archived_at__isnull=True)  # noqa: E731


class _FindingFields(StrictSerializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    technical_details = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    poc = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    recommendation = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    references = ReferenceSerializer(many=True, required=False, max_length=20)
    severity = serializers.ChoiceField(choices=[c for c, _ in SEVERITIES], required=False)
    cvss_vector = serializers.CharField(required=False, allow_blank=True, max_length=200)
    cwe_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    endpoint = serializers.CharField(required=False, allow_blank=True, max_length=500)
    asset = ScopedPrimaryKeyField(scope=_ASSETS, model=Asset, required=False, allow_null=True)
    discovered_at = serializers.DateField(required=False)
    assigned_pentester = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User, required=False, allow_null=True)
    remediation_owner = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User, required=False, allow_null=True)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class FindingCreateSerializer(_FindingFields):
    engagement = ScopedPrimaryKeyField(scope=scope_engagements, model=Engagement)
    # Optional when a template supplies the title (enforced in the service).
    title = serializers.CharField(max_length=200, required=False)
    template = ScopedPrimaryKeyField(
        scope=lambda user: FindingTemplate.objects.all(), model=FindingTemplate, required=False
    )


class FindingUpdateSerializer(_FindingFields):
    version = serializers.IntegerField(min_value=1)


class VersionSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class FalsePositiveSerializer(VersionSerializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class DuplicateSerializer(VersionSerializer):
    duplicate_of = ScopedPrimaryKeyField(scope=scope_findings, model=Finding)


class TransitionSerializer(VersionSerializer):
    to = serializers.ChoiceField(choices=lifecycle.STATUS_ORDER)
    note = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    risk_accepted_until = serializers.DateField(required=False)
    duplicate_of = ScopedPrimaryKeyField(scope=scope_findings, model=Finding, required=False)


class ActivityCreateSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=["fix_deployed", "mitigated", "comment"])
    note = serializers.CharField(max_length=20000)
    evidence_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=20)

    def validate_note(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value


class ActivitySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = RemediationActivity
        fields = ["id", "actor", "action", "note", "evidence_ids", "from_status", "to_status", "created_at"]
        read_only_fields = fields

    def get_actor(self, obj):
        return _user_ref(obj.actor)


class BulkSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    action = serializers.ChoiceField(choices=["publish", "assign", "delete"])
    assigned_pentester = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User, required=False, allow_null=True)
    remediation_owner = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User, required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["action"] == "assign" and not {"assigned_pentester", "remediation_owner"} & set(attrs):
            raise serializers.ValidationError({"action": ["Choose who to assign."]})
        return attrs


class CvssSerializer(StrictSerializer):
    vector = serializers.CharField(max_length=200)


class CWESerializer(serializers.ModelSerializer):
    class Meta:
        model = CWE
        fields = ["id", "name"]
        read_only_fields = fields


class FindingHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "occurred_at", "actor_label", "action", "changes", "metadata", "outcome"]
        read_only_fields = fields


class NoteSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    visibility = serializers.CharField(read_only=True)

    class Meta:
        model = FindingNote
        fields = ["id", "author", "kind", "visibility", "body", "created_at"]
        read_only_fields = fields

    def get_author(self, obj):
        return _user_ref(obj.author)


class NoteCreateSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=FindingNote.MANUAL_KINDS)
    body = serializers.CharField(max_length=20000)

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value


class TemplateSerializer(serializers.ModelSerializer):
    cwe = serializers.SerializerMethodField()

    class Meta:
        model = FindingTemplate
        fields = [
            "id", "name", "title", "description", "recommendation", "severity", "cvss_vector", "cwe",
            "references", "version", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_cwe(self, obj):
        return {"id": obj.cwe_id, "name": obj.cwe.name} if obj.cwe_id else None


class TemplateWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    recommendation = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    severity = serializers.ChoiceField(choices=[c for c, _ in SEVERITIES], required=False, allow_blank=True)
    cvss_vector = serializers.CharField(required=False, allow_blank=True, max_length=200)
    cwe_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    references = ReferenceSerializer(many=True, required=False, max_length=20)

    def validate(self, attrs):
        if not self.partial and not attrs.get("severity") and not attrs.get("cvss_vector"):
            raise serializers.ValidationError({"severity": ["Choose a severity or provide a CVSS vector."]})
        return attrs


class TemplateUpdateSerializer(TemplateWriteSerializer):
    version = serializers.IntegerField(min_value=1)


# retests and queues


class RetestItemSerializer(serializers.ModelSerializer):
    finding = serializers.SerializerMethodField()
    tested_by = serializers.SerializerMethodField()

    class Meta:
        model = RetestItem
        fields = ["id", "finding", "result", "note", "evidence_ids", "tested_by", "tested_at"]
        read_only_fields = fields

    def get_finding(self, obj):
        f = obj.finding
        return {"id": f.pk, "ref": f.ref, "title": f.title, "severity": f.severity, "status": f.status,
                "version": f.version}  # fmt: skip

    def get_tested_by(self, obj):
        return _user_ref(obj.tested_by)


class RetestRoundSerializer(serializers.ModelSerializer):
    ref = serializers.CharField(read_only=True)
    engagement = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    assessor = serializers.SerializerMethodField()
    requested_at = serializers.DateTimeField(source="created_at", read_only=True)
    items = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    can_record = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = RetestRound
        fields = [
            "id", "ref", "engagement", "number", "status", "note", "requested_by", "assessor", "requested_at",
            "completed_at", "version", "items", "counts", "can_record", "can_manage",
        ]  # fmt: skip
        read_only_fields = fields

    def _items(self, obj):
        """Items whose finding the caller may see: a round never discloses findings outside the caller's scope."""
        cache = self.context.setdefault("_items", {})
        if obj.pk not in cache:
            visible = scope_findings(self.context["request"].user).filter(retest_items__round=obj)
            cache[obj.pk] = list(obj.items.filter(finding__in=visible).select_related("finding", "tested_by"))
        return cache[obj.pk]

    def get_engagement(self, obj):
        e = obj.engagement
        return {"id": e.pk, "ref": e.ref, "name": e.name}

    def get_requested_by(self, obj):
        return _user_ref(obj.requested_by)

    def get_assessor(self, obj):
        return _user_ref(obj.assessor)

    def get_items(self, obj):
        return RetestItemSerializer(self._items(obj), many=True).data

    def get_counts(self, obj):
        items = self._items(obj)
        return {k: sum(1 for i in items if i.result == k) for k, _ in RetestItem.RESULTS} | {"total": len(items)}

    def get_can_record(self, obj):
        return obj.status in RetestRound.ACTIVE and obj.assessor_id == self.context["request"].user.pk

    def get_can_manage(self, obj):
        user = self.context["request"].user
        held = engagement_permissions(user, obj.engagement_id)
        return obj.status in RetestRound.ACTIVE and (obj.requested_by_id == user.pk or "retests.manage" in held)


class RetestRoundCreateSerializer(StrictSerializer):
    engagement = ScopedPrimaryKeyField(scope=lambda user: scope_engagements(user, "retests.create"), model=Engagement)
    assessor = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User)
    findings = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RetestAssignSerializer(VersionSerializer):
    assessor = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User)


class RetestResultSerializer(StrictSerializer):
    result = serializers.ChoiceField(choices=["passed", "failed"])
    note = serializers.CharField(max_length=20000)
    evidence_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=20)
    version = serializers.IntegerField(min_value=1, required=False)  # the finding's version, optional


class QueueFindingSerializer(FindingListSerializer):
    days_left = serializers.SerializerMethodField()
    retest = serializers.SerializerMethodField()

    class Meta(FindingListSerializer.Meta):
        fields = FindingListSerializer.Meta.fields + ["resolved_at", "days_left", "retest"]
        read_only_fields = fields

    def get_days_left(self, obj):
        return (obj.due_date - timezone.localdate()).days if obj.due_date else None

    def get_retest(self, obj):
        item = self.context.get("retests", {}).get(obj.pk)
        if item is None:
            return None
        return {"round_id": item.round_id, "ref": item.round.ref, "assessor": _user_ref(item.round.assessor)}
