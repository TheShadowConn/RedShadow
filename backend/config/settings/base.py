import os
from pathlib import Path
from urllib.parse import quote

from apps.core.secrets import secret

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = secret("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

# django.contrib.auth is intentionally NOT installed: authentication is our own session +
# MFA layer (apps.accounts). Only its hashers and password validators are reused.
INSTALLED_APPS = [
    "django.contrib.sessions",
    "rest_framework",
    "apps.core",
    "apps.rbac",
    "apps.audit",
    "apps.accounts",
    "apps.organisations",
    "apps.engagements",
    "apps.files",
    "apps.findings",
    "apps.imports",
    "apps.reports",
    "apps.dashboards",
    "apps.notifications",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"autoescape": True},
    }
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "redshadow"),
        "USER": os.environ["DB_USER"],
        "PASSWORD": secret("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_URL = f"redis://:{quote(secret('REDIS_PASSWORD'), safe='')}@{REDIS_HOST}:6379/0"

MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/data/media")
# Remediation SLA: days from publication to due date, per severity. "info" has no SLA.
SLA_DAYS = {
    "critical": int(os.environ.get("SLA_DAYS_CRITICAL", "7")),
    "high": int(os.environ.get("SLA_DAYS_HIGH", "30")),
    "medium": int(os.environ.get("SLA_DAYS_MEDIUM", "90")),
    "low": int(os.environ.get("SLA_DAYS_LOW", "180")),
}
# Shown on the About page. Set through compose env (APP_VERSION, BUILD_ID, BUILD_DATE).
APP_VERSION = os.environ.get("APP_VERSION", "1.5.0")
# The About page warns Super Admins when the newest recorded backup is older than this many days.
BACKUP_WARN_DAYS = int(os.environ.get("BACKUP_WARN_DAYS", "7"))
BUILD_ID = os.environ.get("BUILD_ID", "dev")
BUILD_DATE = os.environ.get("BUILD_DATE", "")

REPORT_RETENTION_DAYS = int(os.environ.get("REPORT_RETENTION_DAYS", "90"))
RISK_ACCEPT_MAX_DAYS = int(os.environ.get("RISK_ACCEPT_MAX_DAYS", "365"))
ATTACHMENT_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_MB", "25")) * 1024 * 1024
ATTACHMENT_RETENTION_DAYS = int(os.environ.get("ATTACHMENT_RETENTION_DAYS", "30"))  # soft-deleted files kept this long

TLS_ON = os.environ.get("TLS_MODE", "selfsigned") != "off"

# Sessions: server-side, HttpOnly, rotated on login. Idle timeout slides with each request.
# Optional email for notifications. Off while EMAIL_HOST is empty. The password is read from a file, never from .env.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_ENABLED = bool(EMAIL_HOST)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() != "false"
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_FROM", "redshadow@localhost")
_email_pw_file = os.environ.get("EMAIL_HOST_PASSWORD_FILE", "")
EMAIL_HOST_PASSWORD = open(_email_pw_file).read().strip() if _email_pw_file else ""  # noqa: SIM115
EMAIL_TIMEOUT = 10
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "rs_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = TLS_ON
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_IDLE_SECONDS", "1800"))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ABSOLUTE_SECONDS = int(os.environ.get("SESSION_ABSOLUTE_SECONDS", "43200"))
CSRF_COOKIE_NAME = "rs_csrf"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = TLS_ON
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
]
MFA_ENCRYPTION_KEY = secret("MFA_ENCRYPTION_KEY")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "rs",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Default deny: authentication arrives in Phase 2; until then only views that
    # opt in with AllowAny (health) respond.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SessionAuthentication"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsAuthenticatedSession"],
    "NUM_PROXIES": 1,
    "DEFAULT_THROTTLE_RATES": {"login": "20/min", "mfa": "20/min", "password": "10/min"},
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.errors.api_exception_handler",
}

# Celery. Results are stored in database models (later phases), never in Redis.
CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "imports-cleanup-daily": {"task": "imports.cleanup", "schedule": 86400.0, "options": {"queue": "maintenance"}},
    "audit-verify-nightly": {
        "task": "audit.verify_integrity",
        "schedule": 86400.0,
        "options": {"queue": "maintenance"},
    },
    "reports-cleanup-daily": {"task": "reports.cleanup", "schedule": 86400.0, "options": {"queue": "maintenance"}},
    "findings-sla-sweep-hourly": {"task": "findings.sla_sweep", "schedule": 3600.0},
    "engagements-scenario-reminders-hourly": {"task": "engagements.scenario_reminders", "schedule": 3600.0},
    "findings-due-soon-hourly": {"task": "findings.due_soon_sweep", "schedule": 3600.0},
    "notifications-prune-daily": {
        "task": "notifications.prune",
        "schedule": 86400.0,
        "options": {"queue": "maintenance"},
    },
    "findings-expire-risk-acceptance-hourly": {"task": "findings.expire_risk_acceptance", "schedule": 3600.0},
    "cleanup-sessions-daily": {"task": "accounts.cleanup_sessions", "schedule": 86400.0},
    "purge-deleted-attachments-daily": {
        "task": "files.purge_deleted",
        "schedule": 86400.0,
        "options": {"queue": "maintenance"},
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logs.RequestIdFilter"},
        "redact": {"()": "apps.core.logs.RedactFilter"},
    },
    "formatters": {
        "std": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "std",
            "filters": ["request_id", "redact"],
        },
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    # PDF engine and font library: per-page progress at INFO is noise; warnings stay.
    "loggers": {"weasyprint": {"level": "WARNING"}, "fontTools": {"level": "WARNING"}},
}
