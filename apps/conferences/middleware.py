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


class ConferenceWorkspaceMiddleware:
    """The back office for people whose work is in conferences (apps/conferences/workspace.py):

    - /manage/ takes someone who only has conference roles to their conference's Overview;
    - Wagtail's page tree (/manage/pages/<id>/) for a conference page takes them to the conference's
      Website page instead. Superusers keep the page tree.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._patterns = None

    def patterns(self):
        if self._patterns is None:
            import re

            from django.urls import reverse

            home = reverse("wagtailadmin_home")
            explore = reverse("wagtailadmin_explore", args=[1]).rsplit("1/", 1)[0]
            self._patterns = (re.compile("^" + re.escape(home) + "$"),
                              re.compile("^" + re.escape(explore) + r"(\d+)/$"))
        return self._patterns

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (request.method == "GET" and not getattr(request, "conference_host", False)
                and user is not None and user.is_authenticated and not user.is_superuser):
            target = self._redirect(request, user)
            if target:
                from django.shortcuts import redirect

                return redirect(target)
        return self.get_response(request)

    def _redirect(self, request, user):
        from django.urls import reverse

        from . import roles, workspace

        home, explore = self.patterns()
        if home.match(request.path):
            return workspace.home_for(request) if workspace.only_conferences(user) else None
        match = explore.match(request.path)
        if match and not request.GET:
            conference = workspace.conference_of_page(int(match.group(1)))
            if conference is not None and roles.can_view(user, conference):
                return reverse("conference:website", args=[conference.number])
        return None
