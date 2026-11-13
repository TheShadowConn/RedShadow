import logging
import re
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SENSITIVE = re.compile(
    r"(?i)(password|passwd|token|secret|cookie|authorization|api[_-]?key)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s,\"'&]+)"
)


def redact(text: str) -> str:
    return _SENSITIVE.sub(r"\1\2[REDACTED]", text)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True
