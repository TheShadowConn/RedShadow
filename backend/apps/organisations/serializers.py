from rest_framework import serializers

from apps.core.fields import ScopedPrimaryKeyField
from apps.core.serializers import StrictSerializer

from .models import Asset, Contact, Organisation
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


class AssetSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source="organisation.name", read_only=True)
    archived = serializers.BooleanField(source="is_archived", read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id", "organisation", "organisation_name", "name", "type", "identifier", "environment",
            "criticality", "tags", "archived", "archived_at", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = fields


class _TagsField(serializers.ListField):
    child = serializers.CharField(max_length=40)

    def __init__(self, **kwargs):
        super().__init__(max_length=20, **kwargs)


class AssetWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=160)
    type = serializers.ChoiceField(choices=[c for c, _ in Asset.TYPES])
    identifier = serializers.CharField(max_length=500, required=False, allow_blank=True)
    environment = serializers.ChoiceField(choices=[c for c, _ in Asset.ENVIRONMENTS], required=False)
    criticality = serializers.IntegerField(min_value=1, max_value=5, required=False)
    tags = _TagsField(required=False)


class AssetCreateSerializer(AssetWriteSerializer):
    organisation = ScopedPrimaryKeyField(scope=scope_organisations, model=Organisation)
