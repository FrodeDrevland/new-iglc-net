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


class ConferencePageExplorerMiddleware:
    """In the back office, /manage/pages/<id>/ lists a page's subpages. For a conference page without
    subpages that list is empty, and organisers took it for the page having no content. Send them to
    the page's editor instead (not superusers, who may want to add subpages there)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._pattern = None

    def pattern(self):
        if self._pattern is None:
            import re

            from django.urls import reverse

            prefix = reverse("wagtailadmin_explore", args=[1]).rsplit("1/", 1)[0]
            self._pattern = re.compile("^" + re.escape(prefix) + r"(\d+)/$")
        return self._pattern

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (request.method == "GET" and not getattr(request, "conference_host", False) and not request.GET
                and user is not None and user.is_authenticated and not user.is_superuser):
            match = self.pattern().match(request.path)
            if match:
                target = self._editor_for(int(match.group(1)), user)
                if target:
                    from django.shortcuts import redirect

                    return redirect(target)
        return self.get_response(request)

    @staticmethod
    def _editor_for(pk, user):
        from django.urls import reverse
        from wagtail.models import Page

        from .setup import index_page

        page = Page.objects.filter(pk=pk).first()
        index = index_page(create=False)
        if (page is None or index is None or page.numchild or page.depth <= index.depth + 1
                or not page.path.startswith(index.path)):
            return None
        if not page.permissions_for_user(user).can_edit():
            return None
        return reverse("wagtailadmin_pages:edit", args=[pk])
