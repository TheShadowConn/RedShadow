from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer
from apps.files.serializers import AttachmentSerializer
from apps.organisations.models import Asset, Organisation
from apps.organisations.selectors import scope_organisations
from apps.rbac.authz import engagement_permissions
from apps.rbac.catalogue import ENGAGEMENT, PERMISSIONS
from apps.rbac.models import Role

from .models import (
    CATEGORY_CODES,
    CURRENCY_CODES,
    Engagement,
    EngagementAsset,
    EngagementCost,
    EngagementMembership,
    EngagementNote,
    EngagementScenario,
)

_ENGAGEMENT_CODES = {c for c, (scope, _) in PERMISSIONS.items() if scope == ENGAGEMENT}


class UserRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "display_name", "email"]
        read_only_fields = fields


class EngagementListSerializer(serializers.ModelSerializer):
    organisation = serializers.SerializerMethodField()
    lead = UserRefSerializer(read_only=True)
    overdue = serializers.BooleanField(read_only=True)
    scenarios = serializers.SerializerMethodField()

    class Meta:
        model = Engagement
        fields = [
            "id", "ref", "organisation", "name", "type", "status", "start_date", "end_date",
            "lead", "overdue", "scenarios", "version", "archived_at", "deleted_at", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_organisation(self, obj):
        return {"id": obj.organisation_id, "name": obj.organisation.name}

    def get_scenarios(self, obj):
        """Counts only (no names), for the progress bar."""
        from .scenarios import summarise

        return summarise(obj.scenarios.all())


class EngagementSerializer(EngagementListSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta(EngagementListSerializer.Meta):
        fields = EngagementListSerializer.Meta.fields + [
            "scope", "out_of_scope", "objectives", "methodology", "rules_of_engagement", "permissions",
        ]  # fmt: skip
        read_only_fields = fields

    def get_permissions(self, obj):
        """Engagement-scoped codes the requester holds here (drives UI buttons, never security)."""
        return sorted(engagement_permissions(self.context["request"].user, obj.pk) & _ENGAGEMENT_CODES)


class _EngagementDetailFields(StrictSerializer):
    name = serializers.CharField(max_length=200)
    type = serializers.ChoiceField(choices=[c for c, _ in Engagement.TYPES])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    scope = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    out_of_scope = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    objectives = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    methodology = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    rules_of_engagement = serializers.CharField(required=False, allow_blank=True, max_length=50000)


class EngagementCreateSerializer(_EngagementDetailFields):
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)
    lead = ScopedPrimaryKeyField(scope=lambda user: User.objects.filter(is_active=True), model=User)


class EngagementUpdateSerializer(_EngagementDetailFields):
    version = serializers.IntegerField(min_value=1)
    lead = ScopedPrimaryKeyField(scope=lambda user: User.objects.filter(is_active=True), model=User, required=False)

    def validate(self, attrs):
        if "version" not in attrs:
            raise serializers.ValidationError({"version": ["This field is required."]})
        return attrs


class VersionSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class CloneSerializer(StrictSerializer):
    name = serializers.CharField(max_length=200)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    lead = ScopedPrimaryKeyField(scope=lambda user: User.objects.filter(is_active=True), model=User)


class LeadSerializer(VersionSerializer):
    lead = ScopedPrimaryKeyField(scope=lambda user: User.objects.filter(is_active=True), model=User)


class DeleteSerializer(VersionSerializer):
    confirm_ref = serializers.CharField(max_length=20)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class StatusSerializer(VersionSerializer):
    status = serializers.ChoiceField(choices=[c for c, _ in Engagement.STATUSES if c != "archived"])
    acknowledge_open_scenarios = serializers.BooleanField(required=False, default=False)


class MemberSerializer(serializers.ModelSerializer):
    user = UserRefSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    role_override = serializers.SerializerMethodField()

    class Meta:
        model = EngagementMembership
        fields = ["id", "user", "role", "role_override", "finding_scope", "created_at"]
        read_only_fields = fields

    def get_role(self, obj):
        role = obj.effective_role
        return {"id": role.pk, "name": role.name}

    def get_role_override(self, obj):
        return {"id": obj.role_override_id, "name": obj.role_override.name} if obj.role_override_id else None


_ACTIVE_USERS = lambda user: User.objects.filter(is_active=True)  # noqa: E731
_ROLES = lambda user: Role.objects.all()  # noqa: E731


class MemberCreateSerializer(StrictSerializer):
    user = ScopedPrimaryKeyField(scope=_ACTIVE_USERS, model=User)
    role_override = ScopedPrimaryKeyField(scope=_ROLES, model=Role, required=False, allow_null=True)
    finding_scope = serializers.ChoiceField(choices=["", "all", "assigned", "own"], required=False, allow_blank=True)


class MemberUpdateSerializer(StrictSerializer):
    role_override = ScopedPrimaryKeyField(scope=_ROLES, model=Role, required=False, allow_null=True)
    finding_scope = serializers.ChoiceField(choices=["", "all", "assigned", "own"], required=False, allow_blank=True)


class EngagementAssetSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()

    class Meta:
        model = EngagementAsset
        fields = ["id", "asset", "in_scope", "notes", "created_at"]
        read_only_fields = fields

    def get_asset(self, obj):
        a = obj.asset
        return {"id": a.pk, "name": a.name, "type": a.type, "identifier": a.identifier,
                "identifiers": [i.value for i in a.identifiers.all()],
                "environment": a.environment, "criticality": a.criticality, "archived": a.is_archived}  # fmt: skip


class AssetLinkCreateSerializer(StrictSerializer):
    asset = ScopedPrimaryKeyField(scope=lambda user: Asset.objects.select_related("organisation"), model=Asset)
    in_scope = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class AssetLinkUpdateSerializer(StrictSerializer):
    in_scope = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class NoteSerializer(serializers.ModelSerializer):
    author = UserRefSerializer(read_only=True)

    class Meta:
        model = EngagementNote
        fields = ["id", "author", "body", "visibility", "created_at"]
        read_only_fields = fields


class NoteCreateSerializer(StrictSerializer):
    body = serializers.CharField(max_length=20000)
    visibility = serializers.ChoiceField(choices=["team", "all"], required=False, default="team")


class HistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "actor_label",
            "action",
            "entity_type",
            "entity_label",
            "changes",
            "metadata",
            "outcome",
        ]
        read_only_fields = fields


class CostSerializer(serializers.ModelSerializer):
    created_by = UserRefSerializer(read_only=True)

    class Meta:
        model = EngagementCost
        fields = ["id", "amount", "currency", "category", "description", "incurred_on", "created_by", "created_at"]
        read_only_fields = fields


class CostCreateSerializer(StrictSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.ChoiceField(choices=CURRENCY_CODES)
    category = serializers.ChoiceField(choices=CATEGORY_CODES, required=False, default="other")
    description = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")
    incurred_on = serializers.DateField()


class CostUpdateSerializer(CostCreateSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class ScenarioSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = EngagementScenario
        fields = [
            "id", "name", "description", "status", "status_reason", "planned_start", "planned_end",
            "completed_on", "position", "overdue", "images", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_images(self, obj):
        live = [a for a in obj.images.all() if a.deleted_at is None]
        return AttachmentSerializer(sorted(live, key=lambda a: a.created_at), many=True).data

    def get_overdue(self, obj):
        late = obj.planned_end is not None and obj.planned_end < timezone.localdate()
        return bool(late and obj.status in ("planned", "in_progress"))


class _ScenarioDates(StrictSerializer):
    planned_start = serializers.DateField(required=False, allow_null=True)
    planned_end = serializers.DateField(required=False, allow_null=True)


class ScenarioCreateSerializer(_ScenarioDates):
    name = serializers.CharField(max_length=200, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000, default="")


class ScenarioUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=200, required=False, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)


class ScenarioRescheduleSerializer(StrictSerializer):
    planned_start = serializers.DateField(allow_null=True)
    planned_end = serializers.DateField(allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class ScenarioStatusSerializer(_ScenarioDates):
    status = serializers.ChoiceField(choices=[c for c, _ in EngagementScenario.STATUSES])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    completed_on = serializers.DateField(required=False)


class ScenarioOrderSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)


class ScenarioBulkSerializer(StrictSerializer):
    names = serializers.ListField(
        child=serializers.CharField(max_length=200, trim_whitespace=True), allow_empty=False, max_length=50
    )
