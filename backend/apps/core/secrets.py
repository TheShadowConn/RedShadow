import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def secret(name: str, default: str | None = None) -> str:
    """Read a secret from the file named by ``<NAME>_FILE``, else from ``<NAME>``."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"Cannot read secret file for {name}.") from exc
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required secret {name} (set {name}_FILE).")
    return value
