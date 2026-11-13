import re
import uuid

from .logs import request_id_var

_VALID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class RequestIdMiddleware:
    """Attach a request id to the request, the log context and the response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID", "")
        if not _VALID.match(rid):
            rid = uuid.uuid4().hex
        request.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid
        return response
