"""Settings for generating the OpenAPI schema only (`make schema`).

Not used at runtime; drf-spectacular is a dev tool.
"""

from .test import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, "drf_spectacular"]  # noqa: F405
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema"}  # noqa: F405
SPECTACULAR_SETTINGS = {
    "TITLE": "RedShadow API",
    "DESCRIPTION": (
        "Pentest management platform. Session cookie plus CSRF header. "
        "Errors: {error: {code, message, fields, request_id}}."
    ),
    "VERSION": "1",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}
