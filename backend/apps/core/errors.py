from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

CODES = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "throttled",
}


class Conflict(APIException):
    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class PayloadTooLarge(APIException):
    status_code = 413
    default_detail = "The file is too large."
    default_code = "payload_too_large"


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return str(value)


def envelope(status: int, message: str, request=None, fields: dict | None = None) -> dict:
    return {
        "error": {
            "code": CODES.get(status, "error" if status < 500 else "server_error"),
            "message": message,
            "fields": fields or {},
            "request_id": getattr(request, "request_id", None),
        }
    }


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django handler500
    data = response.data
    fields: dict = {}
    if isinstance(data, dict) and set(data) == {"detail"}:
        message = str(data["detail"])
    elif isinstance(data, dict):
        message, fields = "Invalid input.", _plain(data)
    elif isinstance(data, list):
        message = " ".join(_plain(data))
    else:
        message = "Request failed."
    response.data = envelope(response.status_code, message, context.get("request"), fields)
    return response


def not_found(request, exception=None):
    return JsonResponse(envelope(404, "Not found.", request), status=404)


def server_error(request):
    return JsonResponse(envelope(500, "Internal server error.", request), status=500)
