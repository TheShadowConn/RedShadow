from django.conf import settings
from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.rbac.authz import user_permissions
from apps.rbac.models import Role

from .models import User
from .session import restriction


class RoleRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Admin view of a user. Secrets, hashes and session internals are never exposed."""

    role = RoleRefSerializer(read_only=True)
    locked = serializers.BooleanField(source="is_locked", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "display_name", "role", "is_active", "mfa_enabled",
            "must_change_password", "locked", "last_login", "last_password_change", "created_at",
        ]  # fmt: skip
        read_only_fields = fields


def me_payload(user: User, state) -> dict:
    return {
        "id": str(user.pk),
        "email": user.email,
        "display_name": user.display_name,
        "role": {
            "id": str(user.role_id),
            "name": user.role.name,
            "all_engagements": user.role.all_engagements,
            "finding_scope": user.role.finding_scope,
            "mfa_required": user.role.mfa_required,
        },
        "mfa_enabled": user.mfa_enabled,
        "must_change_password": user.must_change_password,
        "session_idle_seconds": settings.SESSION_COOKIE_AGE,
        "restriction": restriction(user, state),
        # UX hints only. The backend enforces every permission on every request.
        "permissions": sorted(user_permissions(user)),
    }


class LoginSerializer(StrictSerializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class PasswordChangeSerializer(StrictSerializer):
    current_password = serializers.CharField(max_length=256, trim_whitespace=False)
    new_password = serializers.CharField(max_length=256, trim_whitespace=False)


class MfaCodeSerializer(StrictSerializer):
    code = serializers.CharField(max_length=10, required=False)
    recovery_code = serializers.CharField(max_length=32, required=False)


class UserCreateSerializer(StrictSerializer):
    email = serializers.CharField(max_length=254)
    display_name = serializers.CharField(max_length=120)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())


class UserUpdateSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=120, required=False)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)


class UserDeleteSerializer(StrictSerializer):
    confirm_email = serializers.CharField(max_length=254)
