"""Middleware for running behind Azure App Service (or any proxy)."""

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, HttpResponsePermanentRedirect


class HealthCheckMiddleware:
    """Answer /healthz before anything else looks at the Host header.

    App Service's health check and warm-up requests use an internal host name that is not in
    ALLOWED_HOSTS, so this runs first. It returns 200 when the database answers, else 503.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception:  # noqa: BLE001 - any failure means unhealthy
                return HttpResponse("database unavailable\n", status=503, content_type="text/plain")
            return HttpResponse("ok\n", content_type="text/plain")
        return self.get_response(request)


class HostRedirectMiddleware:
    """Redirect whole host names, e.g. iglc.net -> www.iglc.net (setting HOST_REDIRECTS)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.redirects = settings.HOST_REDIRECTS

    def __call__(self, request):
        if self.redirects:
            host = request.get_host().split(":")[0].lower()
            target = self.redirects.get(host)
            if target:
                return HttpResponsePermanentRedirect(f"https://{target}{request.get_full_path()}")
        return self.get_response(request)
