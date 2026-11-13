import re
from typing import Any

_SENSITIVE_KEY = re.compile(r"(password|passwd|secret|token|recovery|code_hash|api_key|authorization|cookie)", re.I)
REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Recursively mask values whose key looks sensitive. Booleans such as mfa_enabled are kept."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SENSITIVE_KEY.search(str(k)) and not isinstance(v, bool) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def diff(old: dict, new: dict) -> dict:
    """{field: [old, new]} for fields that differ."""
    return {k: [old.get(k), new.get(k)] for k in new if old.get(k) != new.get(k)}
