"""Backup download and restore upload. Super Admin only, and the password (and two-step code) is asked again."""

import tempfile

from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import IsAuthenticatedSession
from apps.accounts.services import _check_totp
from apps.audit import service as audit
from apps.rbac.viewsets import ActionPermission

from . import backup, restore_jobs
from .errors import Conflict
from .serializers import StrictSerializer
from .views import backup_status

MAX_UPLOAD = 2 * 1024 * 1024 * 1024


class _Confirm(StrictSerializer):
    password = serializers.CharField(max_length=200, trim_whitespace=False)
    code = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    passphrase = serializers.CharField(max_length=200, trim_whitespace=False)


class _Restore(_Confirm):
    file = serializers.FileField(allow_empty_file=False)


def _confirmed(serializer_class, request) -> dict:
    user = request.user
    if user.role.system_key != "super_admin":
        raise PermissionDenied("Only a Super Admin can back up or restore.")
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if not user.check_password(data["password"]):
        audit.record("system.confirmation_failed", request=request, outcome="failure")
        raise ValidationError({"password": ["That is not your password."]})
    if user.mfa_enabled and not _check_totp(user, data["code"]):
        audit.record("system.confirmation_failed", request=request, outcome="failure")
        raise ValidationError({"code": ["Enter a new code from your authenticator app."]})
    return data


class SystemViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticatedSession, ActionPermission]
    permission_map = {"overview": "settings.manage", "backup": "settings.manage", "restore": "settings.manage"}

    parser_classes = [JSONParser, MultiPartParser]

    @action(detail=False, methods=["get"])
    def overview(self, request):
        return Response(
            {"last_backup": backup_status(), "restore_allowed": backup.is_empty(), "restore": restore_jobs.status()}
        )

    @action(detail=False, methods=["post"])
    def backup(self, request):
        data = _confirmed(_Confirm, request)
        if len(data["passphrase"]) < backup.MIN_PASSPHRASE:
            raise ValidationError({"passphrase": [f"Use at least {backup.MIN_PASSPHRASE} characters."]})
        handle = tempfile.TemporaryFile(dir=backup.staging_dir())  # noqa: SIM115 - closed by the response
        manifest = backup.write_bundle(data["passphrase"], handle)
        size = handle.tell()
        handle.seek(0)
        name = f"redshadow-{timezone.now():%Y%m%d-%H%M%S}.rsbk"
        audit.record(
            "system.backup_completed",
            request=request,
            entity_type="system",
            entity_label="Backup",
            metadata={"name": name, "size_bytes": size, "files": manifest["files"]},
        )
        response = FileResponse(handle, content_type="application/octet-stream", as_attachment=True, filename=name)
        response["Content-Length"] = size
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["post"])
    def restore(self, request):
        data = _confirmed(_Restore, request)
        if not backup.is_empty():
            raise Conflict("A restore is only possible on a new installation with no organisations or engagements.")
        if restore_jobs.status()["state"] in restore_jobs.BUSY:
            raise Conflict("A restore is already running.")
        if data["file"].size > MAX_UPLOAD:
            raise ValidationError({"file": ["The file is larger than 2 GB. Use the command line restore."]})
        try:
            restore_jobs.queue(data["file"], data["passphrase"], request.user.email)
        except backup.BackupError as exc:
            raise ValidationError({"file": [str(exc)]}) from None
        audit.record("system.restore_requested", request=request, entity_type="system", entity_label="Restore")
        return Response(restore_jobs.status(), status=202)
