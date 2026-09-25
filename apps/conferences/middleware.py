from django.conf import settings


class ConferenceHostMiddleware:
    """Requests to CONFERENCE_HOST (conference.iglc.net) get the conference sites' URLs only:
    the CMS pages of that Wagtail Site, plus robots.txt, media and documents. Requests to
    PROGRAMME_HOST (program.iglc.net) get the current conference's programme at the venue."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.host = (getattr(settings, "CONFERENCE_HOST", "") or "").lower()
        self.programme_host = (getattr(settings, "PROGRAMME_HOST", "") or "").lower()

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        request.conference_host = bool(self.host) and host == self.host
        request.programme_host = bool(self.programme_host) and host == self.programme_host
        if request.conference_host:
            request.urlconf = "config.conference_urls"
        elif request.programme_host:
            request.urlconf = "config.programme_urls"
        return self.get_response(request)
