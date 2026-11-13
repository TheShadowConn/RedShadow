def client_ip(request) -> str | None:
    """Client address as set by Nginx (it overwrites X-Forwarded-For with $remote_addr).

    The backend is never published, so Nginx is the only caller that can set this header.
    """
    django_request = getattr(request, "_request", request)
    forwarded = django_request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip() or None
    return django_request.META.get("REMOTE_ADDR") or None
