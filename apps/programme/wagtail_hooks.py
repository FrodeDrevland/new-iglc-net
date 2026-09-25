"""The conference programme in the back office (/manage/programme/)."""

from django.urls import include, path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from . import admin_urls


@hooks.register("register_admin_urls")
def programme_urls():
    return [path("programme/", include(admin_urls))]


class ProgrammeMenuItem(MenuItem):
    def is_shown(self, request):
        from .access import programmes_for

        return request.user.is_superuser or programmes_for(request.user).exists()


@hooks.register("register_conferences_menu_item")  # the Conferences menu (apps/conferences/admin_views.py)
def programme_menu_item():
    return ProgrammeMenuItem("Programmes", reverse("programme:list"), icon_name="time", order=2)
