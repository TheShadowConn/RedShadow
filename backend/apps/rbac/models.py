from django.db import models

from apps.core.models import BaseModel

from .catalogue import ENGAGEMENT, PLATFORM


class Permission(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    module = models.CharField(max_length=64)
    action = models.CharField(max_length=64)
    scope = models.CharField(max_length=16, choices=[(PLATFORM, "Platform"), (ENGAGEMENT, "Engagement")])
    description = models.CharField(max_length=255)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class Role(BaseModel):
    FINDING_SCOPES = [("all", "All findings"), ("assigned", "Assigned findings only"), ("own", "Own findings only")]

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    system_key = models.CharField(max_length=32, null=True, blank=True, unique=True)
    all_engagements = models.BooleanField(default=False)
    finding_scope = models.CharField(max_length=16, choices=FINDING_SCOPES, default="all")
    mfa_required = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    class Meta:
        ordering = ["name"]

    @property
    def is_system(self) -> bool:
        return self.system_key is not None

    def audit_label(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uniq_role_permission"),
        ]
