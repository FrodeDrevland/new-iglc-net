"""Redirects from the old iglc.net (ASP.NET MVC, 2014-2026) to the new URLs.

The old site matched URLs case-insensitively and accepted IDs both in the path
and as ?id=. Paper and conference URLs keep their paths; they only lose the capitals.
The full list of old routes is in docs/url-inventory.md.
"""

import re
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.urls import Resolver404, resolve

# Old path (lower case, no trailing slash) -> new path.
STATIC_REDIRECTS = {
    "/home": "/",
    "/home/index": "/",
    "/home/about": "/about/",
    "/home/charterandoperatingprocedures": "/charter-and-operating-procedures/",
    "/home/standards": "/standards/",
    "/home/committees": "/about/committees/",
    "/home/contact": "/contact/",
    "/home/copyright": "/copyright/",
    "/home/referencing": "/for-authors/referencing/",
    "/referencing": "/for-authors/referencing/",
    "/referencing/index": "/for-authors/referencing/",
    "/home/activeconference": "/active-conference/",
    "/home/active-conference": "/active-conference/",
    "/activeconference": "/active-conference/",
    "/activeconference/index": "/active-conference/",
    "/activeconference/callforpapers": "/active-conference/call-for-papers/",
    # The old page only forwarded visitors to the conference's own website (see CONFERENCE_WEBSITE).
    "/activeconference/conferencewebsite": "conference-website",
    "/activeconference/followingconference": "/active-conference/following-conference/",
    "/home/important-links": "/links/",
    "/links": "/links/",
    "/links/index": "/links/",
    "/community/links": "/links/",
    "/community/coaching": "/community/coaching/",
    "/community/mailinglist": "/community/mailing-list/",
    "/forauthors/referencing": "/for-authors/referencing/",
    "/anniversary": "/anniversary/",
    "/anniversary/index": "/anniversary/",
    "/anniversary/svenbertelsen80": "/anniversary/sven-bertelsen-80/",
    "/inmemoriam": "/in-memoriam/",
    "/inmemoriam/index": "/in-memoriam/",
    "/inmemoriam/svenbertelsen": "/in-memoriam/sven-bertelsen/",
    "/proceedings": "/proceedings/",
    "/proceedings/index": "/proceedings/",
    "/papers/index": "/papers",
    "/index/papers": "/papers",  # broken link on the old Proceedings page
    "/errors/error404": "/",
    "/authors/index": "/authors/",
    "/authors/createorassignauthorpersons": "/manage/",
}

# Old areas that need a login are replaced by the new admin.
PREFIX_REDIRECTS = [
    ("/admin", "/cms/"),
    ("/account", "/cms/login/"),
    ("/datapunching", "/manage/"),
]

# Old path that took ?id= -> new path.
ID_QUERY_ROUTES = {
    "/papers/details": "/papers/details/{id}",
    "/papers/conference": "/papers/conference/{id}",
    "/papers/pdf": "/papers/details/{id}/pdf",
    "/papers/presentation": "/papers/details/{id}/presentation",
    "/papers/exportbibtex": "/papers/exportbibtex/{id}",
    "/papers/exportris": "/papers/exportris/{id}",
    "/papers/exportconferencebibtex": "/papers/exportconferencebibtex/{id}",
    "/papers/exportconferenceris": "/papers/exportconferenceris/{id}",
}

FOR_AUTHORS_PATHS = {"/forauthors", "/forauthors/index", "/forauthors/showview"}

# Views of the old "For authors" section; also reachable as /ForAuthors/<View>.
FOR_AUTHORS_VIEWS = [
    "ContentRequirements", "CopyrightPolicy", "EthicsAndMalpracticeStatement", "FormattingRequirements",
    "Keywords", "PaperStructure", "PaperSubmissionAndReviewProcess", "Publication", "PublicationSchedule",
    "Referencing", "Templates",
]

# Paths served as files; never rewritten.
UNTOUCHED_PREFIXES = ("/static/", "/media/", "/documents/")


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def legacy_target(path: str, query) -> str | None:
    """The new URL for an old URL, or None if the path is not an old one."""
    key = path.lower().rstrip("/") or "/"

    if key in FOR_AUTHORS_PATHS:
        view = re.sub(r"[^A-Za-z]", "", query.get("view", ""))
        return f"/for-authors/{_kebab(view)}/" if view and view.lower() != "about" else "/for-authors/"

    if key in STATIC_REDIRECTS:
        target = STATIC_REDIRECTS[key]
        return settings.CONFERENCE_WEBSITE if target == "conference-website" else target

    for view in FOR_AUTHORS_VIEWS:
        if key == f"/forauthors/{view.lower()}":
            return f"/for-authors/{_kebab(view)}/"

    for prefix, target in PREFIX_REDIRECTS:
        if key == prefix or key.startswith(prefix + "/"):
            return target

    template = ID_QUERY_ROUTES.get(key)
    if template and query.get("id", "").isdigit():
        return template.format(id=query["id"])

    match = re.fullmatch(r"/papers/(pdf|presentation)/(\d+)", key)
    if match:
        return f"/papers/details/{match.group(2)}/{match.group(1)}"

    return None


def _resolves(path: str) -> bool:
    try:
        resolve(path)
    except Resolver404:
        return False
    return True


class LegacyUrlMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("GET", "HEAD") and request.path.lower().startswith("/content/"):
            # Old files, now in blob storage. Temporary redirect, so the storage can move later.
            return HttpResponseRedirect(f"{settings.LEGACY_CONTENT_URL}/{quote(request.path[len('/content/'):])}")
        if request.method in ("GET", "HEAD") and not request.path.startswith(UNTOUCHED_PREFIXES):
            target = legacy_target(request.path, request.GET)
            if target is None and request.path != request.path.lower():
                lowered = request.path.lower()
                if _resolves(lowered):
                    query = request.META.get("QUERY_STRING", "")
                    target = f"{lowered}?{query}" if query else lowered
            if target and target != request.get_full_path():
                return HttpResponsePermanentRedirect(target)
        return self.get_response(request)
