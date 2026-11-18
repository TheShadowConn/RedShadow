from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import BaseModel

from . import crypto


class User(BaseModel, AbstractBaseUser):
    """Platform user. Deleting removes the row only when nothing refers to it; otherwise the account is
    anonymised (``deleted_at``) so audit and finding attribution stay intact."""

    email = models.CharField(max_length=254)  # stored lower-case; unique case-insensitively
    display_name = models.CharField(max_length=120)
    role = models.ForeignKey("rbac.Role", on_delete=models.PROTECT, related_name="users")
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret_enc = models.TextField(blank=True)
    mfa_last_step = models.BigIntegerField(default=0)
    session_version = models.PositiveIntegerField(default=1)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_password_change = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    # Set when an administrator deletes the account. The row stays as an anonymous tombstone when
    # findings, notes or evidence still point at it, so history keeps its shape.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci")]
        ordering = ["email"]

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def mfa_secret(self) -> str:
        return crypto.decrypt(self.mfa_secret_enc) if self.mfa_secret_enc else ""

    @mfa_secret.setter
    def mfa_secret(self, value: str) -> None:
        self.mfa_secret_enc = crypto.encrypt(value) if value else ""

    def audit_label(self) -> str:
        return self.email

    def __str__(self) -> str:
        return self.email


class RecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
