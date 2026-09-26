"""The conference workspace in the back office: /manage/<number>/ and everything under it.

Inside a conference (its pages under /manage/<number>/, its programme and production, and the editor
of one of its website pages) the sidebar shows only that conference: Overview, Website, Branding,
People, Programme, Proceedings, Images, Documents and Help. A switcher at the top of the sidebar
leads to the person's other conferences and, for the IGLC's own people, to the IGLC administration
(the full menu). Pictures and documents belong to the conference last visited (kept in the session).

People whose only roles are in conferences never see the IGLC administration: /manage/ takes them to
their conference.
"""

from __future__ import annotations

import copy
import re

from django.urls import reverse
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem

from . import roles

SESSION_KEY = "iglc_workspace"

_PATTERNS = None


def _patterns():
    global _PATTERNS
    if _PATTERNS is None:
        admin = reverse("wagtailadmin_home")  # /manage/
        esc = re.escape(admin)
        _PATTERNS = {
            "number": re.compile("^" + esc + r"(?:programme/|production/)?(\d+)(?:/|$)"),
            "page": re.compile("^" + esc + r"pages/(\d+)/"),
            "add": re.compile("^" + esc + r"pages/add/[^/]+/[^/]+/(\d+)/"),
            "home": re.compile("^" + esc + "$"),
            "shared": re.compile("^" + esc + r"(images|documents|account|site-help|password_reset)/"),
        }
    return _PATTERNS


def conference_of_page(page_id):
    from .models import ConferenceHomePage

    from wagtail.models import Page

    page = Page.objects.filter(pk=page_id).first()
    if page is None:
        return None
    home = ConferenceHomePage.objects.ancestor_of(page, inclusive=True).select_related("conference").first()
    return home.conference if home else None


def from_path(path):
    """The conference a back-office address belongs to, or None. ("shared" addresses: None too.)"""
    from apps.archive.models import Conference

    patterns = _patterns()
    match = patterns["number"].match(path)
    if match:
        return Conference.objects.filter(number=int(match.group(1))).first()
    match = patterns["add"].match(path) or patterns["page"].match(path)
    if match:
        return conference_of_page(int(match.group(1)))
    return None


def only_conferences(user) -> bool:
    """True for people whose only way into the back office is a role in a conference."""
    if not user.is_authenticated or user.is_superuser:
        return False
    return set(user.get_all_permissions()) <= {"wagtailadmin.access_admin"}


def current(request):
    """The conference the request is working in, or None (the IGLC administration). Cached on the
    request; the last one is kept in the session for pictures, documents and help."""
    if hasattr(request, "_iglc_workspace"):
        return request._iglc_workspace
    from apps.archive.models import Conference

    user = request.user
    conference = None
    path = request.path
    patterns = _patterns()
    if patterns["home"].match(path):
        request.session.pop(SESSION_KEY, None)
    else:
        conference = from_path(path)
        if conference is not None and roles.can_view(user, conference):
            request.session[SESSION_KEY] = conference.number
        elif conference is not None:
            conference = None
        elif patterns["shared"].match(path) or only_conferences(user):
            number = request.session.get(SESSION_KEY)
            conference = Conference.objects.filter(number=number).first() if number else None
            if conference is not None and not roles.can_view(user, conference):
                conference = None
    request._iglc_workspace = conference
    return conference


def home_for(request):
    """Where /manage/ takes someone who only has conference roles: the conference they were last in,
    or their newest."""
    conferences = roles.conferences_for(request.user)
    last = request.session.get(SESSION_KEY)
    chosen = (conferences.filter(number=last).first() if last else None) or conferences.first()
    return reverse("conference:overview", args=[chosen.number]) if chosen else None


# ---------------------------------------------------------------- the sidebar

def _label(conference):
    return f"IGLC {conference.number}" + (f": {conference.city}" if conference.city else "")


def switcher(request, conference):
    """The first item of the sidebar: where you are, and where else you can go."""
    from apps.archive.models import Conference

    user = request.user
    items = []
    order = 1
    if user.is_superuser:
        others = Conference.objects.exclude(start_date=None).order_by("-number")[:6]
    else:
        others = roles.conferences_for(user)
    for other in others:
        if conference is not None and other.pk == conference.pk:
            continue
        items.append(MenuItem(_label(other), reverse("conference:overview", args=[other.number]),
                              name=f"conference-{other.number}", icon_name="date", order=order))
        order += 1
    if not only_conferences(user):
        if user.is_superuser or user.has_perm("archive.view_conference") or user.has_perm("archive.change_conference"):
            items.append(MenuItem("All conferences", reverse("conferences:index"), name="all-conferences-switch",
                                  icon_name="list-ul", order=90))
        if conference is not None:
            items.append(MenuItem("IGLC admin", reverse("wagtailadmin_home"), name="iglc-admin",
                                  icon_name="site", order=100))
    if not items:
        return None
    label = _label(conference) if conference else "IGLC admin"
    return SubmenuMenuItem(label, Menu(items=items), name="workspace-switcher",
                           icon_name="date" if conference else "site", order=-100)


def conference_items(request, conference):
    """The sidebar inside a conference."""
    from apps.production.access import productions_for
    from apps.programme.access import programmes_for

    user = request.user
    mine = roles.roles_of(user, conference)
    number = conference.number
    items = [MenuItem("Overview", reverse("conference:overview", args=[number]), name="conference-overview",
                      icon_name="home", order=1)]
    if mine & {"iglc", "chair", "organiser"} or user.has_perm("archive.change_conference"):
        items += [
            MenuItem("Website", reverse("conference:website", args=[number]), name="conference-website",
                     icon_name="doc-full", order=2),
            MenuItem("Dates and links", reverse("conference:dates", args=[number]), name="conference-dates",
                     icon_name="calendar", order=3),
            MenuItem("Branding", reverse("conference:branding", args=[number]), name="conference-branding",
                     icon_name="pick", order=4),
        ]
    items.append(MenuItem("People", reverse("conference:people", args=[number]), name="conference-people",
                          icon_name="group", order=5))
    if programmes_for(user).filter(conference=conference).exists():
        items.append(MenuItem("Programme", reverse("programme:overview", args=[number]),
                              name="conference-programme", icon_name="time", order=6))
    if productions_for(user).filter(conference=conference).exists():
        items.append(MenuItem("Proceedings", reverse("proceedings:production", args=[number]),
                              name="conference-proceedings", icon_name="doc-full-inverse", order=7))
    # Submission and review (phase 5) goes here, order 8.
    return items


def construct_menu(request, menu_items):
    """construct_main_menu: the conference's own sidebar inside a conference; the full menu with the
    switcher on top in the IGLC administration."""
    conference = current(request)
    top = switcher(request, conference)
    if conference is None:
        if top:
            menu_items.append(top)
        return
    keep = []
    for item in menu_items:
        if item.name in ("images", "documents", "help"):
            item = copy.copy(item)  # the registered items are shared between requests
            item.order = {"images": 20, "documents": 21, "help": 30}[item.name]
            keep.append(item)
    menu_items[:] = ([top] if top else []) + conference_items(request, conference) + keep
