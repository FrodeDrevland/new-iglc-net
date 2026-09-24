from django.contrib import messages
from django.shortcuts import redirect
from wagtail import hooks

from .models import ConferenceHomePage
from .setup import add_standard_pages, organiser_group


@hooks.register("after_create_page")
def conference_organisers(request, page):
    if isinstance(page.specific, ConferenceHomePage):
        organiser_group(page.specific)
        add_standard_pages(page.specific)
        messages.info(request, "The standard pages were added below it as drafts: call for papers, important "
                               "dates, programme, keynotes, committees, accepted papers, venue and travel, "
                               "registration and sponsors. Delete the ones the conference does not need.")


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
