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


@hooks.register("register_admin_menu_item")
def programme_menu_item():
    return ProgrammeMenuItem("Conference programme", reverse("programme:list"), icon_name="date", order=260)
