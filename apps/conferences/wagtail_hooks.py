from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path, reverse
from wagtail import hooks

from .admin_views import MENU_HOOK, ConferenceViewSet, conferences_menu_item, your_conference_menu_item
from .models import ConferenceHomePage
from .setup import add_standard_pages, organiser_group


# ---------------------------------------------------------------- the Conferences menu and list

@hooks.register("register_admin_menu_item")
def conferences_menu():
    return conferences_menu_item()


@hooks.register(MENU_HOOK)
def your_conference():
    return your_conference_menu_item()


@hooks.register("construct_homepage_panels")
def your_conferences_panel(request, panels):
    """On the back office's front page: the conferences this person has a role in, with what to do."""
    from .panels import YourConferencesPanel

    panel = YourConferencesPanel(request)
    if panel.conferences:
        panels.insert(0, panel)


@hooks.register("register_admin_viewset")
def conference_viewset():
    return ConferenceViewSet("conferences", url_prefix="conferences")


@hooks.register("register_admin_urls")
def old_conference_urls():
    """The conference list used to be under Archive (/manage/archive/conference/...)."""
    def old(request, rest=""):
        query = request.META.get("QUERY_STRING")
        return redirect(reverse("conferences:index") + rest + (f"?{query}" if query else ""), permanent=True)

    return [path("archive/conference/", old), path("archive/conference/<path:rest>", old)]


@hooks.register("after_create_page")
def conference_organisers(request, page):
    if isinstance(page.specific, ConferenceHomePage):
        organiser_group(page.specific)
        add_standard_pages(page.specific)
        messages.info(request, "The standard pages (Conferences → Website standard pages) were added below it "
                               "as drafts. Delete the ones the conference does not need.")


def _frozen_home(page):
    return ConferenceHomePage.objects.ancestor_of(page, inclusive=True).filter(frozen=True).first()


def _refuse(request, page):
    home = _frozen_home(page)
    if home and not request.user.is_superuser:
        messages.error(request, f"The website of {home.short_name} is frozen: the conference has taken place. "
                                f"Ask the IGLC if something must change.")
        return redirect("wagtailadmin_explore", (page.get_parent() or page).pk)
    return None


@hooks.register("before_edit_page")
def frozen_edit(request, page):
    return _refuse(request, page)


@hooks.register("before_delete_page")
def frozen_delete(request, page):
    return _refuse(request, page)


@hooks.register("before_move_page")
def frozen_move(request, page, destination):
    return _refuse(request, page) or _refuse(request, destination)


@hooks.register("before_create_page")
def frozen_create(request, parent_page, page_class):
    home = _frozen_home(parent_page)
    if home and not request.user.is_superuser:
        messages.error(request, f"The website of {home.short_name} is frozen: no pages can be added.")
        return redirect("wagtailadmin_explore", parent_page.pk)
    return None


# ---------------------------------------------------------------- standard pages (Settings menu)

from wagtail.admin.panels import HelpPanel  # noqa: E402
from wagtail.admin.ui.tables import BooleanColumn, Column  # noqa: E402
from wagtail.admin.viewsets.model import ModelViewSet  # noqa: E402

from .models import StandardPageTemplate  # noqa: E402


class StandardPageViewSet(ModelViewSet):
    model = StandardPageTemplate
    name = "conference_standard_pages"
    menu_label = "Website standard pages"
    menu_name = "website-standard-pages"
    icon = "doc-empty-inverse"
    menu_order = 4
    menu_hook = MENU_HOOK  # under Conferences
    sort_order_field = "sort_order"
    list_display = ["title", "slug", Column("kind", label="Kind", accessor="get_page_type_display"),
                    BooleanColumn("show_in_menus", label="In the menu"), BooleanColumn("active", label="Active")]
    list_filter = ["page_type", "active"]
    ordering = "sort_order"
    panels = [
        HelpPanel("<p>Every new conference website starts with these pages, as drafts, in this order "
                  "(drag the rows in the list to change it). Changes apply to sites created afterwards; "
                  "existing sites keep their pages.</p>"),
    ] + StandardPageTemplate.panels


@hooks.register("register_admin_viewset")
def standard_pages_viewset():
    return StandardPageViewSet()
