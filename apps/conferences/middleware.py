from django.conf import settings


class ConferenceHostMiddleware:
    """Requests to CONFERENCE_HOST (conference.iglc.net) get the conference sites' URLs only:
    the CMS pages of that Wagtail Site, plus robots.txt, media and documents."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.host = (getattr(settings, "CONFERENCE_HOST", "") or "").lower()

    def __call__(self, request):
        request.conference_host = bool(self.host) and request.get_host().split(":")[0].lower() == self.host
        if request.conference_host:
            request.urlconf = "config.conference_urls"
        return self.get_response(request)
