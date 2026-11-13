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


class AboutView(APIView):
    """Version and build facts for the About page. Any fully signed-in user; nothing sensitive."""

    pagination_class = None

    def get(self, request):
        return Response(
            {
                "name": "RedShadow",
                "version": settings.APP_VERSION,
                "build": settings.BUILD_ID,
                "build_date": settings.BUILD_DATE,
                "django": django.get_version(),
                "python": platform.python_version(),
            }
        )
