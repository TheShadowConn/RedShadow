from .base import *  # noqa: F403

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed; Argon2 has its own test
CELERY_TASK_ALWAYS_EAGER = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
_HIGH = {"login": "1000/min", "mfa": "1000/min", "password": "1000/min"}
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": _HIGH}  # noqa: F405
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
