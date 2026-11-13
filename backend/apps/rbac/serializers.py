from rest_framework import serializers

from apps.core.serializers import StrictSerializer

from .models import Permission, Role


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["code", "module", "action", "scope", "description"]
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    is_system = serializers.BooleanField(read_only=True)
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = [
            "id", "name", "description", "is_system", "system_key", "all_engagements",
            "finding_scope", "mfa_required", "permissions", "user_count",
        ]  # fmt: skip
        read_only_fields = fields

    def get_permissions(self, role) -> list[str]:
        return sorted(rp.permission_id for rp in role.role_permissions.all())


class RoleWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(allow_blank=True, required=False, max_length=2000)
    all_engagements = serializers.BooleanField(required=False)
    finding_scope = serializers.ChoiceField(choices=["all", "assigned", "own"], required=False)
    mfa_required = serializers.BooleanField(required=False)
    permissions = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=200)

    def validate_name(self, value):
        return value.strip()
