"""Setting up the conference sites: the Wagtail Site, and a group per conference for its organisers.

    sync_site()                  run after every migrate: the Site's host name follows CONFERENCE_HOST
    organiser_group(home)        the group "IGLC 35 organisers" and the image collection "IGLC 35"
    seed(conference, current)    a home page with the standard pages, as drafts to fill in
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import transaction


def _port() -> int:
    url = urlsplit(settings.SITE_URL)
    if url.port:
        return url.port
    return 443 if url.scheme == "https" else 80


def index_page(create: bool = True):
    from wagtail.models import Page

    from .models import ConferenceIndexPage

    index = ConferenceIndexPage.objects.first()
    if index or not create:
        return index
    root = Page.get_first_root_node()
    if root is None:
        return None
    return root.add_child(instance=ConferenceIndexPage(title="IGLC conferences", slug="conferences"))


def sync_site(**kwargs):
    """The conference sites' Wagtail Site, at CONFERENCE_HOST. Repeatable."""
    from wagtail.models import Site

    host = getattr(settings, "CONFERENCE_HOST", "")
    if not host:
        return
    with transaction.atomic():
        index = index_page()
        if index is None:
            return
        site = Site.objects.filter(root_page=index).first() or Site(root_page=index)
        site.hostname, site.port, site.site_name, site.is_default_site = host, _port(), "IGLC conferences", False
        site.save()


# ---------------------------------------------------------------- organisers

PAGE_PERMISSIONS = ("add_page", "change_page", "publish_page")  # organisers publish their own pages
IMAGE_PERMISSIONS = ("add_image", "change_image", "choose_image")
DOCUMENT_PERMISSIONS = ("add_document", "change_document", "choose_document")


def organiser_group(home) -> Group:
    """The group whose members edit and publish this conference's pages,
    and upload its pictures and documents. Repeatable."""
    from wagtail.models import Collection, GroupCollectionPermission, GroupPagePermission

    name = f"IGLC {home.conference.number}"
    group, _ = Group.objects.get_or_create(name=f"{name} organisers")
    group.permissions.add(Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin"))
    for codename in PAGE_PERMISSIONS:
        GroupPagePermission.objects.get_or_create(
            group=group, page=home, permission=Permission.objects.get(content_type__app_label="wagtailcore",
                                                                      codename=codename))
    root = Collection.get_first_root_node()
    collection = root.get_children().filter(name=name).first() or root.add_child(name=name)
    for app, codenames in (("wagtailimages", IMAGE_PERMISSIONS), ("wagtaildocs", DOCUMENT_PERMISSIONS)):
        for codename in codenames:
            GroupCollectionPermission.objects.get_or_create(
                group=group, collection=collection,
                permission=Permission.objects.get(content_type__app_label=app, codename=codename))
    return group


# ---------------------------------------------------------------- a new site

def add_standard_pages(home, publish: bool = False):
    """The standard pages (StandardPageTemplate, edited in the back office) below a conference
    home page, as drafts to fill in. Pages that are there already (by slug) are left alone."""
    from . import models

    existing = set(home.get_children().values_list("slug", flat=True))
    for template in models.StandardPageTemplate.objects.filter(active=True):
        if template.slug in existing:
            continue
        page = getattr(models, template.page_type)(title=template.title, slug=template.slug,
                                                   show_in_menus=template.show_in_menus, live=publish)
        page.intro = template.intro
        if template.page_type in template.WITH_BODY:
            page.body = list(template.body.raw_data)
        home.add_child(instance=page)
        page.save_revision()


def seed(conference, current: bool = False, publish: bool = False):
    """A conference home page with the standard pages. Repeatable. Returns the home page."""
    from .models import ConferenceHomePage, ImportantDate

    home = ConferenceHomePage.objects.filter(conference=conference).first()
    if home is None:
        home = ConferenceHomePage(
            title=f"IGLC {conference.number}: {conference.location}" if conference.city else f"IGLC {conference.number}",
            slug=str(conference.start_date.year), conference=conference, is_current=current,
            body=[("important_dates", None)], live=publish)
        index_page().add_child(instance=home)
        ImportantDate.objects.create(page=home, label="Conference", date=conference.start_date,
                                     end_date=conference.end_date, sort_order=0)
        home = ConferenceHomePage.objects.get(pk=home.pk)
        home.save_revision()  # after the date, so that the draft the organisers edit has it
    add_standard_pages(home, publish=publish)
    organiser_group(home)
    return home
