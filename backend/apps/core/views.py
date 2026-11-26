import logging
import platform

import django
import redis
from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    pagination_class = None


class LiveView(HealthView):
    def get(self, request):
        return Response({"status": "ok"})


class ReadyView(HealthView):
    def get(self, request):
        checks = {"database": self._database(), "redis": self._redis()}
        ok = all(v == "ok" for v in checks.values())
        return Response(
            {"status": "ok" if ok else "unavailable", "checks": checks},
            status=200 if ok else 503,
        )

    @staticmethod
    def _database() -> str:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
            return "ok"
        except Exception:
            logger.exception("readiness: database check failed")
            return "fail"

    @staticmethod
    def _redis() -> str:
        try:
            client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            return "ok"
        except Exception:
            logger.exception("readiness: redis check failed")
            return "fail"


def backup_status() -> dict:
    """Newest recorded backup (scripts/backup.sh records one) and whether it is recent enough. Super Admin only."""
    from django.utils import timezone

    from apps.audit.models import AuditEvent

    last = AuditEvent.objects.filter(action="system.backup_completed").order_by("-id").first()
    warn = settings.BACKUP_WARN_DAYS
    if last is None:
        return {"status": "none", "last_at": None, "name": "", "size_bytes": 0, "age_days": None,
                "warn_after_days": warn}  # fmt: skip
    age = (timezone.now() - last.occurred_at).days
    meta = last.metadata or {}
    return {
        "status": "stale" if age > warn else "ok",
        "last_at": last.occurred_at,
        "name": meta.get("name", ""),
        "size_bytes": meta.get("size_bytes", 0),
        "age_days": age,
        "warn_after_days": warn,
    }


class AboutView(APIView):
    """Version and build facts for the About page. Any fully signed-in user; nothing sensitive."""

    pagination_class = None

    def get(self, request):
        from apps.rbac.authz import has_platform_perm

        return Response(
            {
                "name": "RedShadow",
                "version": settings.APP_VERSION,
                "build": settings.BUILD_ID,
                "build_date": settings.BUILD_DATE,
                "django": django.get_version(),
                "python": platform.python_version(),
                "backup": backup_status() if has_platform_perm(request.user, "audit.view_all") else None,
            }
        )
