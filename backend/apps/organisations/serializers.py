from rest_framework import serializers

from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer

from .identifiers import KINDS
from .models import Asset, AssetIdentifier, Contact, Organisation
from .selectors import scope_organisations


class OrganisationSerializer(serializers.ModelSerializer):
    archived = serializers.BooleanField(source="is_archived", read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = [
            "id",
            "name",
            "slug",
            "industry",
            "notes",
            "logo_url",
            "archived",
            "archived_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_logo_url(self, obj):
        return f"/api/v1/attachments/{obj.logo_id}/download" if obj.logo_id else None


class OrganisationWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    industry = serializers.CharField(max_length=80, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=20000)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "organisation", "name", "email", "phone", "title", "is_primary", "created_at", "updated_at"]
        read_only_fields = fields


class ContactWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)


class ContactCreateSerializer(ContactWriteSerializer):
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)


class AssetIdentifierSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = AssetIdentifier
        fields = ["id", "kind", "kind_label", "value", "normalized", "is_primary", "source", "created_at"]
        read_only_fields = fields


class AssetSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source="organisation.name", read_only=True)
    archived = serializers.BooleanField(source="is_archived", read_only=True)
    identifiers = AssetIdentifierSerializer(many=True, read_only=True)
    engagement_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Asset
        fields = [
            "id", "organisation", "organisation_name", "name", "type", "identifier", "identifiers", "environment",
            "criticality", "tags", "archived", "archived_at", "onboarding_status", "origin", "onboarded_at",
            "engagement_count", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields


class _TagsField(serializers.ListField):
    child = serializers.CharField(max_length=40)

    def __init__(self, **kwargs):
        super().__init__(max_length=20, **kwargs)


class IdentifierInputSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=KINDS, required=False, allow_blank=True)
    value = serializers.CharField(max_length=500, trim_whitespace=True)
    is_primary = serializers.BooleanField(required=False)


class IdentifierPatchSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=KINDS, required=False)
    value = serializers.CharField(max_length=500, required=False)
    is_primary = serializers.BooleanField(required=False)


class AssetWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    type = serializers.ChoiceField(choices=[c for c, _ in Asset.TYPES])
    # Older clients send one identifier as text; it becomes the primary identifier.
    identifier = serializers.CharField(max_length=500, required=False, allow_blank=True)
    environment = serializers.ChoiceField(choices=[c for c, _ in Asset.ENVIRONMENTS], required=False)
    criticality = serializers.IntegerField(min_value=1, max_value=5, required=False)
    tags = _TagsField(required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value


class AssetCreateSerializer(AssetWriteSerializer):
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)
    identifiers = IdentifierInputSerializer(many=True, required=False, max_length=50)


class AssetOnboardSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160, required=False)
    type = serializers.ChoiceField(choices=[c for c, _ in Asset.TYPES], required=False)
    environment = serializers.ChoiceField(choices=[c for c, _ in Asset.ENVIRONMENTS], required=False)
    criticality = serializers.IntegerField(min_value=1, max_value=5, required=False)
    tags = _TagsField(required=False)


class AssetBulkOnboardSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=500)


class AssetBulkArchiveSerializer(StrictSerializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=500)
    archived = serializers.BooleanField()


class AssetMergeSerializer(StrictSerializer):
    source = serializers.UUIDField()


class IdentifierCheckSerializer(StrictSerializer):
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)
    asset = serializers.UUIDField(required=False)
    identifiers = IdentifierInputSerializer(many=True, max_length=50)
